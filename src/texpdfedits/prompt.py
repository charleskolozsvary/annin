import logging
import argparse
import pymupdf
import json
import time
import pickle
import re

from texpdfedits.corr import Correction, getCorrections, groupOverlappingCorrections

import google.genai as genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

THINKING_GEMINI_MODELS = {'gemini-3-flash-preview', 'gemini-3-pro-preview'}

def writeListOfPrompts(corrections: list[Correction], tex_filename: str) -> None:
    prompt_dir = Path('markdown_prompts')
    Path.mkdir(prompt_dir, exist_ok=True)
    
    savefile = f"{prompt_dir / Path(tex_filename).stem}_list_of_prompts.md"

    with open(savefile, 'w') as f:
        f.write('\n\n---\n\n'.join([f"# {corr.index}\n\n" + corr.asMarkdownPrompt() for corr in corrections if corr is not None]))
    logging.info(f"The list of prompts have been written to {savefile}.")

def writePromptsWithResponses(
        corrections: list[Correction],
        updated_snippets,
        explanations,
        tex_filename,
        identifying_run_str,
        system_prompt,
        standalone_corridxs: list[int],
        group_corridxs: list[list[int]],
):
    prompt_dir = Path('markdown_prompts')
    Path.mkdir(prompt_dir, exist_ok=True)
    
    savefile = f"{prompt_dir / Path(tex_filename).stem}_responses_{identifying_run_str}.md"

    prompts_with_responses = []

    corridx_to_correction = {corr.index: corr for corr in corrections}

    def writePromptsAndResponses(corr_idxs: list[int]):
        for corridx in corr_idxs:
            corr = corridx_to_correction[corridx]
            if corr is None:
                continue
            prompt = corr.asMarkdownPrompt()
            updated_snippet = updated_snippets[corr.index] if corr.index in updated_snippets else None
            if updated_snippet is None:
                continue
            explanation = explanations[corr.index] if corr.index in explanations else 'No explanation found'
            if re.search(r'(?:\s*#{5} Before codeblock\s*#{5} After codeblock|^\s*$)', explanation):
                explanation = ''
            else:
                explanation = '\n#### Explanation\n' + explanation

            if updated_snippet.startswith("#### FAILURE:"):
                beneath_response = updated_snippet
            else:
                beneath_response = f"```latex\n{updated_snippet}\n```"
            
            prompts_with_responses.append(
                f"## {corr.index}\n\n{prompt}\n### Response\n{beneath_response}\n{explanation}"
            )

    writePromptsAndResponses(standalone_corridxs)
    for g in group_corridxs:
        prompts_with_responses.append(f"# Overlapping corrections: {g}")
        writePromptsAndResponses(g)

    with open(savefile, 'w') as f:
        f.write(f"# System prompt\n{system_prompt}\n---\n")
        f.write('\n\n'.join(prompts_with_responses))

    logging.info(f"The prompts with their responses have been written to {savefile}.")    

def callGemini(prompt: str, model: str, system_prompt: str, temperature: float, top_p: float, history: list = None, **kwargs):
    """
    Call Google's Gemini API with chat history support.
    
    Args:
        prompt: The current user prompt
        model: Model name (e.g., 'gemini-2.0-flash-exp')
        system_prompt: Optional system instruction
        history: List of dicts with 'prompt' and 'response' keys
    
    Returns:
        Response text from the model
    """
    client = genai.Client()
    
    messages = []
    if history:
        for exchange in history:
            messages.append({'role': 'user', 'parts': [{'text': exchange['prompt']}]})
            messages.append({'role': 'model', 'parts': [{'text': exchange['response']}]})
    
    messages.append({'role': 'user', 'parts': [{'text': prompt}]})

    if model not in THINKING_GEMINI_MODELS:
        config = types.GenerateContentConfig(
            response_mime_type = 'text/plain',
            system_instruction=system_prompt,
            temperature=temperature,   
            top_p=top_p,
        )
    else:
        if model == 'gemini-3-pro-preview':
            thinking_level = 'high'
            temperature = 0.4
            top_p = .9
        else:
            thinking_level = 'minimal'
            
        config = types.GenerateContentConfig(
            response_mime_type = "text/plain",
            system_instruction=system_prompt,
            temperature=temperature,   
            top_p=top_p,         
            thinking_config=types.ThinkingConfig(
                include_thoughts=False, 
                thinking_level=thinking_level # can be minimal, low, medium, or (default) high
            )
        )

    response = client.models.generate_content(
        model=model,
        contents=messages,
        config=config
    )
    
    return response.text

