import logging
import argparse
import pymupdf
import json
import time
import pickle
import re

from texpdfedits.extract import getEdits
from texpdfedits.segmentsource import segment, sourceAsString, numericComponent, alphaComponent, markIdToCountInfo, runDiffpdf, pdfFname, runPDFlatex

from pathlib import Path

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

def replaceNewlines(s: str) -> str:
    return re.sub(r'[\n\r]', r' ', s)

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

    def asComment(self):
        replies = '", "'.join([replaceNewlines(reply) for reply in self.messages['responses']])
        if replies:
            replies = f'\n%% Replies: "{replies}"'
        
        return rf"""%% Correction {self.index}
%% Annotated text: "{replaceNewlines(self.pdf_selected_text)}"
%% Comment: "{replaceNewlines(self.messages['comment'])}" {replies}
%% 
"""

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
    num_marks, marked_tex, unmarked_str, mark_positions, document_word_boxes, all_metadata = segment(latex_filename)

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
            unmarked_str
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
    
    return groups

def commentSource(tex_str: str, char_positions: list[int], charpos_to_correction: dict[int, list[tuple[str, Correction]]]) -> str:
    """
    Add the corrections to the original source as comments.

    Args:
    tex_str: original LaTeX source as string
    char_positions: sorted character positions of the starts and ends of the LaTeX snippets for each correction.
            important: the positions are simply sorted from smallest to largest, and a position can correspond to a start or end of a snippet
            and it's possible to that snippets can overlap.
    charpos_to_correction: dictionary where keys are members of char_positions and values are lists of string--Correction pairs where the string is
    either 'start' or 'end' and the correction is the corresponding correction object for the position. A list is returned for each key incase
    there are two start/end character positions which are the same. Most of the time the list should just be a singleton.

    In the event that two corrections END at the same position, I'll just write

    %% END OF CORRECTIONS corr_idx1, corr_idx2, ...
    
    If two corrections START at the same position, I'll write

    %% Correction: corr_idx
    %% Type: <type>
    %% PDF selected text:
    %% Comment: (mabye should be 'Instruction:'; see asComment())

    for each correction in order and then
    %% START OF CORRECTIONS corr_idx1, corr_idx2, ...

    Finally if a start and end are at the same position then I'll write the correction info then say

    %% START of correction ... and END of correction ...
    """
    if not char_positions:
        return tex_str
    
    inserted_comments = [] #list of tuples where tuple index 0 is the char_pos and tuple index 1 is the inserted material
    for char_pos in char_positions:
        kinds_and_corrs = charpos_to_correction[char_pos]
        corr_descriptions = []
        start_corr_idxs, end_corr_idxs = [], []
        for kind_and_corr in kinds_and_corrs:
            (kind, corr) = kind_and_corr
            if kind == 'start':
                corr_descriptions.append(corr.asComment())
                start_corr_idxs.append(corr.index)
            elif kind == 'end':
                end_corr_idxs.append(corr.index)
            else:
                assert False, f"A position should only be a start or end. Invalid kind of position '{kind}'."
                
        def writeCallout(corr_idxs: list[int], start_or_end: str):
            sing_plural = 'correction' if len(corr_idxs) == 1 else 'corrections'
            return f'{start_or_end.upper()} of {sing_plural} ' + ', '.join([str(idx) for idx in corr_idxs])
        
        start_end_callout = []
        if start_corr_idxs:
            start_end_callout.append(writeCallout(start_corr_idxs, 'start'))
        if start_corr_idxs and end_corr_idxs:
            start_end_callout.append(' AND ')
        if end_corr_idxs:
            start_end_callout.append(writeCallout(end_corr_idxs, 'end'))

        description_str = ''.join(corr_descriptions)
        callout_str = ''.join(start_end_callout)

        inserted_comments.append((char_pos, f'%%\n{description_str}%% {callout_str}\n')) # orig

    commented_source = []
    prev_pos = 0
    for (char_pos, inserted_comment) in inserted_comments:
        commented_source.append(tex_str[prev_pos:char_pos])
        curr_char = tex_str[char_pos]
        next_char = tex_str[char_pos+1] if char_pos + 1 < len(tex_str) else ''
        
        # logging.debug(f"curr char: '{curr_char}'     next char: '{next_char}'")

        curr_is_space = re.match(r'[ \t]', curr_char)
        curr_is_newline = re.match(r'[\r\n]', curr_char)
        next_is_newline = re.match(r'[\r\n]', next_char)

        if curr_is_space or curr_is_newline:
            commented_source.append(' ')

        if curr_is_space and next_is_newline:
            prev_pos = char_pos + 2
        elif curr_is_space or curr_is_newline:
            prev_pos = char_pos + 1
        else:
            prev_pos = char_pos
                
        commented_source.append(inserted_comment)

    commented_source.append(tex_str[prev_pos:]) # add what remains of the tex file

    return ''.join(commented_source)

