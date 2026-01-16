import logging
import argparse
import pymupdf
import json
import time
import pickle
import re

from texpdfedits.extract import getEdits
from texpdfedits.segmentsource import segment, sourceAsString

import google.genai as genai

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path


BOXES_ORDER_THRESHOLD_BUFF = 6
"""
when a rectangle doesn't intersect any word boxes we look for the word boxes before and after the rectangle.
If the inputted rectangle has y0 Y and a word box has y0 Y+.01 it is still recognized as coming "after" the inputted
rectangle when very often it could actually appear earlier in the line. To mitigate this, we extend the threshold a little, so
for a word box to be considered "after" (or before) its y0 needs to be greater than the inputted rectangle's y0 plus this buffer
(and less than the inputted buffer's y0 minus this buffer). This is used in determining boxes_before and boxes_after.
We may need to eventually find a new and better way to determine word box order if we continue to encounter issues.
"""

def rectangleToLatex(
        pageno: int,
        in_rectangle: pymupdf.Rect,
        document_word_boxes: dict[int, dict[str, pymupdf.Rect]],
        mark_positions: dict[str, tuple[int, int]],
        tex_str: str
) -> str | None:
    r"""
    Args:
        pageno: Zero-indexed page number
        in_rectangle: Rectangle on the page (pymupdf format)
        document_word_boxes: Dictionary from getWordBoxes()
        mark_positions: dictionary mapping mark_id -> (start, end) positions in tex_str 
        tex_str: original unmarked LaTeX source

    Returns: The (unmarked) source LaTeX snippet which "contains" the rectangle.

    Given some rectangle, we find the closest word box before and after that rectangle
    then return all of the LaTeX between (and including) those two word boxes.

    If the inputted rectangle intersects at least one word box, finding the preceding and following word boxes is simple:
    out of the word boxes that intersect, find the one with the smallest id and the one with the largest id, then just use the first
    existing id (because not all \markbox commands make it to the document_work_boxes dictionary) before the smallest and the next existing id
    after the largest.

    If the inputted rectangle doesn't intersect any document_word_boxes, then the "before" box is the one with the largest id whose topline (y0) is less than
    (higher up the page) than the topline of the inputted box, and the "after" box is the one with the smallest id whose topline is greater than the inputted box.
    """

    page_word_boxes = document_word_boxes[pageno]
    intersecting_word_boxes = {k: rect for k, rect in page_word_boxes.items() if in_rectangle.intersects(rect)} 

    def getNumericComponent(k: str) -> int:
        return int(''.join(filter(str.isdigit, k)))

    def getPrevKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)        
        prev_keys = [k for k in all_keys if getNumericComponent(k) < target_num]
        return max(prev_keys, key = getNumericComponent) if prev_keys else None

    def getNextKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)
        next_keys = [k for k in all_keys if getNumericComponent(k) > target_num]
        return min(next_keys, key = getNumericComponent) if next_keys else None        

    all_keys = [k for page_boxes in document_word_boxes.values() for k in page_boxes.keys()]
    
    if intersecting_word_boxes:
        logging.debug(f"Rectangle {in_rectangle} on page {pageno} did intersect word boxes")
        min_key = min(intersecting_word_boxes.keys(), key = getNumericComponent)
        max_key = max(intersecting_word_boxes.keys(), key = getNumericComponent)
        before_key = getPrevKey(min_key, all_keys)
        after_key = getNextKey(max_key, all_keys)
    else:
        # the boxes before and after are on the same page
        logging.debug(f"No word box was intersected by rectangle {in_rectangle} on page {pageno}")
        boxes_before = {k: rect for k, rect in page_word_boxes.items() if rect.y0 < in_rectangle.y0 - BOXES_ORDER_THRESHOLD_BUFF}
        boxes_after = {k: rect for k, rect in page_word_boxes.items() if rect.y0 > in_rectangle.y0 + BOXES_ORDER_THRESHOLD_BUFF}

        # logging.debug(f"boxes before: {boxes_before}\n\n")
        # logging.debug(f"boxes after: {boxes_after}\n\n")        
        
        before_key = max(boxes_before.keys(), key=getNumericComponent) if boxes_before else None
        after_key = min(boxes_after.keys(), key=getNumericComponent) if boxes_after else None

    if before_key is None:
        before_key = max(document_word_boxes[pageno-1].keys(), key=getNumericComponent) if pageno-1 in document_word_boxes else None

    if after_key is None:
        after_key = min(document_word_boxes[pageno+1].keys(), key=getNumericComponent) if pageno+1 in document_word_boxes else None

    if before_key is None or after_key is None:
        # This should only happen if the rectangle is before or after ALL marked boxes in the document.
        # This is a situation where we should check metadata, but I'll have to think more about that in general
        logging.warning(f"Cannot extract LaTeX: Rectangle outside marked boxes (before_key={before_key}, after_key={after_key})")
        return None, None

    logging.debug(f"Before key is {before_key} and after key is {after_key}")

    # NEW
    # the mark_positions.keys() should be a superset of the document_word_boxes.keys()
    # document_word_boxes should only not contain the keys whose individual word boxes were rejected---mark_positions has all of them
    # we could simplify what is above to just take the adjacent key by numeric component (checking if its just the number or preceded by 'm')
    # and this would actually slightly enhance the extraction---it would on average make the snippet smaller, including only what is needed
    # excluding, obviously, the cases where what needs to be edited is very far from the original inputted rectangle (like far down in an enumerate list)
    start_pos = mark_positions[before_key][0]
    end_pos = mark_positions[after_key][1]

    if start_pos > end_pos:
        # this shouldn't happen thanks to BOXES_ORDER_THRESHOLD_BUFF
        logging.warning(f"Cannot extract LaTeX: start_pos = '{start_pos}' > '{end_pos}' = end_pos")
        return None, None
    
    return tex_str[start_pos:end_pos], (start_pos, end_pos)

