import pymupdf
import json
import argparse
import logging
import sys
from copy import deepcopy

PDF_ANNOT_TEXT = (0, 'Text')
PDF_ANNOT_STRIKE_OUT = (11, 'StrikeOut')
PDF_ANNOT_CARET = (14, 'Caret')

SELECT_TEXT_ANNOTS = {"Replace", "StrikeOut", "Highlight", "Underline"}

# When extracting selection text I alter the bounding boxes slightly to avoid repeating or missing symbols.
# The value of two points was chosen heuristically; it works well enough for the time being on the PDFs I've tested.
# It is possible that this approach will fail on very small or large text and will need to updated in the future.
CARET_BUFF = 2 # in pymupdf points
EXTRACT_TEXT_BUFFER_WIDTH = 2 # also in pymupdf points

# set surrounding lines to at most the line above and below
# if set to two, include two lines above and two lines below
# the line the annot intersects
NUM_SURROUNDING_LINES = 1

NORMALIZATION_HEIGHT_PROPORTION = 1/3 # bottom and top thirds

class Annot:
    """Revised version of pymupdf's Annot which fixes the bounding box of the Caret annotation and isn't fragile. See getRobustAnnots()"""
    def __init__ (self, _pageno, _type, _info, _xref, _irt_xref, _rect, _line_bb, _surr_lines):
        self.pageno = _pageno        
        self.type = _type
        self.info = _info                
        self.xref = _xref
        self.irt_xref = _irt_xref
        self.rect = _rect
        self.line_bb = _line_bb
        self.surr_lines = _surr_lines
        
    def __str__ (self):
        return str({'pageno':self.pageno,
                    'type':self.type,
                    'info':self.info,
                    'xref':self.xref,
                    'irt_xref':self.irt_xref,
                    'rect':self.rect,
                    'intersecting line bb':self.intersecting_line_bb})
    
    def __repr__ (self):
        return str(self)

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
    def __init__ (self, _pageno, _type, _message, _selection, _selection_bbs, _selection_line_rect):
        self.pageno = _pageno 
        self.type = _type
        self.message = _message
        self.selection = _selection
        self.selection_bbs = _selection_bbs # will not be sent to the model
        self.selection_line_rect = _selection_line_rect # will also not be sent to the model, but is used in segmentsource routines
        
    def __str__ (self): # json is getting scrapped for markdown, but this is still fine for debugging
        return json.dumps({
            "pageno": self.pageno, # will probably not ultimately give to the model
            "type": self.type, 
            "message": {
                "comment": self.message['comment'],
                "responses": self.message['responses']
            },
            "PDF text selection": self.selection
        }, indent=4, ensure_ascii=False)
    
    def __repr__ (self):
        return str(self)

def normalizeLineRectYs(line_bb, line_bbs):
    """Every now and then I  see the top of one line extend into the line above it,
    which is what this definition addresses, but I have never seen the bottom of a line
    extend into the line below it, though I also handle this here just in case.
    
    Rect corrdinates = (x0, y0, x1, y1)"""
    line_rect = pymupdf.Rect(line_bb)
    intersecting_lines = list(filter(lambda l: line_rect.intersects(l), line_bbs))
    num_isec_lines = len(intersecting_lines)
    if line_rect not in intersecting_lines:
        logging.error(f"""line_rect {line_rect} is not in intersecting_lines, {intersecting_lines}.
        It should always intersect itself. Exiting...""")
        sys.exit(1)
    if num_isec_lines == 1:
        return line_rect # nothing to normalize

    if num_isec_lines > 3:
        logging.debug(f"""line {line_bb} intersected {len(intersecting_lines)} other lines,
        {intersecting_lines}, which is more than usual, but it shouldn't be a problem""")

    # sorting the lines by y0 or y1 is an arbitrary decision, but our logic should give identical results in either case
    # so that would be a good thing to test. 
    lines_by_y1 = list(sorted(intersecting_lines, key = lambda bb: bb[3]))
    idx = lines_by_y1.index(line_rect)

    lines_before = lines_by_y1[:idx]
    lines_after = lines_by_y1[idx+1:]    

    # new line normalization >>>
    # add a filter so that we only keep
    # (1) lines before whose baselines (y1s) are *above* the bottom_thresh 
    # (2) lines after  whose toplines  (y0s) are *below* the top_thresh

    # of course, if line_bb itself is already quite compromised (say, it extends very far into the line
    # above or below it) this doesn't work too well but I think it's the best I can do right now
    thresh_height_proportion = line_rect.height * NORMALIZATION_HEIGHT_PROPORTION
    bottom_thresh = line_rect.y1 - thresh_height_proportion
    top_thresh = line_rect.y0 + thresh_height_proportion
    
    lines_before = list(filter(lambda bb: bb[3] < bottom_thresh, lines_before))
    lines_after = list(filter(lambda bb: bb[1] > top_thresh, lines_after))
    # <<<

    # plus or minus fraction of a point to prevent intersection
    buff = 0.25
    
    # set y0 to below lowest baseline of lines before
    if lines_before == []:
        normalized_y0 = line_rect.y0        
    else:
        normalized_y0 = max(lines_before, key = lambda bb: bb[3])[3] + buff
        logging.debug(f"Lines before = {lines_before}")
        logging.debug(f"normalized_y0 = {normalized_y0}")        

    # set y1 of line to above highest topline of lines after            
    if lines_after == []:
        normalized_y1 = line_rect.y1        
    else:
        normalized_y1 = min(lines_after,  key = lambda bb: bb[1])[1] - buff
        logging.debug(f"Lines after = {lines_after}")
        logging.debug(f"normalized_y1 = {normalized_y1}")

    return pymupdf.Rect(line_rect.x0, normalized_y0, line_rect.x1, normalized_y1)         

