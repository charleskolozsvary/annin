import logging
import argparse
import pymupdf
import json
import time
import pickle
import re

from texpdfedits.extract import getEdits
from texpdfedits.segmentsource import segment, sourceAsString, numericComponent, alphaComponent, markIdToCountInfo

import google.genai as genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

THINKING_GEMINI_MODELS = {'gemini-3-flash-preview', 'gemini-3-pro-preview'}


BOXES_ORDER_THRESHOLD_BUFF = 6
"""
When a rectangle doesn't intersect any word boxes, we look for the word boxes before and after the rectangle.
If the inputted rectangle has y0 Y and a word box has y0 Y+.01 it would by default be recognized as coming "after" the inputted
rectangle when very often it could actually appear earlier in the line. To mitigate this, we extend the threshold a little, so
for a word box to be considered "after" (or before), its y0 needs to be greater than the inputted rectangle's y0 plus this buffer
(and less than the inputted buffer's y0 minus this buffer). This is used in determining boxes_before and boxes_after.
We may need to eventually find a new and better way to determine word box order if we continue to encounter issues.
"""

def categorizeMarkIDs(mark_ids: list[str]) -> int:
    """
    if the marks are all structured the same level of nesting, e.g., all boxes within the same footnote, return 'compatible'
    if the marks are all the same level of nesting except for the head count, e.g., all boxes within thanks but includes boxes in two different thanks,
    return 'maybe compatible'
    if the marks are not the same at all, e.g., one is in just in the document and another is in a footnote (inside the document), return 'incompatible'
    """
    sets_of_counter_info = {}
    count_info_lens = set()
    for mark_id in mark_ids:
        count_info = markIdToCountInfo(mark_id)
        count_info_lens.add(len(count_info))
        for i, name_head_stem in enumerate(count_info):
            if i not in sets_of_counter_info:
                sets_of_counter_info[i] = {'names': set(), 'heads': set(), 'stems': set()}
            sets_of_counter_info[i]['names'].add(name_head_stem['name'])
            sets_of_counter_info[i]['heads'].add(name_head_stem['head'])
            sets_of_counter_info[i]['stems'].add(name_head_stem['stem'])
            
    if len(count_info_lens) != 1:
        return 'incompatible'

    max_counter_idx = max(sets_of_counter_info.keys())
    # walk through lengths piece by piece
    for index, set_of_c_info in sets_of_counter_info.items():
        if len(set_of_c_info['names']) != 1:
            return 'incompatible'
        if len(set_of_c_info['heads']) != 1:
            if index < max_counter_idx:
                return 'incompatible'
            else:
                return 'maybe same'
        if len(set_of_c_info['stems']) != 1 and index < max_counter_idx:
            return 'incompatible'
        
    return 'compatible'

def isOnlyDocumentID(mark_id: str) -> bool:
    count_info = markIdToCountInfo(mark_id)
    return len(count_info) == 1 and count_info[0]['name'] == 'DOCUMENT'

def getTerminalStem(mark_id: str) -> int:
    count_info = markIdToCountInfo(mark_id)
    return count_info[-1]['stem']

