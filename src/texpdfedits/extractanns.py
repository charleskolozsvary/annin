import pymupdf
import json
import argparse
import logging
logger = logging.getLogger(__name__)

import math
from copy import deepcopy

import re

PDF_ANNOT_TEXT = (0, 'Text')
PDF_ANNOT_STRIKE_OUT = (11, 'StrikeOut')
PDF_ANNOT_CARET = (14, 'Caret')

class Annot:
    """
    Revised version of pymupdf's Annot which fixes the bounding box of the Caret annotation and isn't fragile. See getRobustAnnots().
    
    There's a good chance that there's already something in pymupdf which separates the annot from the page, though, in which case this
    should be removed and the code refactored.
    """
    def __init__ (self, _pageno, _type, _info, _xref, _irt_xref, _rect): #, _line_bb, _surr_lines):
        self.pageno = _pageno        
        self.type = _type
        self.info = _info                
        self.xref = _xref
        self.irt_xref = _irt_xref
        self.rect = _rect
        
    def __str__ (self):
        return str({'pageno':self.pageno, 'type':self.type, 'info':self.info['content'], 'rect':self.rect})
    
    def __repr__ (self):
        return str(
            {'pageno':self.pageno,
             'type':self.type,
             'info':self.info,
             'xref':self.xref,
             'irt_xref':self.irt_xref,
             'rect':self.rect,
             }
        )
    
class Edit:
    """
    Represents the information necessary to carry out an edit. An edit has the following attributes:
    
    "pageno":    page number in the PDF the annotation appears on (won't ultimately be fed to the model)
    
    "type":      annotation type
                 The Edit types are mostly a subset of the Annot types (full list at
                 https://pymupdf.readthedocs.io/en/latest/vars.html#annotationtypes) with the exception
                 of "Replace" which corresponds to the combination of a Strikeout and Caret annotation
                 which are identified by isReplaceAnnot in getEdits(), not by pymupdf. 
    
    "message":   text in the annotation comment box and responses to it---typically edit directions
                 if it's not already self-evident from the type (e.g., Strikeout). The message itself
                 will contain one string for the original comment and a list of strings for the responses
    
    "selection": selected and surrounding text of the annotation from the PDF.

    Example
    {
      "pageno" : 1, 
      "type" : "Replace" 
      "message": {
                   "comment": "Theorem 3.14", 
                   "responses": ["COMP: pls link"]
                 }
      "selection": "We now prove the <Replace>following theorem</Replace>."
    }

    """

    CARET_NAME = 'Caret'
    
    def __init__ (self, _pageno, _type, _message, _selection, _selection_bbs, _annot_rect):
        self.pageno = _pageno 
        self.type = _type
        self.message = _message
        self.selection = _selection
        self.selection_bbs = _selection_bbs # for debugging
        self.annot_rect = _annot_rect # used in marktex routines
        
    def __str__ (self): 
        return json.dumps({
            "pageno": self.pageno, 
            "type": self.type, 
            "message": {
                "comment": self.message['comment'],
                "responses": self.message['responses']
            },
            "PDF text selection": self.selection
        }, indent=4, ensure_ascii=False)
    
    def __repr__ (self):
        return str(self)

def getRobustAnnots(doc):
    """
    The bounding boxes of the original caret annotations often extend below the line they
    were inserted on, so they are resized to prevent that.

    pymupdf's annotations are also kind of fragile---they are strongly bound to the page they
    come from (so when the page goes away, so does the annotation), and I've encountered issues
    with using the provided methods to update the annotations, so I'll just store the
    annotations with my own class which isn't tied to the page and correctly stores the information.
    """
    CARET_V_PROPORTION = 0.2
    CARET_H_PROPORTION = 0.2
    
    robust_annots = {pageno:[] for pageno in range(doc.page_count)}
    for pageno, page in enumerate(doc):
        for annot in page.annots():
            new_ann_rect = pymupdf.Rect(annot.rect.top_left, annot.rect.bottom_right)            
            if annot.type == PDF_ANNOT_TEXT:
                robust_annots[pageno].append(Annot(pageno, annot.type, annot.info, annot.xref, annot.irt_xref, new_ann_rect))
                continue
            (x0, y0, x1, y1) = new_ann_rect
            
            # hacky heuristic adjustment of annot rectangles (in points)
            REDUCE_AMMOUNT_ABOVE = 2.5 
            REDUCE_AMMOUNT_BELOW = 1.5 
            
            if annot.type == PDF_ANNOT_CARET:
                extension = CARET_V_PROPORTION * (y1 - y0)
                new_ann_rect.y1 = y0 + extension
                new_ann_rect.y0 = y0 - 0.75 * extension

                reduction = CARET_H_PROPORTION * (x1 - x0)
                new_ann_rect.x0 += reduction
                new_ann_rect.x1 -= reduction
            else:
                new_ann_rect.y0 = y0 + REDUCE_AMMOUNT_ABOVE
                new_ann_rect.y1 = y1 - REDUCE_AMMOUNT_BELOW
            robust_annots[pageno].append(
                Annot(pageno,
                      annot.type,
                      annot.info,
                      annot.xref,
                      annot.irt_xref,
                      new_ann_rect)
            )
    return robust_annots