def markdownReplies(replies: list[str]):
    if not replies:
        return ''
    output = '\n\n## Replies '
    for i in range(len(replies)):
        output += f'\n\n### Reply {i+1}\n```text\n{replies[i]}\n```'
    return output

class Correction:
    """
    Includes all the information I could hope to need to produce and debug the
    individual correction prompts. See asMarkdownPrompt for which pieces actually get
    sent to the LLM. There's certainly room for improvement in the terminology I have so far,
    but right now an "edit" is just the information I get from a PDF annotation.
    A "correction" is that information alongside the corresponding latex_snippet which is required
    to carry out the edit. And a prompt is just the text prompted to the LLM.
    
    Attributes:
    index: the zero-indexed correction number
    
    pageno: the page the correction appears on
    
    type: the annotaiton type of the correction, e.g.,
            "Caret", "Strikeout", "Highlight"
    
    messages: the text written in the annotation comment box and
            any replies to it (which are sorted by date)
    
    pdf_selected_text: the text extracted from the PDF.
            HTML-like focus tags denote exactly which text was
            selected by the annotaiton. Granted, this still fails
            for annotations which select multiple lines of text because the
            required bounding box information is missing

    pdf_selection_line_rect: the rectangle used to select the text
            on that page of the PDF.

    pdf_selection_bbs: the rectangles used to partition the text
            extracted from the pdf_selection_line_rect into
            pieces which are and are not inside the HTML-like
            focus tags. See getSelection in extract.py for more on this
    
    latex_snippet: the latex source which corresponds to the pdf_selected_text.
            See segmentsource.py for more on how this was retrieved
    
    snippet_source_positions: the start and end positions of the latex_snippet
            in the original latex_string. That is, the latex_snippet is
            tex_str[start:end] where tex_str is the source LaTeX as a string
    """
    def __init__(
            self,
            _index: int,
            _pageno: int, 
            _type: str,
            _messages: dict[str, str | list[str]],
            _pdf_selected_text: str,
            _pdf_selection_line_rect: pymupdf.Rect,
            _pdf_selection_bbs: list[pymupdf.Rect],
            _latex_snippet: str,
            _snippet_source_positions: tuple[int, int]
    ) -> None:
        """Using underscores in the argument names isn't necessary, but I like setting the distinction"""
        self.index = _index
        self.pageno = _pageno
        self.type = _type
        self.messages = _messages
        self.pdf_selected_text = _pdf_selected_text
        self.pdf_selection_line_rect = _pdf_selection_line_rect
        self.pdf_selection_bbs = _pdf_selection_bbs
        self.latex_snippet = _latex_snippet
        self.snippet_source_positions = _snippet_source_positions

    def __str__ (self): # the model will not be given json, but I think this format is good for debugging
        return json.dumps({
            "index" : self.index,
            "pageno": self.pageno,
            "type": self.type,
            "messages": {
                "comment": self.messages['comment'],
                "responses": self.messages['responses']
            },
            "PDF selected text": self.pdf_selected_text,
            "PDF selection line rectangle": str(self.pdf_selection_line_rect),
            "LaTeX snippet": self.latex_snippet,
            "Snippet source positions": self.snippet_source_positions
        }, indent=4, ensure_ascii=False)

    def __repr__ (self):
        return str(self)

    def asMarkdownPrompt(self):
        replies = markdownReplies(self.messages['responses'])
        return rf"""## Type
{self.type}

## Comment
```text
{self.messages['comment']}
```{replies}

## PDF selected text
```text
{self.pdf_selected_text}
```
  
## LaTeX snippet
```latex
{self.latex_snippet}
```"""
    def updateSnippet(self, new_source_pos: tuple[int], new_snippet: str) -> None:
        self.snippet_source_positions = new_source_pos
        self.latex_snippet = new_snippet

    def snippetToCodeblock(self):
        return f"```latex\n{self.latex_snippet}\n```"