def infoToMarkID(count_info: list[dict[str, str]]):
    return ','.join([f"{piece['name']}{piece['head']};{piece['stem']}" for piece in count_info])
                
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

    If the inputted rectangle intersects at least one word box -> 
    We handle three possibilities
         1. the word boxes are "compatible" -> we use the boxes within that level, first preceding, next following
         2. the word boxes are "maybe compatible" -> we have partitions of ids by head value
                     we check the pairs last stem of head i versus first stem of head i + 1
                     and see if their distance in source position (in characters) is more than some threshold
                     if all of these distances are less than a threshold, then we give all the source between the box before the earliest
                     intersected head and the box after the last intersected head

                     if the distances are not all within that threshold then we don't extract the source
          3. the word boxes are "incompatible" -> we don't extract any source

    if the inputted rectangle does not intersect any boxes -> 
    we simply use the boxes only numbered within the document and use the range of the first document box before the rectangle through (and including) the
    first document box after the rectangle
    """
    if pageno not in document_word_boxes:
        logging.warning(f"Cannot extract LaTeX: pageno {pageno} not in document_word_boxes")
        return None, None

    def getAdjacentKey(mark_id: str, plus_minus: int, page: int) -> str:
        """ return the previous key based on the terminal stem value. So document0;0,caption0;1,footnote5;10 should return
        document0;0,caption0;1,footnote5;9
        """
        count_info = markIdToCountInfo(mark_id)
        stem_val = int(count_info[-1]['stem']) 
        count_info[-1]['stem'] = str(stem_val + plus_minus)
        adjacentMark = infoToMarkID(count_info) 
        
        if adjacentMark in document_word_boxes[page]:
            return adjacentMark
        elif page + plus_minus in document_word_boxes and adjacentMark in document_word_boxes[page + plus_minus]:
            return adjacentMark
        else:
            return None

    def checkMaybeCompatible(mark_ids: list[str]) -> tuple[str, str]:
        """ mark_ids are maybe compatible, so their counters other than the last are known to be all equal
        
        In word's the intention on this function is to look at each group of counters which have the same head value and compare the last in that group to the
        first in the next group with the same head value (typically it will have head value of just one more, but we don't require this)
        
        If the number of characters between the end and the start for each of these pairs is less than some arbitrary threshold, say 100 characters,
        Then we'll return the key of the first id in the lowest head count group and the key of the last id in the largest head count group as our
        start_ and end_ extraction keys.
        """
        count_infos = [markIdToCountInfo(m_id) for m_id in mark_ids]
        head_partitions = {}
        for c_info in count_infos:
            head_count = c_info[-1]['head'] # [-1] because we already know that all preceding count information is the same
            if head_count in head_partitions:
                head_partitions[head_count].append(c_info[-1])
            else:
                head_partitions[head_count] = [c_info[-1]]
        sorted_head_counts = list(sorted(head_partitions.keys()))

        def returnCinfoStem(single_c_info: dict[str, str | int]):
            return single_c_info['stem']
        
        for i in range(len(sorted_head_counts)-1):
            curr_hcount = sorted_head_counts[i]
            next_hcount = sorted_head_counts[i+1]
            last_curr = infoToMarkID(max(head_partitions[curr_hcount], key=returnCinfoStem))
            first_next = infoToMarkID(min(head_partitions[next_hcount], key=returnCinfoStem))

            start_pos = mark_positions[last_curr][1]
            end_pos = mark_positions[first_next][0]
            if not (start_pos < end_pos and end_pos - start_pos < MAYBE_COMPATIBLE_POSITION_DIFFERENCE_THRESH):
                logging.debug(
                    f"Mark IDs are not compatible for source extraction:\n"
                    f"markId {last_curr} had end {start_pos} and id {first_next} had start {end_pos}"
                )
                return None, None

        start_key = infoToMarkID(min(head_partitions[sorted_head_counts[0]], key=returnCinfoStem))
        end_key = infoToMarkID(max(head_partitions[sorted_head_counts[-1]], key=returnCinfoStem))
        return start_key, end_key

    page_word_boxes = document_word_boxes[pageno]
    intersecting_word_boxes = {k: rect for k, rect in page_word_boxes.items() if in_rectangle.intersects(rect)}

    if intersecting_word_boxes:
        logging.debug(f"Rectangle {in_rectangle} on page {pageno} intersected {len(intersecting_word_boxes)} word boxes")
        mark_ids = list(intersecting_word_boxes.keys())
        category = categorizeMarkIDs(mark_ids)
        if category == 'compatible':
            min_key = min(mark_ids, key=getTerminalStem)
            max_key = max(mark_ids, key=getTerminalStem)
            before_min = getAdjacentKey(min_key, -1, pageno)
            after_max = getAdjacentKey(max_key, 1, pageno)
            
            start_key = before_min if before_min is not None else min_key
            end_key = after_max if after_max is not None else max_key
        elif category == 'maybe compatible':
            start_key, end_key = checkMaybeCompatible(mark_ids)
        else:
            logging.warning(f"Cannot extract LaTeX: intersected mark IDs were not compatible.")
            logging.debug(f"Incompatible mark IDs were\n{mark_ids}")
            return None, None
    else:
        logging.debug(f"Rectangle {in_rectangle} did not intersect any word box on page {pageno}")
        boxes_before = {k: rect for k, rect in page_word_boxes.items() if rect.y0 < in_rectangle.y0 - BOXES_ORDER_THRESHOLD_BUFF and isOnlyDocumentID(k)}
        boxes_after = {k: rect for k, rect in page_word_boxes.items() if rect.y0 > in_rectangle.y0 + BOXES_ORDER_THRESHOLD_BUFF and isOnlyDocumentID(k)}

        # logging.debug(f"boxes before: {boxes_before}\n\n")
        # logging.debug(f"boxes after: {boxes_after}\n\n")        
        
        start_key = max(boxes_before.keys(), key=getTerminalStem) if boxes_before else None
        end_key = min(boxes_after.keys(), key=getTerminalStem) if boxes_after else None
        
        if start_key is None:
            start_key = max(filter(isOnlyDocumentID, document_word_boxes[pageno - 1].keys()), key=getTerminalStem) if pageno-1 in document_word_boxes else None

        if end_key is None:
            end_key = min(filter(isOnlyDocumentID, document_word_boxes[pageno + 1].keys()), key=getTerminalStem) if pageno+1 in document_word_boxes else None

    if start_key is None or end_key is None:
        # This should only happen if
        # (1) the rectangle doesn't intersect any boxes and it comes before or after all of them
        # (2) the rectangle intersects boxes which have incompatible ids
        # (2.1) the rectangle intersects boxes which are maybe compatible that are actually deemed incompatible by checkMaybeCompatible
        logging.warning(f"Cannot extract LaTeX: Rectangle outside marked boxes (start_key={start_key}, end_key={end_key})")
        return None, None

    logging.debug(f"Before key is {start_key} and after key is {end_key}")

    start_pos = mark_positions[start_key][0]
    end_pos = mark_positions[end_key][1]

    if start_pos > end_pos:
        # this shouldn't happen thanks to BOXES_ORDER_THRESHOLD_BUFF
        logging.warning(f"Cannot extract LaTeX: start_pos = '{start_pos}' > '{end_pos}' = end_pos")
        return None, None
    
    return tex_str[start_pos:end_pos], (start_pos, end_pos)

def markdownReplies(replies: list[str]):
    if not replies:
        return ''
    output = '\n\n### Replies '
    for i in range(len(replies)):
        output += f'\n\n#### Reply {i+1}\n```text\n{replies[i]}\n```'
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

    pdf_annot_rect: the rectangle used to select the text
            on that page of the PDF.

    pdf_selection_bbs: the rectangles used to partition the text
            extracted from the pdf_annot_rect into
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
            _pdf_annot_rect: pymupdf.Rect,
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
        self.pdf_annot_rect = _pdf_annot_rect
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
            "PDF selection line rectangle": str(self.pdf_annot_rect),
            "LaTeX snippet": self.latex_snippet,
            "Snippet source positions": self.snippet_source_positions
        }, indent=4, ensure_ascii=False)

    def __repr__ (self):
        return str(self)

    def asMarkdownPrompt(self):
        replies = markdownReplies(self.messages['responses'])
        return rf"""### Annotation: {self.type}

### Comment
```text
{self.messages['comment']}
```{replies}

### PDF selected text
```text
{self.pdf_selected_text}
```
  
### LaTeX snippet
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
    mark_positions, document_word_boxes = segment(latex_filename)
    tex_str = sourceAsString(Path(latex_filename))

    corrections = []
    for i, edit in enumerate(edits):
        progress = f"{i}/{len(edits)-1}"
        pageno = edit.pageno
        if pageno not in document_word_boxes:
            logging.warning(f"Could not create correction {progress}: Page '{pageno}' not in `document_word_boxes` for edit {edit}")
            continue
        
        pdf_annot_rect = edit.annot_rect
        latex_snippet, snippet_source_positions = rectangleToLatex(
            pageno,
            pdf_annot_rect,
            document_word_boxes,
            mark_positions,
            tex_str
        )
        
        if latex_snippet is None:
            logging.warning(f"Could not create correction {progress}: no LaTeX snippet for edit {progress}: {edit}")
            continue

        corrections.append(
            Correction(
                i, pageno, edit.type, edit.message, edit.selection,
                pdf_annot_rect, edit.selection_bbs, latex_snippet,
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
    """find which corrections overlap"""
    if not corrections:
        return [], []
    ### Don't extend snippets based on groups now. If one correction fails it compromises the entire group. I think it's more clean if a little more challenging to just compose the individual edits (and individuall screen them, too).
    # tex_str = sourceAsString(tex_filename)
    
    keyed_start_ends = {corr.index: corr.snippet_source_positions for corr in corrections}
    
    groups = groupOverlaps(keyed_start_ends)

    ### Don't extend snippets based on groups now. If one correction fails it compromises the entire group. I think it's more clean if a little more challenging to just compose the individual edits (and individuall screen them, too).
    # snippets = [] 
    # for group in groups:
    #     spans_in_group = [keyed_start_ends[k] for k in group]
    #     min_start = min(spans_in_group, key = lambda span: span[0])[0]
    #     max_end = max(spans_in_group, key = lambda span: span[1])[1]
    #     containing_snippet = tex_str[min_start:max_end]
    #     snippets.append(containing_snippet)
    #     for k in group:
    #         corr = key_to_correction[k]
    #         if not corr.latex_snippet in containing_snippet:
    #             logging.error(
    #                  "Failed to create overlapping groups: "
    #                 f"a snippet \n{corr.snippetToCodeblock()}\n was not in its spanning snippet \n{toCodeblock(containing_snippet)}\n"
    #             )
    #             sys.exit(1)
    #         corr.updateSnippet((min_start, max_end), containing_snippet)
    
    return groups

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
    corrections = kwargs.get('corrections', None)

    if corrections is None:
        corrections = getCorrections(*args) # returns list[Correction]
        
    key_to_correction = {corr.index: corr for corr in corrections}

    # modifies corrections so that all snippets in a group are the same---they span the group
    overlapping_corrections = groupOverlappingCorrections(corrections, tex_filename, key_to_correction) # returns tuple[list[list[int]], list[str]], second argument currently unused.

    ## chunk corrections
    standalone_keys = [corridx for corridx in key_to_correction if corridx not in {idx for group in overlapping_corrections for idx in group}]    
    chunks = getChunks(key_to_correction, standalone_keys, chunksize)

    ## prompt model with chunks
    updated_snippets = {}
    explanations = {}

    logging.info(f"QUERYING {model}...")
    start_time = time.time()    

    processStandaloneChunks(chunks['standalone'], model, updated_snippets, explanations, system_prompt, model_temp, model_top_p)
    processOverlappingGroups(overlapping_corrections, key_to_correction, model, updated_snippets, explanations, system_prompt, model_temp, model_top_p)

    logging.info(f"DONE QUEREYING {model}. Total elapsed time: {(time.time() - start_time)/60:.2f} minutes")

    ## apply updates to source file
    # TODO: implement later
    
    return updated_snippets, explanations, standalone_keys, overlapping_corrections
    
    
if __name__ == '__main__':
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

    Path.mkdir(Path("tmp_prompt"), exist_ok = True)
    corr_file = Path("tmp_prompt/corrections.pkl")
    tmp_prompt_dir = corr_file.parent

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
        corrections = getCorrections(args.annotated_PDF_filename, args.latex_filename)
        with open(corr_file, 'wb') as f:
            pickle.dump(corrections, f)
    else:
        with open(corr_file, 'rb') as f:
            corrections = pickle.load(f)

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
    updated_snippets_pickle_file = tmp_prompt_dir / Path(f'updated_snippets_and_explanations_{Path(args.annotated_PDF_filename).stem}_{identifying_run_str}.pkl')

    if args.load_previous_output:
        logging.info(f"Loading pickle file {updated_snippets_pickle_file}...")
        with open(updated_snippets_pickle_file, 'rb') as f:
            (updated_snippets, explanations, standalone_keys, group_keys) = pickle.load(f)
        logging.info("Done.")
    else:
        updated_snippets, explanations, standalone_keys, group_keys = processCorrections(
            args.annotated_PDF_filename,
            args.latex_filename,
            corrections=corrections,
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
