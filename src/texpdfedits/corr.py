import logging
logger = logging.getLogger(__name__)

import argparse
import pymupdf
import json
import time
import pickle
import re
import sys

import texpdfedits.extractanns as extractanns
import texpdfedits.marktex as marktex
import texpdfedits.utils as utils

from pathlib import Path      

BOXES_ORDER_THRESHOLD_BUFF = 6
"""
When a rectangle doesn't intersect any word boxes, we look for
the word boxes "before" and "after" the rectangle. If the given
rectangle has y0 Y and a word box has y0 Y+.01, it would by
default be recognized as coming "after" the given rectangle
when very often it could actually appear earlier in the line.

To address this, we introduce a threshold so a word box is "after"
(or "before") the given rectangle only if its y0 is greater than
the given y0 plus this buffer (or less than the given y0 minus
this buffer). This is used in determining boxes_before and boxes_after.

We may need to eventually find a new and better way to determine word
box order if we continue to encounter issues (but I haven't so far).
"""

def categorizeMarkIDs(mark_ids: list[str]) -> int:
    """
    If the marks are all the same level of nesting, e.g.,
    all boxes are within the same footnote, return 'compatible'
    
    If the marks are all the same level of nesting except for the head count,
    e.g., all boxes are within thanks but include boxes in two different thanks,
    return 'maybe compatible'
    
    If the marks are not the same at all, e.g., one is in just in the
    document and another is in a footnote (inside the document),
    return 'incompatible'
    """
    sets_of_counter_info = {}
    count_info_lens = set()
    for mark_id in mark_ids:
        count_info = marktex.markIdToCountInfo(mark_id)
        count_info_lens.add(len(count_info))
        for i, name_head_stem in enumerate(count_info):
            if i not in sets_of_counter_info:
                sets_of_counter_info[i] = {
                    'names': set(),
                    'heads': set(),
                    'stems': set(),
                }
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

def isSimpleID(mark_id: str) -> bool:
    names = [
        c['name']
        for c in marktex.markIdToCountInfo(mark_id)
    ]
    return names in (['DOCUMENT'], ['DOCUMENT', 'ABSTRACT'])

def getTerminalStem(mark_id: str) -> int:
    count_info = marktex.markIdToCountInfo(mark_id)
    return count_info[-1]['stem']

def infoToMarkID(count_info: list[dict[str, str]]):
    return ','.join(
        [
            f"{piece['name']}{piece['head']};{piece['stem']}"
            for piece in count_info
        ]
    )

def getAdjacentKey(
        mark_id: str,
        plus_minus: int,
        page: int,
        tex_word_boxes: dict[int, dict[str, pymupdf.Rect]],
) -> str:
    """return the previous and next key based on the terminal stem value.
    So document0;0,caption0;1,footnote5;10
    should return

    document0;0,caption0;1,footnote5;9
    and
    document0;0,caption0;1,footnote5;11
    """
    count_info = marktex.markIdToCountInfo(mark_id)
    stem_val = int(count_info[-1]['stem']) 
    count_info[-1]['stem'] = str(stem_val + plus_minus)
    adjacentMark = infoToMarkID(count_info) 
        
    if adjacentMark in tex_word_boxes[page]:
        return adjacentMark
    elif (
        page + plus_minus in tex_word_boxes
        and adjacentMark in tex_word_boxes[page + plus_minus]
    ):
        return adjacentMark
    else:
        return None