def getCorrections(annot_filename: str, latex_filename: str) -> list[Correction]:
    edits = getEdits(annot_filename)
    num_marks, marked_tex, unmarked_str, mark_positions, document_word_boxes, all_metadata = segment(latex_filename)

    corrections = []
    for i, edit in enumerate(edits):
        progress = f"{i}/{len(edits)-1}"
        pageno = edit.pageno
        if pageno not in document_word_boxes:
            logging.warning(f"Could not create correction {progress}: Page '{pageno}' not in `document_word_boxes` for edit {edit}")
            continue
        
        pdf_selection_line_rect = edit.selection_line_rect
        latex_snippet, snippet_source_positions = rectangleToLatex(
            pageno,
            pdf_selection_line_rect,
            document_word_boxes,
            mark_positions,
            unmarked_str
        )
        
        if latex_snippet is None:
            logging.warning(f"Could not create correction {progress}: no LaTeX snippet for edit {progress}: {edit}")
            continue

        corrections.append(
            Correction(
                i, pageno, edit.type, edit.message, edit.selection,
                pdf_selection_line_rect, edit.selection_bbs, latex_snippet,
                snippet_source_positions
            )
        )
        logging.info(f"Created correction {progress}")

    logging.info(f"Produced {len(corrections)} corrections from {len(edits)} edit annotations.")                

    return corrections

def toCodeblock(string: str, language: str = 'latex'):
        return f"```{language}\n{string}\n```"        

def groupOverlaps(keyed_start_ends: dict[int, tuple[int]]) -> list[list[int]]:
    """
    I have a list of dictionaries where each dictionary has some key and its value is a tuple with a start and end value, a span
    I want to group together all keys whose start and end values overlap. If there are no such keys then I should return an
    empty list. The keys just happen to be ints in this case, but the ints don't have anything to do with the ordering
    """
    if not keyed_start_ends:
        return []
    
    # sort by starts    
    keys = list(sorted([k for k in keyed_start_ends], key = lambda k: keyed_start_ends[k][0])) 

    groups = []
    current_group = [keys[0]]
    curr_group_end = keyed_start_ends[keys[0]][1]
    for i, k in enumerate(keys):
        if i == 0:
            continue
        start, end = keyed_start_ends[k][0], keyed_start_ends[k][1]
        if start < curr_group_end:
            current_group.append(k)
            curr_group_end = max(curr_group_end, end)
        else:
            if len(current_group) >= 2:
                groups.append(current_group)
            current_group = [k]
            curr_group_end = end
    if len(current_group) >= 2:
        groups.append(current_group)
    return groups