def callClaude(prompt: str, model: str, system_prompt: str, temperature: float, top_p: float, history: list = None, **kwargs):
    """Call Anthropic's Claude API (to be implemented)"""
    # TODO: implement with anthropic package
    return prompt

def callEcho(prompt: str, model: str, system_prompt: str, history: list, *args):
    """ Just return the first supplied latex code block """
    codeblocks = []
    matches = re.finditer(r'```(\w+)\n(.*?)\n?```', prompt, re.DOTALL)
    
    for match in matches:
        codeblocks.append({
            'full-match': match.group(0),
            'language': match.group(1),
            'code': match.group(2),
            'start': match.start(),
            'end': match.end()
        })

    latex_blocks = [block for block in codeblocks if block['language'] in 'latex']

    if not latex_blocks:
        logging.warning("No latex code block supplied to Echo model; returning empty block")
        return "```latex\n\n```"
    
    return '\nEcho explanation (nothing)'.join([block['full-match'] for block in latex_blocks])

def callLLM(prompt: str, model: str, system_prompt: str, model_temp: float, model_top_p: float, history: list | None = None):
    """
    Dispatch to appropriate LLM based on model name.
    
    Args:
        prompt: The current user prompt
        model: Model identifier (e.g., 'gemini-2.0-flash-exp', 'claude-sonnet-4-20250514')
        system_prompt: Optional system instruction
        history: List of dicts with 'prompt' and 'response' keys
    
    Returns:
        Response text from the model
    """
    if 'gemini' in model.lower():
        llm = callGemini
    elif 'claude' in model.lower():
        llm = callClaude
    elif 'echo' in model.lower():
        llm = callEcho
    else:
        raise ValueError(f"Unrecognized model: {model}")

    # logging.info(f"Calling {model}...")
    start = time.time()    
    response = llm(prompt, model, system_prompt, model_temp, model_top_p, history)
    logging.info(f"{model} responded to prompt after {time.time() - start:.2f}s")
    
    return response

def getChunks(
    key_to_correction: dict[int, Correction],
    standalone_keys: list[int],
    chunksize: int
) -> dict[str, list[list[Correction]]]:
    """Chunk corrections by category. Could further group by type in the future."""
    
    chunks = {'standalone': []}
    
    def makeChunks(keys, category):
        curr_chunk = []
        for k in keys:
            curr_chunk.append(key_to_correction[k])
            if len(curr_chunk) == chunksize:
                chunks[category].append(curr_chunk)
                curr_chunk = []
        if curr_chunk:
            chunks[category].append(curr_chunk)
    
    makeChunks(standalone_keys, 'standalone')
    
    return chunks

def parseResponse(response_str: str, corrections: list[Correction], model_name: str):
    """Extract codeblocks and explanations from LLM response.
    
    Returns: list of dicts with 'code', 'explanation', 'language', 'start', 'end'
    """
    codeblocks = []
    matches = re.finditer(r'```(\w+)\n(.*?)\n?```', response_str, re.DOTALL)

    default_return = [{'code':response_str} for _ in corrections]

    if matches is None:
        logging.warning(
            "Could not parse Response: "
            f"No matching codeblocks found.\n\nBAD RESPONSE:\n{reseponse_str}"
        )
        return default_return, 1
    
    for match in matches:
        codeblocks.append({
            'language': match.group(1),
            'code': match.group(2),
            'start': match.start(),
            'end': match.end()
        })
    
    if len(codeblocks) != len(corrections):
        logging.warning(
            f"Could not parse response: "
            f"{len(codeblocks)} codeblocks were returned when expecting {len(corrections)}"
            f"\n\nBAD RESPONSE:\n{response_str}"
        )
        return default_return, 1
    
    languages = {block['language'] for block in codeblocks}
    if not languages.issubset({'latex', 'tex'}):
        logging.warning(
            f"Codeblock languages for corrections {[c.index for c in corrections]} "
            f"contained unexpected languages: {languages - {'latex', 'tex'}}"
        )
    
    # Extract explanations after codeblocks
    for i, block in enumerate(codeblocks):
        explanation = []
        before_start = codeblocks[i+1]['end'] if i+1 < len(codeblocks) else 0
        before_end = block['start']
        explanation.append('##### Before codeblock\n' + response_str[before_start:before_end].strip())
        
        after_start = block['end']
        after_end = codeblocks[i+1]['start'] if i < len(codeblocks)-1 else len(response_str)
        explanation.append('##### After codeblock\n' + response_str[after_start:after_end].strip())
        
        block['explanation'] = '\n'.join(explanation)
    
    return codeblocks, 0