def checkMaybeCompatible(
        mark_ids: list[str],
        mark_positions: dict[str, tuple[int, int]],        
) -> tuple[str, str]:
    """mark_ids are "maybe compatible" if their counters other
    than the last are known to all be equal

    In word's, the intention of this function is to look
    at each group of counters which have the same head value
    and compare the last in that group to the first in the
    next group with the same head value.

    (Typically it will have head value of just one more, but we don't require this.)

    If the number of characters between the end and the start
    for each of these pairs is less than some arbitrary threshold,
    say 100 characters, Then we'll return the key of the first id
    in the lowest head count group and the key of the last id in
    the largest head count group as our start_ and end_ extraction keys.
    """
    count_infos = [
        marktex.markIdToCountInfo(m_id)
        for m_id in mark_ids
    ]
    head_partitions = {}
        
    for c_info in count_infos:
        # [-1] because we already know that all preceding 
        # count information is the same            
        head_count = c_info[-1]['head']
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
        last_curr = infoToMarkID(
            max(head_partitions[curr_hcount], key=returnCinfoStem)
        )
        first_next = infoToMarkID(
            min(head_partitions[next_hcount], key=returnCinfoStem)
        )

        start_pos = mark_positions[last_curr][1]
        end_pos = mark_positions[first_next][0]
        if not (
            start_pos < end_pos
            and end_pos - start_pos < MAYBE_COMPATIBLE_POSITION_DIFFERENCE_THRESH
        ):
            logger.debug(
                f"Mark IDs are not compatible for source extraction:\n"
                f"markId {last_curr} had end {start_pos} and id {first_next} had start {end_pos}"
            )
            return None, None

    start_key = infoToMarkID(
        min(head_partitions[sorted_head_counts[0]], key=returnCinfoStem)
    )
        
    end_key = infoToMarkID(
        max(head_partitions[sorted_head_counts[-1]], key=returnCinfoStem)
    )
    return start_key, end_key
                