def groupOverlappingCorrections(corrections: list[Correction], tex_filename: str, key_to_correction: dict[int, Correction]) -> tuple[list[list[int]], list[str]]:
    if not corrections:
        return [], []
    tex_str = sourceAsString(tex_filename)
    keyed_start_ends = {corr.index: corr.snippet_source_positions for corr in corrections}
    groups = groupOverlaps(keyed_start_ends)

    snippets = []
    for group in groups:
        spans_in_group = [keyed_start_ends[k] for k in group]
        min_start = min(spans_in_group, key = lambda span: span[0])[0]
        max_end = max(spans_in_group, key = lambda span: span[1])[1]
        containing_snippet = tex_str[min_start:max_end]
        snippets.append(containing_snippet)
        for k in group:
            corr = key_to_correction[k]
            if not corr.latex_snippet in containing_snippet:
                logging.error(
                     "Failed to create overlapping groups: "
                    f"a snippet \n{corr.snippetToCodeblock()}\n was not in its spanning snippet \n{toCodeblock(containing_snippet)}\n"
                )
                sys.exit(1)
            corr.updateSnippet((min_start, max_end), containing_snippet)
    
    return groups, snippets # will probably not return snippets in future: unnecessary

def writeListOfPrompts(corrections: list[Correction], tex_filename: str) -> None:
    prompt_dir = Path('markdown_prompts')
    Path.mkdir(prompt_dir, exist_ok=True)
    
    savefile = f"{prompt_dir / Path(tex_filename).stem}_list_of_prompts.md"

    with open(savefile, 'w') as f:
        f.write('\n\n---\n\n'.join([f"#{corr.index}\n\n" + corr.asMarkdownPrompt() for corr in corrections if corr is not None]))
    logging.info(f"The list of prompts have been written to {savefile}.")

def writePromptsWithResponses(corrections: list[Correction], updated_snippets, explanations, tex_filename, model):
    prompt_dir = Path('markdown_prompts')
    Path.mkdir(prompt_dir, exist_ok=True)
    
    savefile = f"{prompt_dir / Path(tex_filename).stem}_responses_{model}.md"

    with open(savefile, 'w') as f:
        f.write(
            '\n\n---\n\n'.join(
                [f"#{corr.index}\n\n" + corr.asMarkdownPrompt() + f"\n## Response\n```latex\n{updated_snippets[corr.index]}\n```\n### Explanation\n{explanations[corr.index]}"
                 for corr in corrections if corr is not None]
            )
        )
    logging.info(f"The prompts with their responses have been written to {savefile}.")    

def callGemini(prompt: str, model: str, system_prompt: str = None, history: list = None):
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
    
    # Build message history
    messages = []
    if history:
        for exchange in history:
            messages.append({'role': 'user', 'parts': [{'text': exchange['prompt']}]})
            messages.append({'role': 'model', 'parts': [{'text': exchange['response']}]})
    
    # Add current prompt
    messages.append({'role': 'user', 'parts': [{'text': prompt}]})
    
    # Build config
    config = {}
    if system_prompt:
        config['system_instruction'] = system_prompt
    
    # Make API call
    response = client.models.generate_content(
        model=model,
        contents=messages,
        config=config if config else None
    )
    
    return response.text

def callClaude(prompt: str, model: str, system_prompt: str = None, history: list = None):
    """Call Anthropic's Claude API (to be implemented)"""
    # TODO: implement with anthropic package
    return prompt

def callEcho(prompt: str, model: str, system_prompt: str = None, history: list = None):
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