def getAnnotAndSurrLineRects(annot_type, annot_info, annot_rect, page_lines):
    """Return a corrected annotation bounding box (if its a caret)
       And the (normalized) bounding boxes of the line the annotation appears on and the line(s) above and
       below it (if present).
    """
    lines_that_intersect_annot = list(filter(lambda l: annot_rect.intersects(l), page_lines))
    num_lines_isec_annot = len(lines_that_intersect_annot)
    
    if num_lines_isec_annot < 1:
        # might turn this into a warning and just ignore the annotation, but this really shouldn't ever happen...
        logging.error(f"""Annotation {annot_info} of type {annot_type} and with rectangle {annot_rect}
        did not intersect any PDF line bounding boxes. Exiting...""")
        sys.exit(1)

    if num_lines_isec_annot > 1:
        # this very much seems to only happen with caret annotation rectangles
        logging.debug(f"Annot intersects more than one line bbox: {annot_info}")        

    if num_lines_isec_annot > 2 and annot_type == PDF_ANNOT_CARET:
        logging.warning(f"""A caret annotation, {annot_info}, intersected more than two lines.
        This is somewhat unusual. There's probably a lot of tall inline math near the annotation""")

    # bb (bounding box)/rectangle = (x0, y0, x1, y1)
    # where x0,y0 is top left and x1, y1 is bottom right
    
    # PDF coordinate system is with (0,0) as the top left corner of the page,
    # (page width, page height) as the bottom right corner

    # by highest I mean highest up the page, closer to y = 0

    # so in the case of a caret, we set its y1 to the value of the line it is inserted on.
    # as far as I can tell, this is always the line the caret annotation rectangle intersects which
    # has the highest baseline. Typically the caret only intersects at most two lines:
    # the line it's on and the line below it.
    # although in the what I believe to be impossible situation where the line above the line the caret is
    # inserted extends so far down into the caret's line that the caret intersects the line above,
    # this would fail. But again, I have never seen that happen and I have good reason to suspect that it won't

    # we make our "chosen line", annot_line_bb, the one which has the highest y1 which is below some threshold based on the annotation's
    # y info
    threshold = annot_rect.y0 + (annot_rect.height)/4
    lines_that_intersect_annot = list(filter(lambda bb: bb[3] > threshold, lines_that_intersect_annot))
    
    annot_line_bb = list(sorted(lines_that_intersect_annot, key = lambda bb: bb[3]))[0]

    if annot_line_bb == []:
        logging.warning(f"""None of the lines that intersected the annotation '{annot_info}'
        had a baseline below the annotations vertical midpoint. Returning no surrounding lines,
        just the original annotation rectangle""")
        return annot_rect, None, None
        
    # fix caret rect
    if annot_type == PDF_ANNOT_CARET:
        raised_rect = pymupdf.Rect(annot_rect.top_left, annot_rect.bottom_right)
        raised_rect.y1 = annot_line_bb[3]
        annot_rect = raised_rect

    lines_by_y0 = list(sorted(page_lines, key = lambda bb: bb[1]))
    idx = lines_by_y0.index(annot_line_bb)

    lines_before = lines_by_y0[:idx][-NUM_SURROUNDING_LINES:]
    lines_after = lines_by_y0[idx+1:][:NUM_SURROUNDING_LINES]
    
    annot_line_bb = normalizeLineRectYs(annot_line_bb, page_lines)
    lines_before = list(map(lambda l: normalizeLineRectYs(l, page_lines), lines_before))
    lines_after = list(map(lambda l: normalizeLineRectYs(l, page_lines), lines_after))

    return annot_rect, annot_line_bb, {'lines before': lines_before, 'lines_after': lines_after}
    