def processStandaloneChunks(
        chunks: list[list[Correction]],
        model: str,
        updated_snippets: dict[int, str],
        explanations: dict[int, str],
        system_prompt: str,
        model_temp: float,
        model_top_p: float
) -> None:
    """Process standalone corrections in batches."""
    num_chunks = len(chunks)
    for i, chunk in enumerate(chunks):
        prompt = writeBatchPrompt(chunk)
        correction_indices = [corr.index for corr in chunk]
        
        logging.debug(f"\nSTANDALONE PROMPT {correction_indices}:\n{prompt}")

        def writeFailure(f_chunk, failure_response):
            for correction in f_chunk:
                updated_snippets[correction.index] = f'#### FAILURE:\n{failure_response}'
                explanations[correction.index] = ''
        
        response = callLLM(prompt, model, system_prompt, model_temp, model_top_p)

        if response is None or not response:
            logging.warning(
                f"Could not process standalone corrections {correction_indices}: "
                f"Response from callLLM was None or falsy (empty).\n\nBAD RESPONSE:\n{response}"
            )
            writeFailure(chunk, response)
            continue

        logging.debug(f"\nSTANDALONE RESPONSE {correction_indices}:\n{response}")
        parsed, status = parseResponse(response, chunk, model)
        
        if status != 0:
            logging.warning(
                f"Could not process standalone corrections {correction_indices}: "
                f"parseResponse returned failure status"
            )
            writeFailure(chunk, response)
            continue
        
        for correction, block in zip(chunk, parsed):
            updated_snippets[correction.index] = block['code']
            explanations[correction.index] = block['explanation']
            
        logging.info(f"Processed standalone correction   {i:3d}/{num_chunks-1:3d}")

def processOverlappingGroups(
    overlapping_groups: list[list[int]], 
    key_to_correction: dict[int, Correction],
    model: str, 
    updated_snippets: dict[int, str],
    explanations: dict[int, str],
    system_prompt: str,
    model_temp: float,
    model_top_p: float,
):
    """Process overlapping corrections. The difference between these and the standalone corrections is that the entire spanning
    snippet needs to be updated with each edit for easy substitution with the source later. So these cannot be processed in batches. At least
    not without reconstructing the original source from the several conflicting versions.

    We're actually not going to update the "entire spanning snippet anymore, so this is very redundant with process standalone corrections---
    desperately need refactoring
    """
    def writeFailure(f_correction, failure_response):
        updated_snippets[f_correction.index] = f'#### FAILURE:\n{failure_response}'
        explanations[f_correction.index] = ''
                
    num_overlapping_groups = len(overlapping_groups)

    running_index = 0
    tot_num_group_corrections = sum(map(lambda g: len(g), overlapping_groups))
    
    for i, group_indices in enumerate(overlapping_groups):
        # could maybe make a deep copy of corrections in group in future to not modify original
        group = [key_to_correction[idx] for idx in group_indices]
        
        for j, correction in enumerate(group):
            prompt = correction.asMarkdownPrompt()
            logging.debug(f"\nGROUP PROMPT {correction.index}:\n{prompt}")
            
            response = callLLM(prompt, model, system_prompt, model_temp, model_top_p)
            logging.debug(f"\nGROUP RESPONSE {correction.index}:\n{response}")

            if response is None or not response:
                logging.warning(
                    f"Could not process response for correction {correction.index}: "
                    f"Response from callLLM was None or falsy. Response: {response}\n"
                )
                writeFailure(correction, response)
                running_index += 1
                continue
            
            parsed, status = parseResponse(response, [correction], model)
            
            if status != 0:
                logging.warning(
                    f"Could not process correction {correction.index} in group {group_indices}: "
                    f"parseResponse returned failure status"
                )
                writeFailure(correction, response)
                running_index += 1
                continue

            # if len(parsed) != 1:
            #     warning_text = f"Could not process correction {correction.index} in group {group_indices}: "
            #     warning_text += f"Model returned {len(parsed)} codeblocks, not 1."
            #     logging.warning(warning_text)
            #     # updated_snippets[correction.index] = correction.latex_snippet                
            #     explanations[correction.index] = warning_text
            #     running_index += 1
            #     continue

            parsed_response = parsed[0]
            language = parsed_response['language']
            
            if language not in {'latex', 'tex'}:
                logging.warning(
                    f"Could not process correction {correction.index} in group {group_indices}: "
                    f"Response code block language was '{language}', not latex!"
                )
                writeFailure(correction, parsed_response)
                running_index += 1
                continue

            updated_snippets[correction.index] = parsed_response['code']
            explanations[correction.index] = parsed_response['explanation']

            logging.info(f"Processed overlapping correction {running_index:3d}/{tot_num_group_corrections-1:3d}")            
            running_index += 1