def callLLM(prompt: str, model: str, system_prompt: str = None, history: list = None):
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
        raise ValueError(f"Unsupported model: {model}")

    logging.info(f"Calling {model}...")
    start = time.time()    
    response = llm(prompt, model, system_prompt, history)
    logging.info(f"Call to {model} completed in {time.time() - start:.2f}s")    
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
    
    for match in matches:
        codeblocks.append({
            'language': match.group(1),
            'code': match.group(2),
            'start': match.start(),
            'end': match.end()
        })
    
    if len(codeblocks) != len(corrections):
        logging.warning(
            f"Response from {model_name} returned {len(codeblocks)} codeblocks "
            f"but expected {len(corrections)} corrections"
        )
    
    languages = {block['language'] for block in codeblocks}
    if not languages.issubset({'latex', 'tex'}):
        logging.warning(
            f"Codeblock languages for corrections {[c.index for c in corrections]} "
            f"contained unexpected languages: {languages - {'latex', 'tex'}}"
        )
    
    # Extract explanations after codeblocks
    for i, block in enumerate(codeblocks):
        start = block['end']
        end = codeblocks[i+1]['start'] if i < len(codeblocks)-1 else len(response_str)
        block['explanation'] = response_str[start:end].strip()
    
    return codeblocks

def processStandaloneChunks(
        chunks: list[list[Correction]],
        model: str,
        updated_snippets: dict[int, str],
        explanations: dict[int, str],
        _system_prompt: str | None = None
) -> None:
    """Process standalone corrections in batches."""
    num_chunks = len(chunks)-1
    for i, chunk in enumerate(chunks):
        prompt = writeBatchPrompt(chunk)
        try:
            response = callLLM(prompt, model, system_prompt = _system_prompt)
            print(response)
        except Exception as e:
            logging.error(f"You got an error from calling the LLM: {e}\nQuitting with the current updated_snippets variable")
            return 
        parsed = parseResponse(response, chunk, model)
        
        if not parsed:
            logging.error(f"No codeblocks found in response for corrections {[c.index for c in chunk]}")
            continue
        
        # Update snippets with parsed codeblocks
        for correction, block in zip(chunk, parsed):
            updated_snippets[correction.index] = block['code']
            explanations[correction.index] = block['explanation']
        logging.info(f"Processed standalone snippets {i:3d}/{num_chunks:3d}")

def processOverlappingGroups(
    overlapping_groups: list[list[int]], 
    key_to_correction: dict[int, Correction],
    model: str, 
    updated_snippets: dict[int, str],
    explanations: dict[int, str],
    _system_prompt: str | None = None
):
    """Process overlapping corrections sequentially with chat history."""
    MAX_HISTORY = 10
    num_overlapping_groups = len(overlapping_groups)-1
    for i, group_indices in enumerate(overlapping_groups):
        group = [key_to_correction[i] for i in group_indices]
        chat_history = []
        
        for correction in group:
            prompt = writeSinglePrompt(correction)
            response = callLLM(prompt, model, system_prompt = _system_prompt, history=chat_history)
            parsed = parseResponse(response, [correction], model)
            
            if not parsed:
                logging.error(f"No codeblock found in response for correction {correction.index}")
                # Still add to chat history so conversation continues
                chat_history.append({'prompt': prompt, 'response': response})
                if len(chat_history) > MAX_HISTORY:
                    chat_history = chat_history[-MAX_HISTORY:]
                continue
            
            block = parsed[0]
            # Update all corrections in this group with the new snippet
            for c in group:
                updated_snippets[c.index] = block['code']
            explanations[correction.index] = block['explanation']
            
            # Maintain chat history with sliding window
            chat_history.append({'prompt': prompt, 'response': response})
            if len(chat_history) > MAX_HISTORY:
                chat_history = chat_history[-MAX_HISTORY:]
        logging.info(f"Processed overlapping snippets {i:3d}/{num_overlapping_groups:3d}")

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

def writeSinglePrompt(correction: Correction) -> str:
    """Create prompt for a single correction."""
    return correction.asMarkdownPrompt()