def getRobustAnnots(doc):
    """
    The bounding boxes of the original caret annotations often extend below the line they
    were inserted on, so they are resized to prevent that.

    pymupdf's annotations are also kind of fragile---they are strongly bound to the page they
    come from (so when the page goes away, so does the annotation), and I've encountered issues
    with using the provided methods to update the annotations, so I'll just store the
    annotations with my own class which isn't tied to the page and correctly stores the information.
    """
    robust_annots = {pageno:[] for pageno in range(doc.page_count)}
    for pageno, page in enumerate(doc):
        blocks = page.get_text('dict', sort=True)['blocks']
        page_lines = [line['bbox'] for block in blocks for line in block['lines']]
        for annot in page.annots():
            if annot.type == PDF_ANNOT_TEXT:
                robust_annots[pageno].append(Annot(pageno, annot.type, annot.info, annot.xref, annot.irt_xref, annot_rect, None, None))
                continue
            annot_rect, line_bb, surrounding_lines = getAnnotAndSurrLineRects(annot.type, annot.info, annot.rect, page_lines)
            robust_annots[pageno].append(Annot(pageno,
                                               annot.type,
                                               annot.info,
                                               annot.xref,
                                               annot.irt_xref,
                                               annot_rect,
                                               line_bb,
                                               surrounding_lines))
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

def getSelection(ann, doc):
    """return an annotation's selected text (and the bounding boxes for debugging purposes)"""
    buff = EXTRACT_TEXT_BUFFER_WIDTH
    selection_name = ann.type[1]
    page = doc[ann.pageno]
    # if there's no supplied line_bb for the annotation, just extend the annotation's rectangle across the width of the page
    if ann.line_bb == None:
        x0, y0, x1, y1 = 0, ann.rect.y0, page.rect.width, ann.rect.y1
    else:
        x0, y0, x1, y1 = ann.line_bb

    # as of this moment, surrounding lines are not added/considered

    ann_rect = pymupdf.Rect(x0, y0, x1, y1)
    
    if selection_name == PDF_ANNOT_CARET[1]:
        insertion_point_x = ann.rect.x0 + ann.rect.width/2
        left_rect = pymupdf.Rect(x0, y0, insertion_point_x-CARET_BUFF, y1)
        right_rect = pymupdf.Rect(insertion_point_x+CARET_BUFF, y0, x1, y1)
        return '{left}<Caret></Caret>{right}'.format(left = page.get_textbox(left_rect),
                                                     right = page.get_textbox(right_rect)), (left_rect, right_rect), ann_rect

    elif selection_name in SELECT_TEXT_ANNOTS:
        left_rect = pymupdf.Rect(x0, y0, ann.rect.x0-buff, y1)
        middle_rect = pymupdf.Rect(ann.rect.x0+buff/2, y0, ann.rect.x1-buff/2, y1)
        right_rect = pymupdf.Rect(ann.rect.x1+buff, y0, x1, y1)
        return '{left}<{name}>{middle}</{name}>{right}'.format(left = page.get_textbox(left_rect),
                                                               middle = page.get_textbox(middle_rect),
                                                               right = page.get_textbox(right_rect),
                                                               name = selection_name), (left_rect, middle_rect, right_rect), ann_rect
    else:
        return None
    
def getEdits(filename):
    """return a list of Edits. See class Edit."""
    doc = pymupdf.open(filename)
    robust_annots = getRobustAnnots(doc)
    all_responses = getAllResponses(robust_annots)

    target_num_edits = 0
    logging.info("Turning annotations into edits...")
    edits = []
    for pageno, page in enumerate(doc):
        for annot in robust_annots[pageno]:
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine
                # with another to make an annotation of type 'Replace'
                continue
            target_num_edits += 1
            
            responses = getResponses(annot, all_responses)
            text_responses = responses[PDF_ANNOT_TEXT] if PDF_ANNOT_TEXT in responses else []
            text_responses = [resp.info['content'] for resp in text_responses]
            message = {'comment': annot.info['content'], 'responses': text_responses}            

            def isReplaceAnnot(ann, ann_resps):
                if not (ann.type == PDF_ANNOT_STRIKE_OUT or ann.type == PDF_ANNOT_CARET) or ann_resps == []:
                    return False, None
                
                assert ann.type not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = PDF_ANNOT_STRIKE_OUT if ann.type == PDF_ANNOT_CARET else PDF_ANNOT_CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False, None
                other_ann = ann_resps[other_ann_type][0]

                return ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == '', other_ann
                
            is_replace, other_ann = isReplaceAnnot(annot, responses)
            
            if is_replace:
                if annot.type == PDF_ANNOT_CARET:
                    annot.rect = other_ann.rect
                annot.type = (None, 'Replace')

            res = getSelection(annot, doc)
            if res is None:
                # I don't think I've seen this happen before in testing, so 
                logging.warning("getSelection() returned None; skipping---did not produce an edit for this annotation")
                continue
            
            selection_text, selection_bbs, selection_line_rect = getSelection(annot, doc)
            edits.append(Edit(annot.pageno, annot.type[1], message, selection_text, selection_bbs, selection_line_rect))
        logging.info(f"Extracted annotations on page {pageno:3d}/{doc.page_count-1:3d}")
        
    logging.info(f"Produced {len(edits)} edits from {target_num_edits} PDF annotations")
    return edits
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python extract.py',
                                     description = 'Return edits from annotated pdf as json')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    edits = getEdits(filename)
    for edit in edits:
        print(edit)