def writeBatchPrompt(chunk: list[Correction]) -> str:
    """Create prompt for multiple standalone corrections."""
    if len(chunk) == 0:
        return ''
    if len(chunk) == 1:
        return chunk[0].asMarkdownPrompt()
    
    prompt = ''
    for i, correction in enumerate(chunk):
        prompt += f'# Correction #{i+1}:\n{correction.asMarkdownPrompt()}\n\n'
    return prompt

def processCorrections(*args, **kwargs):
    """
    *args are the annotated pdf file name followed by the LaTeX file name
    **kwargs are for now chunksize and model. Will add further options later
    """
    
    annot_filename, tex_filename = args
    
    chunksize = kwargs.get('chunksize', 1)
    model = kwargs.get('model', 'echo')
    model_temp = kwargs.get('temp', 0.1)
    model_top_p = kwargs.get('top_p', 0.9)
    
    system_prompt = kwargs.get('sysprompt', '')
    (corrections, overlapping_keys) = kwargs.get('corrections', (None, None))

    if corrections is None:
        corrections, overlapping_keys = getCorrections(*args, update_overlap_corr=False) # returns list[Correction]

    logging.debug(f"overlapping keys are: {overlapping_keys}")
        
    key_to_correction = {corr.index: corr for corr in corrections}

    ## chunk corrections
    standalone_keys = [corridx for corridx in key_to_correction if corridx not in {idx for group in overlapping_keys for idx in group}]    
    chunks = getChunks(key_to_correction, standalone_keys, chunksize)

    ## prompt model with chunks
    updated_snippets = {}
    explanations = {}

    logging.info(f"QUERYING {model}...")
    start_time = time.time()    

    processStandaloneChunks(chunks['standalone'], model, updated_snippets, explanations, system_prompt, model_temp, model_top_p)
    processOverlappingGroups(overlapping_keys, key_to_correction, model, updated_snippets, explanations, system_prompt, model_temp, model_top_p)

    logging.info(f"DONE QUEREYING {model}. Total elapsed time: {(time.time() - start_time)/60:.2f} minutes")

    ## TODO: update the source file
    
    return updated_snippets, explanations, standalone_keys, overlapping_keys
    
    