def rectangleToLatex(
        pageno: int,
        in_rectangle: pymupdf.Rect,
        tex_word_boxes: dict[int, dict[str, pymupdf.Rect]],
        mark_positions: dict[str, tuple[int, int]],
        tex_str: str
) -> str | None:
    r"""
    Args:
        pageno: Zero-indexed page number
        in_rectangle: Rectangle on the page (pymupdf format)
        tex_word_boxes: Dictionary from getWordBoxes()
        in marktex.py mark_positions:
        dictionary mapping mark_id -> (start, end) positions in tex_str 
        tex_str: original unmarked LaTeX source

    Returns: The (unmarked) source LaTeX snippet which
    "contains" the rectangle.

    Logic:
    If the inputted rectangle intersects at least one
    word box, then we consider three possibilities
         1. The word boxes are "compatible" -> we use the
            boxes within that level: ids are first preceding,
            next following
    
         2. The word boxes are "maybe compatible" -> we have
            partitions of ids by head value, and we check the pairs
            (last stem of head i, first stem of head i + 1)
            and see if their distance in source position (in
            characters) is more than some threshold.
    
            If all of these distances are less than a threshold, then
            we give all the source between the box before the
            earliest intersected head and the box after the
            last intersected head.

            If the distances are not all within that threshold
            then we don't extract the source
    
          3. The word boxes are "incompatible"
             -> we don't extract any source

    Otherwise, (the inputted rectangle does not intersect any boxes) -> 
    We simply use the boxes only numbered within the document and the
    range of the first document box before the rectangle through
    (and including) the first document box after the rectangle
    """
    if pageno not in tex_word_boxes:
        logger.warning(
            f"Cannot extract LaTeX: "
            f"pageno {pageno} not in tex_word_boxes"
        )
        return None, None

    page_word_boxes = tex_word_boxes[pageno]
    intersecting_word_boxes = {
        k : rect
        for k, rect in page_word_boxes.items()
        if in_rectangle.intersects(rect)
    }

    if intersecting_word_boxes:
        # logger.debug(f"Rectangle {in_rectangle} on page {pageno} intersected {len(intersecting_word_boxes)} word boxes")
        mark_ids = list(intersecting_word_boxes.keys())
        category = categorizeMarkIDs(mark_ids)
        if category == 'compatible':
            min_key = min(mark_ids, key=getTerminalStem)
            max_key = max(mark_ids, key=getTerminalStem)
            
            before_min = getAdjacentKey(
                min_key,
                -1,
                pageno,
                tex_word_boxes,
            )
            after_max = getAdjacentKey(
                max_key,
                1,
                pageno,
                tex_word_boxes,
            )
            
            start_key = before_min if before_min is not None else min_key
            end_key = after_max if after_max is not None else max_key
        elif category == 'maybe compatible':
            start_key, end_key = checkMaybeCompatible(mark_ids, mark_positions)
        else:
            logger.warning(
                f"Cannot extract LaTeX: "
                f"intersected mark IDs were not compatible."
            )
            logger.debug(f"Incompatible mark IDs were\n{mark_ids}")
            return None, None
    else:
        logger.debug(
            f"Rectangle {in_rectangle} did NOT intersect "
            f"any word box on page {pageno}"
        )
        boxes_before = {
            k: rect
            for k, rect in page_word_boxes.items()
            if rect.y0 < in_rectangle.y0 - BOXES_ORDER_THRESHOLD_BUFF
            and isSimpleID(k)
        }
        boxes_after = {
            k: rect
            for k, rect in page_word_boxes.items()
            if rect.y0 > in_rectangle.y0 + BOXES_ORDER_THRESHOLD_BUFF
            and isSimpleID(k)
        }

        # logger.debug(f"boxes before: {boxes_before}\n\n")
        # logger.debug(f"boxes after: {boxes_after}\n\n")        
        
        start_key = max(boxes_before.keys(), key=getTerminalStem) if boxes_before else None
        end_key = min(boxes_after.keys(), key=getTerminalStem) if boxes_after else None
        
        if start_key is None:
            simple_IDs = [fid for fid in tex_word_boxes[pageno - 1] if isSimpleID(fid)] if pageno-1 in tex_word_boxes else []
            start_key = max(simple_IDs, key=getTerminalStem) if len(simple_IDs) > 0 else None

        if end_key is None:
            simple_IDs = [fid for fid in tex_word_boxes[pageno + 1] if isSimpleID(fid)] if pageno+1 in tex_word_boxes else []
            end_key = min(simple_IDs, key=getTerminalStem) if len(simple_IDs) > 0  else None

    if start_key is None or end_key is None:
        # This should only happen if
        # (1) the rectangle doesn't intersect any boxes and it comes before or after all of them
        # (2) the rectangle intersects boxes which have incompatible ids
        # (2.1) the rectangle intersects boxes which are maybe compatible that are actually deemed incompatible by checkMaybeCompatible
        logger.warning(
            f"Cannot extract LaTeX: "
            f"Rectangle outside marked boxes "
            f"(start_key={start_key}, end_key={end_key})"
        )
        return None, None

    # logger.debug(f"Before key is {start_key} and after key is {end_key}")

    start_pos = mark_positions[start_key][0]
    end_pos = mark_positions[end_key][1]

    if start_pos > end_pos:
        # this shouldn't happen thanks to BOXES_ORDER_THRESHOLD_BUFF
        logger.warning(
            f"Cannot extract LaTeX: "
            f"start_pos = '{start_pos}' > '{end_pos}' = end_pos"
        )
        return None, None
    
    return (tex_str[start_pos:end_pos], (start_pos, end_pos))

def toCodeblock(string: str, language: str = 'latex'):
        return f"```{language}\n{string}\n```"

def markdownReplies(replies: list[str]):
    if not replies:
        return ''
    output = '\n\n### Replies '
    for i in range(len(replies)):
        output += (
            f'\n\n#### Reply {i+1}\n'
            f'```text\n{replies[i]}\n```'
        )
    return output