def processCorrections(*args, **kwargs):
    """
    *args are the annotated pdf file name followed by the LaTeX file name
    **kwargs are for now chunksize and model. Will add further options later
    """
    annot_filename, tex_filename = args
    
    chunksize = kwargs.get('chunksize', 1)
    model = kwargs.get('model', 'echo')
    system_prompt = kwargs.get('sysprompt', None)
    corrections = kwargs.get('corrections', None)

    if corrections is None:
        corrections = getCorrections(*args) # returns list[Correction]
        
    key_to_correction = {corr.index: corr for corr in corrections}

    # modifies corrections so that all snippets in a group are the same---they span the group
    overlapping_corrections, _ = groupOverlappingCorrections(corrections, tex_filename, key_to_correction) # returns tuple[list[list[int]], list[str]], second argument currently unused.

    ## chunk corrections
    standalone_keys = [corridx for corridx in key_to_correction if corridx not in {idx for group in overlapping_corrections for idx in group}]    
    chunks = getChunks(key_to_correction, standalone_keys, chunksize)

    ## prompt model with chunks
    updated_snippets = {}
    explanations = {}

    processStandaloneChunks(chunks['standalone'], model, updated_snippets, explanations)
    processOverlappingGroups(overlapping_corrections, key_to_correction, model, updated_snippets, explanations)

    ## apply updates to source file
    # TODO: implement later
    
    return updated_snippets, explanations
    
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annot_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-p", "--load-pickle", action="store_true", help='load pickle file of corrections if available')
    parser.add_argument("-m", "--model", type=str, help="specify the LLM model")
    parser.add_argument("-c", "--chunksize", type=int, help="specify chunk size for standalone snippets")        
    parser.add_argument("-sp", "--system-prompt", type=str, help="filename of text containing system prompt")
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    Path.mkdir(Path("tmp_prompt"), exist_ok = True)
    corr_file = Path("tmp_prompt/corrections.pkl")

    sp_file = args.system_prompt

    if sp_file and Path(sp_file).exists():
        with open(sp_file, 'r') as f:
            _system_prompt = f.read()
        logging.info(f"Read system prompt from {sp_file}")
    else:
        _system_prompt = None

    if not (corr_file.exists() and args.load_pickle):
        corrections = getCorrections(args.annot_filename, args.latex_filename)

        with open(corr_file, 'wb') as f:
            pickle.dump(corrections, f)
    else:
        with open(corr_file, 'rb') as f:
            corrections = pickle.load(f)

    if args.model:
        model = args.model
    else:
        model = 'echo' # for now

    if args.chunksize:
        _chunksize = args.chunksize
    else:
        _chunksize = 1
            
    writeListOfPrompts(corrections, args.latex_filename)

    updated_snippets, explanations = processCorrections(
        args.annot_filename,
        args.latex_filename,
        corrections=corrections,
        system_prompt = _system_prompt,
        chunksize = _chunksize,
        model=model
    )

    writePromptsWithResponses(corrections, updated_snippets, explanations, args.latex_filename, model)

    # for correction in corrections:
    #     if corr.index in groupKs:
    #         logging.info(f"{correction.index}: \n{correction.snippetToCodeblock()}\n")

    # o_groups, o_snippets = groupOverlappingCorrections(corrections, args.latex_filename)

    # groupKs = [k for group in o_groups for k in group]    

    # for corr in corrections:
    #     if corr.index in groupKs:
    #         logging.info(f"{corr.index}: \n{corr.snippetToCodeblock()}\n")

    # print(sum([len(group) for group in o_groups]))

    # assert len(o_groups) == len(o_snippets)
    
    # for i in range(len(o_groups)):
    #     logging.info(f"This group is made up of {len(o_groups[i])} corrections")
    #     logging.info(f"Corrections {o_groups[i]} overlap")
    #     logging.info(f"Here's the spanning snippet for these corrections:\n```latex\n{o_snippets[i]}\n```\n")    