if __name__ == '__main__':
    ## definitely a mess
    default_model = 'gemini-3-flash-preview'
    default_chunksize = 1
    default_system_prompt = 'syst_prompt.md'
    default_temp = 0.025  # low temperature ideal for precise, non-novel and non-creative outputs
    default_topp = 0.8 # top_p = p \in [0, 1] means bottom 1-p% likely tokens ignored

    parser = argparse.ArgumentParser()
    parser.add_argument('annotated_PDF_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-p", "--load-pickle", action="store_true", help='load pickle file of corrections if available')
    parser.add_argument("-m", "--model", type=str, help=f"specify the LLM model; default: {default_model}")
    parser.add_argument("-c", "--chunksize", type=int, help=f"specify chunk size for standalone snippets; default: {default_chunksize}")        
    parser.add_argument("-sp", "--system-prompt", type=str, help=f"filename of text containing system prompt; default: {default_system_prompt}")
    parser.add_argument("-lpo", "--load-previous-output", action="store_true", help="Do not query the model and load the updated_snippets and explanations from most recent pickle file if it exists")
    parser.add_argument("--temp", type=float, help=f"model temperature; default: {default_temp}")
    parser.add_argument("--top-p", type=float, help=f"model top_p; default: {default_topp}")
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    latex_filename = Path(args.latex_filename)

    tmp_pickle_dir = Path("tmp_pickle")
    Path.mkdir(tmp_pickle_dir, exist_ok = True)
    corr_file = tmp_pickle_dir / Path(f"{latex_filename.stem}_corrections.pkl")

    sp_file = args.system_prompt

    if sp_file and Path(sp_file).exists():
        with open(sp_file, 'r') as f:
            _system_prompt = f.read()
        logging.info(f"Read system prompt from '{sp_file}'")
    elif Path(default_system_prompt).exists():
        with open(default_system_prompt, 'r') as f:
            _system_prompt = f.read()
        logging.info(f"Read system prompt from '{default_system_prompt}'")
    else:
        logging.warning(f"NO SYSTEM PROMPT SUPPLIED; continuing with simple default system prompt")
        _system_prompt = "You are a LaTeX compositor. Your role is to carry out changes to source LaTeX based on instructions. You are NOT responsible for identifying any errors in the text---you are only to make the changes instructed. You must respond with just a single LaTeX markdown codeblock with the entire original snipet edited as instructed. Do not add or remove any text from the supplied snippet other than what is specifically asked. Do not add elipses or reflow text or change whitespace. For whatever piece of the snippet you do change, do not insert any non-ASCII characters. If you are at all uncertain for how to change the document, echo back the LaTeX snippet as it was given to you."

    if not (corr_file.exists() and args.load_pickle):
        (corrections, overlapping_keys) = getCorrections(args.annotated_PDF_filename, args.latex_filename, update_overlap_corr=False)
        with open(corr_file, 'wb') as f:
            pickle.dump((corrections, overlapping_keys), f)
    else:
        with open(corr_file, 'rb') as f:
            (corrections, overlapping_keys) = pickle.load(f)

    if args.model is not None:
        model = args.model
    else:
        model = default_model

    if args.chunksize is not None:
        _chunksize = args.chunksize
    else:
        _chunksize = default_chunksize

    if args.temp is not None:
        temp = args.temp
    else:
        temp = default_temp

    if args.top_p is not None:
        top_p = args.top_p
    else:
        top_p = default_topp

    temp_as_str = 'temp' + re.sub(r'\.', '-', str(temp))
    top_p_as_str = 'topp' + re.sub(r'\.', '-', str(top_p))
            
    writeListOfPrompts(corrections, args.latex_filename)

    identifying_run_str = f'{model}_{temp_as_str}_{top_p_as_str}'
    updated_snippets_pickle_file = tmp_pickle_dir / Path(f'updated_snippets_and_explanations_{Path(args.annotated_PDF_filename).stem}_{identifying_run_str}.pkl')

    if args.load_previous_output:
        logging.info(f"Loading pickle file {updated_snippets_pickle_file}...")
        with open(updated_snippets_pickle_file, 'rb') as f:
            (updated_snippets, explanations, standalone_keys, group_keys) = pickle.load(f)
        logging.info("Done.")
    else:
        updated_snippets, explanations, standalone_keys, group_keys = processCorrections(
            args.annotated_PDF_filename,
            args.latex_filename,
            corrections=(corrections, overlapping_keys),
            system_prompt=_system_prompt,
            chunksize=_chunksize,
            model=model,
            temp=temp,
            top_p=top_p,
        )

        logging.info(f"Dumping updated snippets and explanations to {updated_snippets_pickle_file}...")
        
        with open(updated_snippets_pickle_file, "wb") as f:
            pickle.dump((updated_snippets, explanations, standalone_keys, group_keys), f)
        logging.info("Done.")

    logging.info("Writing prompts and responses to .md file...")
    writePromptsWithResponses(
        corrections,
        updated_snippets,
        explanations,
        args.latex_filename,
        identifying_run_str,
        _system_prompt,
        standalone_keys,
        group_keys
    )
    logging.info("Done.")