class Correction:
    """
    Includes all the information I need to produce and
    debug the individual correction prompts. There's
    probably room for improvement in the terminology,
    but an "edit" is the information I get from a PDF
    annotation; and a "correction" is that information
    combined with the corresponding latex_snippet
    which is needed to carry out the "edit".
    
    Attributes:
    index: the zero-indexed correction number
    
    pageno: the (also zero-indexed) page the correction appears on
    
    type: the annotation type of the correction, e.g.,
          "Caret", "Strikeout", "Highlight".
    
          These are a tuple where the first value is an int as listed
          at https://pymupdf.readthedocs.io/en/latest/vars.html#annotationtypes
          (see PDF_ANNOT_TEXT for example) and the second is a string
          which is a name pymupdf supplies but isn't easily accessible
          other than through an actual annotation object which was
          processed in extractanns.py
    
    messages: the text written in the annotation comment box and
          any replies to it (which are sorted by date)
    
    pdf_selected_text: the text extracted from the PDF.
          HTML-like focus tags indicate which text was
          selected by the annotaiton.

    pdf_annot_rect: the rectangle of the correction annotation from
          the that page of the PDF

    **pdf_selection_bbs: the rectangles used to partition the text
          extracted from the pdf_annot_rect into
          pieces which are and are not inside the HTML-like
          focus tags. See getSelection in extract.py for more on this
    
    latex_snippet: the latex source which (more or less) rendered
          the pdf_selected_text. See marktex.py for more on how this
          was retrieved
    
    snippet_source_positions: the start and end positions of the latex_snippet
          in the original latex_string.

          The latex_snippet is simply tex_str[start:end] where tex_str
          is the source LaTeX as a string
    """
    def __init__(
            self,
            index: int,
            pageno: int, 
            type: tuple[int, str],
            messages: dict[str, str | list[str]],
            pdf_selected_text: str,
            pdf_annot_rect: pymupdf.Rect,
            pdf_selection_bbs: list[pymupdf.Rect],
            latex_snippet: str,
            snippet_source_positions: tuple[int, int]
    ) -> None:
        self.index                    = index
        self.pageno                   = pageno
        self.type                     = type
        self.messages                 = messages
        self.pdf_selected_text        = pdf_selected_text
        self.pdf_annot_rect           = pdf_annot_rect
        self.pdf_selection_bbs        = pdf_selection_bbs
        self.latex_snippet            = latex_snippet
        self.snippet_source_positions = snippet_source_positions

        self.is_autocorrected = False
        self.group = None

    def __str__ (self): 
        return json.dumps({
            "index" : self.index,
            "pageno": self.pageno,
            "type": self.type[1],
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

    def asCommentStart(self, format: str):
        import texpdfedits.formatcomm as formatcomm        
        replies = '", "'.join(utils.replaceNewlines(reply) for reply in self.messages['responses'])
        return formatcomm.startComment(self, format, replies)
        
    def asCommentEnd(self, format: str):
        import texpdfedits.formatcomm as formatcomm
        replies = '", "'.join(utils.replaceNewlines(reply) for reply in self.messages['responses'])        
        return formatcomm.endComment(self, format, replies)
    
    def asMarkdownPrompt(self):
        replies = markdownReplies(self.messages['responses'])
        return rf"""### Annotation: {self.type[1]}

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
    
    def updateSnippet(
            self,
            new_source_pos: tuple[int, int],
            new_snippet: str
    ) -> None:
        self.snippet_source_positions = new_source_pos
        self.latex_snippet = new_snippet

    def snippetToCodeblock(self):
        return f"```latex\n{self.latex_snippet}\n```"


def groupOverlaps(
        keyed_start_ends: dict[int, tuple[int]]
) -> list[list[int]]:
    """
    I have a list of dictionaries where each dictionary has
    keys whose values are tuples with start and end values.
    
    I  group together all keys whose start and end values overlap.
    
    If there are no such keys, then I return an empty list.
    """
    if not keyed_start_ends:
        return []
    
    # sort by starts    
    keys = list(
        sorted(
            [k for k in keyed_start_ends],
            key = lambda k: keyed_start_ends[k][0]
        )
    ) 

    groups = []
    current_group = [keys[0]]
    curr_group_end = keyed_start_ends[keys[0]][1]
    for i, k in enumerate(keys):
        if i == 0:
            continue
        start = keyed_start_ends[k][0]
        end   = keyed_start_ends[k][1]
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

def groupOverlappingCorrections(
        corrections: list[Correction],
        tex_str: str,
        **kwargs
) -> tuple[list[list[int]], list[str]]:
    """
    Find which corrections overlap, and update the
    correction snippets (and source positions) to
    span the union of the overlapping corrections
    """
    merge_overlapping_snippets = kwargs.get('merge_overlapping_snippets', True)
    
    if not corrections:
        return [], []

    key_to_correction = {corr.index: corr for corr in corrections}
    keyed_start_ends = {
        corr.index: corr.snippet_source_positions for corr in corrections
    }
    groups = groupOverlaps(keyed_start_ends)

    for group in groups:
        spans_in_group = [keyed_start_ends[k] for k in group]
        min_start = min(spans_in_group, key = lambda span: span[0])[0]
        max_end = max(spans_in_group, key = lambda span: span[1])[1]
        containing_snippet = tex_str[min_start:max_end]
        for k in group:
            corr = key_to_correction[k]
            if not corr.latex_snippet in containing_snippet:
                logger.critical(
                     "Failed to create overlapping groups: "
                    f"a snippet \n{corr.snippetToCodeblock()}\n was not in its"
                    f" spanning snippet \n{toCodeblock(containing_snippet)}\n"
                )
                sys.exit(1)
            if merge_overlapping_snippets:
                corr.updateSnippet((min_start, max_end), containing_snippet)
            corr.group = group
    
    return groups    

def getCorrections(
        annot_filename: str,
        latex_filename: str,
        **kwargs
) -> list[Correction]:

    # To be honest, I don't know why you would ever group the overlapping
    # snippets and *not* update them. This must be a remnant of something
    # I discarded before 
    merge_overlapping_snippets = kwargs.get('merge_overlapping_snippets', True)
    
    group_overlapping   = kwargs.get('group_overlapping', True)
    compiler            = kwargs.get('compiler', 'pdflatex')
    clean               = kwargs.get('clean', True)

    edits = extractanns.getEdits(annot_filename, **kwargs)
    (mark_positions, tex_word_boxes) = marktex.getSyncInfo(
        latex_filename,
        **kwargs
    )
    
    tex_str = utils.sourceAsString(Path(latex_filename))

    logger.info("Making correction objects...")
    corrections = []
    for i, edit in enumerate(edits):
        progress = f"{i}/{len(edits)-1}"
        pageno = edit.pageno
        if pageno not in tex_word_boxes:
            logger.warning(
                f"Could not create correction {progress}: "
                f"Page '{pageno}' not in `tex_word_boxes` for edit {edit}"
            )
            continue
        
        pdf_annot_rect = edit.annot_rect
        logger.debug(f"Getting latex snippet for edit {edit}...")
        latex_snippet, snippet_source_positions = rectangleToLatex(
            pageno,
            pdf_annot_rect,
            tex_word_boxes,
            mark_positions,
            tex_str
        )
        logger.debug(f"Done.")
        
        if latex_snippet is None:
            logger.warning(
                f"Could not create correction {progress}: "
                f"no LaTeX snippet for edit {progress}: {edit}"
            )
            continue

        corrections.append(
            Correction(
                i, pageno, edit.type, edit.message, edit.selection,
                pdf_annot_rect, edit.selection_bbs, latex_snippet,
                snippet_source_positions
            )
        )
    logger.info("Done.")

    logger.info(
        f"Produced {len(corrections)} corrections from "
        f"{len(edits)} edit annotations."
    )

    overlapping_keys = []
    if group_overlapping:
        overlapping_keys = groupOverlappingCorrections(
            corrections,
            tex_str,
            merge_overlapping_snippets=merge_overlapping_snippets
        )
        logger.info("Grouped overlapping corrections.")
        if merge_overlapping_snippets:
            logger.info("Overlapping correction snippets merged.")
        else:
            logger.info("Overlapping correction snippets WERE NOT merged.")
    else:
        logger.info("Did **NOT** group overlapping corrections.")

    return corrections, overlapping_keys