def getAllResponses(robust_annots):
    """return dictionary where dict[xref] => [annots for which annot.irt_xref == xref]"""
    all_responses = dict()
    for pageno, annots in robust_annots.items():
        for annot in annots: 
            if annot.irt_xref == 0:
                continue
            if annot.irt_xref in all_responses:
                all_responses[annot.irt_xref].append(annot)
            else:
                all_responses[annot.irt_xref] = [annot]
    return all_responses

def getResponses(annot, all_responses):
    """
    return dictionary where dict[type] =>
    [annots for which annot.type == type and are a response to passed annot]
    """
    if annot.xref not in all_responses:
        return []

    resps_by_type = dict()
    for resp in all_responses[annot.xref]:
        if resp.type not in resps_by_type:
            resps_by_type[resp.type] = [resp]
        else:
            resps_by_type[resp.type].append(resp)

    for ann_type, resps in resps_by_type.items():
        # sort responses by creation date
        resps_by_type[ann_type] = sorted(resps, key = lambda r: r.info['creationDate']) 
    
    return resps_by_type

def getSelection(annot: Annot, page_words: list[tuple[int, int, int, int, str, int, int, int]], doc: pymupdf.Document):
    """
    Return: annotation's selected text, rectangle for latex source extraction,
    and selection bounding boxes for debugging

    page_words is list of (x0, y0, x1, y1, "word", block_no, line_no, word_no) tuples
    """
    page = doc[annot.pageno]
    intersecting_words = []
    
    for word in page_words:
        word_rect = pymupdf.Rect(word[0:4])
        word_intersects = annot.rect.intersects(word_rect)
        if not word_intersects:
            continue
        intersecting_words.append(word)
        
    if not intersecting_words:
        logger.warning(
            f"No selection text for {annot}: "
            "ann rectangle did not intersect ANY PDF word boxes"
        )
        return None, None, None

    CARET_X_BUFF = 1 # in points
    OTHER_ANN_X_BUFF = .75 # in points

    NUM_CONTEXT_WORDS = 2 # words to add before and after which are not selected    
    first_sel_word = intersecting_words[0]
    last_sel_word = intersecting_words[-1]

    logger.debug(
        f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
        f"intersecting_words: {intersecting_words}"
    )

    logger.debug(
        f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
        f"first_sel_word: {first_sel_word}\nlast_sel_word: {last_sel_word}"
    )

    intersecting_words = {word : '' for word in intersecting_words} # make dict for fast lookup later

    start_word_idx = max(0, page_words.index(first_sel_word) - NUM_CONTEXT_WORDS)
    end_word_idx = min(len(page_words)-1, page_words.index(last_sel_word) + NUM_CONTEXT_WORDS)

    logger.debug(
        f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
        f"start_word: {page_words[start_word_idx]}\nend_word: {page_words[end_word_idx]}"
    )    

    selection_name = annot.type[1]
    selection_bbs = []

    DIFF_THRESH = 1 # in points

    def wordGetTextToStr(word_selection):
        return ' '.join([word[4] for word in word_selection])

    def insideAnnotRect(word_box):
        """ only call on words which intersect annot """
        left_diff = abs(annot.rect.x0 - word_box.x0)
        right_diff = abs(annot.rect.x1 - word_box.x1)
        
        return annot.rect.x0 < word_box.x0 and left_diff > DIFF_THRESH and word_box.x1 < annot.rect.x1 and right_diff > DIFF_THRESH

    def getCaretSelection(word_box):
        """word_box intersects the annot rectangle, but it is not "inside" it according to insideAnnotRect"""        
        x0 = annot.rect.x0 if annot.rect.x0 <= word_box.x0 else word_box.x0
        insertion_x = annot.rect.x0 + annot.rect.width / 2
        x1 = annot.rect.x1 if word_box.x1 <= annot.rect.x1 else word_box.x1

        y0, y1 = annot.rect.y0, annot.rect.y1
        left_rect = pymupdf.Rect(x0, y0, insertion_x - CARET_X_BUFF, y1)
        right_rect = pymupdf.Rect(insertion_x + CARET_X_BUFF, y0, x1, y1,)

        selection_bbs.append([left_rect, right_rect])

        left = wordGetTextToStr(page.get_text('words', clip=left_rect, sort=True))
        right = wordGetTextToStr(page.get_text('words', clip=right_rect, sort=True))
        return f"{left}<{Edit.CARET_NAME}>{right}"

    def getOtherSelection(word_box):
        """
        word_box intersects the annot rectangle, but it is not
        "inside" it according to insideAnnotRect---it is on the annotation "boundary"
        """        
        tag_insertion_xs = {'start': None, 'end': None}
        a_rect = annot.rect

        x0_diff = abs(a_rect.x0 - word_box.x0)
        x1_diff = abs(a_rect.x1 - word_box.x1)

        if (word_box.x0 <= a_rect.x0 or x0_diff < DIFF_THRESH)  and a_rect.x0 < word_box.x1:
            tag_insertion_xs['start'] = a_rect.x0
        if word_box.x0 < a_rect.x1 and (a_rect.x1 <= word_box.x1 or x1_diff < DIFF_THRESH):
            tag_insertion_xs['end'] = a_rect.x1

        y0, y1 = a_rect.y0, a_rect.y1
        
        if tag_insertion_xs['start'] is not None and tag_insertion_xs['end'] is None:
            left_rect  = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['start'] - OTHER_ANN_X_BUFF, y1)
            right_rect = pymupdf.Rect(tag_insertion_xs['start'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, right_rect])

            left = wordGetTextToStr(page.get_text('words', clip=left_rect, sort=True)) if left_rect.is_valid else ''    
            right= wordGetTextToStr(page.get_text('words', clip=right_rect, sort=True))
            return f"{left}<{selection_name}>{right}"
            
        elif tag_insertion_xs['end'] is not None and tag_insertion_xs['start'] is None:
            left_rect  = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['end'] - OTHER_ANN_X_BUFF, y1)
            right_rect = pymupdf.Rect(tag_insertion_xs['end'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, right_rect])
            
            left = wordGetTextToStr(page.get_text('words', clip=left_rect, sort=True))
            right= wordGetTextToStr(page.get_text('words', clip=right_rect, sort=True)) if right_rect.is_valid else ''                
            return f"{left}</{selection_name}>{right}"
            
        elif tag_insertion_xs['start'] is not None and tag_insertion_xs['end'] is not None:
            left_rect = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['start'] - OTHER_ANN_X_BUFF, y1)
            middle_rect = pymupdf.Rect(tag_insertion_xs['start']+OTHER_ANN_X_BUFF, y0, tag_insertion_xs['end']-OTHER_ANN_X_BUFF, y1)
            right_rect = pymupdf.Rect(tag_insertion_xs['end'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, middle_rect, right_rect])

            left = wordGetTextToStr(page.get_text('words', clip=left_rect, sort=True)) if left_rect.is_valid else ''
            middle = wordGetTextToStr(page.get_text('words', clip=middle_rect, sort=True))
            right = wordGetTextToStr(page.get_text('words', clip=right_rect, sort=True)) if right_rect.is_valid else ''
            return f"{left}<{selection_name}>{middle}</{selection_name}>{right}"

        else:
            logger.warning(
                f"Could not produce selection text for annot {annot}: "
                "There was neither a start or end boundary of the annotation on the word box"
            )
            return None

    def wordDistance(w1: tuple[int, int, int, int, str, int, int, int], w2) -> float:
        rect1 = pymupdf.Rect(w1[0:4])
        rect2 = pymupdf.Rect(w2[0:4])
        def getCenter(rect):
            return (rect.x0 + rect.width / 2, rect.y0 + rect.height/2)
        c_1 = getCenter(rect1)
        c_2 = getCenter(rect2)
        return math.sqrt((c_1[0] - c_2[0]) ** 2 + (c_1[1] - c_2[1]) ** 2)

    MAX_WORD_DISTANCE_IF_DIFF_BLOCK = 24 # in points
            
    selected_text = []
    caret_inserted = False
    for idx in range(start_word_idx, end_word_idx + 1):
        word = page_words[idx]
        word_box = pymupdf.Rect(word[0:4])
        word_str = word[4]
        if word not in intersecting_words:
            # logger.debug(f"word '{word_str}' in {annot} doesn't intersect annot Rect")
            word_block_no = word[5]
            if word_block_no == first_sel_word[5] or wordDistance(word, first_sel_word) < MAX_WORD_DISTANCE_IF_DIFF_BLOCK:
                selected_text.append(word_str)
            continue

        if insideAnnotRect(word_box):
            # logger.debug(f"word '{word_str}' with box '{word_box}' in {annot} inside annot Rect")
            selected_text.append(word_str)
            continue
        
        if annot.type == PDF_ANNOT_CARET:
            if caret_inserted:
                continue
            selected_text.append(getCaretSelection(word_box))
            caret_inserted = True
        else:
            res = getOtherSelection(word_box)
            if res is None:
                return None, None, None
            selected_text.append(res)
    # logger.debug(f"selected_text for {annot} is {selected_text}")
    return ' '.join(selected_text), selection_bbs, annot.rect
    