def addCorrectionComments(*args, **kwargs):
    """
    *args are the annotated pdf file name followed by the LaTeX file name
    **kwargs are key word arguments (nothing specified for now)
    """
    annot_filename, tex_filename = args
    
    corrections = kwargs.get('corrections', None)

    no_group_overlapping = kwargs.get('ngo', False)

    if corrections is None:
        corrections = getCorrections(*args)

    new_tex_filename = f"{Path(tex_filename).stem}_commentcorrs.tex"


    if not no_group_overlapping:
        key_to_correction = {corr.index: corr for corr in corrections}
        overlapping_keys = groupOverlappingCorrections(corrections, tex_filename, key_to_correction) # updates corrections
    
    # standalone_keys = [corridx for corridx in key_to_correction if corridx not in {idx for group in overlapping_keys for idx in group}]

    char_positions = []
    charpos_to_correction = dict()
    for corr in corrections:
        (start_pos, end_pos) = corr.snippet_source_positions
        if start_pos in charpos_to_correction:
            charpos_to_correction[start_pos].append(('start', corr))
        else:
            charpos_to_correction[start_pos] = [('start', corr)]
        if end_pos in charpos_to_correction:
            charpos_to_correction[end_pos].append(('end', corr))
        else:
            charpos_to_correction[end_pos] = [('end', corr)]
        char_positions.extend([start_pos, end_pos])

    char_positions = sorted(set(char_positions))

    tex_str = sourceAsString(tex_filename)
    
    commented_source = commentSource(tex_str, char_positions, charpos_to_correction)

    with open(new_tex_filename, 'w') as f:
        f.write(commented_source)

    new_tex_filename = Path(new_tex_filename)

    ## TODO: clean up file management
    ## currently original PDF has to be in cwd
    process1 = runPDFlatex(new_tex_filename)
    process2 = runPDFlatex(Path(tex_filename))
    process3 = runDiffpdf(pdfFname(Path(tex_filename)), pdfFname(new_tex_filename), Path('./'), per_page_tol=0)

    logging.info(f"Original and commented source produce identical PDFs.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annotated_PDF_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-p", "--load-pickle", action="store_true", help='load pickle file of corrections if available')
    parser.add_argument("-ngo", "--no-group-overlapping", action="store_true", help='Do not expand overlapping snippets') 
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    Path.mkdir(Path("tmp_prompt"), exist_ok = True)
    corr_file = Path("tmp_prompt/corrections.pkl")
    tmp_prompt_dir = corr_file.parent

    if not (corr_file.exists() and args.load_pickle):
        corrections = getCorrections(args.annotated_PDF_filename, args.latex_filename)
        with open(corr_file, 'wb') as f:
            pickle.dump(corrections, f)
    else:
        with open(corr_file, 'rb') as f:
            corrections = pickle.load(f)

    addCorrectionComments(args.annotated_PDF_filename, args.latex_filename, corrections=corrections, ngo=args.no_group_overlapping)

    