def isNotForCOMP(message: dict[str, str | list[str]]) -> bool:
    head_comment = message['comment']
    responses = message['responses']
    first_response = responses[0] if responses else ''

    not_for_comp = r"\b(?:AU|PE|PTG|GA)\b:?"
    for_comp = r"\b(?:COMP|TEG)\b:?"

    if re.search(not_for_comp, head_comment, re.IGNORECASE) is not None:
        if re.search(for_comp, first_response, re.IGNORECASE) is not None:
            return False
        else:
            return True
    else:
        return False

def getEdits(filename):
    """return a list of Edits. See class Edit."""
    doc = pymupdf.open(filename)
    robust_annots = getRobustAnnots(doc)
    all_responses = getAllResponses(robust_annots)

    target_num_edits = 0
    logger.info("Turning annotations into edits...")
    num_not_for_comp = 0
    edits = []
    for pageno, page in enumerate(doc):
        for annot in robust_annots[pageno]:
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine with another to make an annotation of type 'Replace'
                continue
            target_num_edits += 1
            
            responses = getResponses(annot, all_responses)
            text_responses = responses[PDF_ANNOT_TEXT] if PDF_ANNOT_TEXT in responses else []
            text_responses = [resp.info['content'] for resp in text_responses]
            message = {'comment': annot.info['content'], 'responses': text_responses}

            # skip annots whose comment text starts with AU:, PE:, or PTG: among other things, unless the first response has COMP: or TEG:
            if isNotForCOMP(message):
                logger.debug(f"Annot {annot} deemed not for COMP")
                num_not_for_comp += 1
                continue

            def isReplaceAnnot(ann, ann_resps):
                if not (ann.type == PDF_ANNOT_STRIKE_OUT or ann.type == PDF_ANNOT_CARET) or ann_resps == []:
                    return False, None
                
                assert ann.type not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = PDF_ANNOT_STRIKE_OUT if ann.type == PDF_ANNOT_CARET else PDF_ANNOT_CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False, None
                other_ann = ann_resps[other_ann_type][0]

                if not (ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == ''):
                    return False, None
                return True, other_ann
                
            is_replace, other_ann = isReplaceAnnot(annot, responses)
            
            if is_replace:
                if annot.type == PDF_ANNOT_CARET:
                    annot.rect = other_ann.rect
                annot.type = (None, 'Replace')

            # rename strikeout to remove
            if annot.type == PDF_ANNOT_STRIKE_OUT:
                annot.type = (None, 'Remove')

            page_words = page.get_text('words', sort=True)    
            # the sort option doesn't actually sort in lexicographic order... maybe it does it by rectangle positions.
            page_words = list(sorted(page_words, key = lambda w: (w[5], w[6], w[7])))
            
            selection_text, selection_bbs, latex_extraction_bb = getSelection(annot, page_words, doc)
            if selection_text is None:
                continue
            
            edits.append(Edit(annot.pageno, annot.type[1], message, selection_text, selection_bbs, latex_extraction_bb))

        if robust_annots[pageno]:
            logger.info(f"Extracted annotations on page {pageno:3d}/{doc.page_count-1:3d}")
        
    logger.info(f"Created {len(edits)} edits from {target_num_edits} PDF annotations")
    logger.info(f"Ignored {num_not_for_comp} annotation(s) deemed not for COMP")
    return edits
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python extract.py',
                                     description = 'Return edits from annotated pdf as json')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-pe", "--print-edits", action="store_true", help='print edits at the end')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    edits = getEdits(filename)    

    if args.print_edits:
        for edit in edits:
            print(edit)
