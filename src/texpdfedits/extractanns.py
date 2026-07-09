import pymupdf
import json
import argparse
import logging
from icecream import ic
logger = logging.getLogger(__name__)
import math
import re
from dataclasses import dataclass
from typing import ClassVar

import texpdfedits.utils as utils

pymupdf.TOOLS.set_small_glyph_heights(True)

# how many characters to include on either side of what was selected by an annotation
NUM_SELECTION_CONTEXT_CHARS = 12

# words to add before and after which are not selected    
NUM_CONTEXT_WORDS = 2 

# instead of iterating through every character on the page
# to get the selection text of a single annotation, limit
# the chars to those within 12 points above and below the
# annotation
PAGE_GET_TEXT_VERT_BEFORE_AFTER = 15

# for adjust annots option
CMR10_ADJUST = 2.75 # in points
STIX_ADJUST = 4

USE_STIX = utils.PDF_WORKFLOW

EXPECT_NO_IRT_KEY = '|'.join(
    r'popup',
)

class Annot:
    """
    Revised version of pymupdf's Annot which adjusts the bounding box of the
    Caret annotation to suit my purposes and creates annotations which aren't
    fragile. See getRobustAnnots() for more.
    
    Though if there's already something in pymupdf which separates the annot
    from the page, this should be removed and the code refactored.
    """
    TEXT = 0
    LINK = 1  # <=== Link object in PyMuPDF
    FREE_TEXT = 2
    LINE = 3
    SQUARE = 4
    CIRCLE = 5
    POLYGON = 6
    POLY_LINE = 7
    HIGHLIGHT = 8
    UNDERLINE = 9
    SQUIGGLY = 10
    STRIKE_OUT = 11
    REDACT = 12
    STAMP = 13
    
    CARET = 14
    CARET_NAME = 'Caret'
    
    INK = 15
    POPUP = 16
    FILE_ATTACHMENT = 17
    SOUND = 18
    MOVIE = 19
    RICH_MEDIA = 20
    WIDGET = 21  # <=== Widget object in PyMuPDF
    SCREEN = 22
    PRINTER_MARK = 23
    TRAP_NET = 24
    WATERMARK = 25
    _3D = 26
    PROJECTION = 27
    UNKNOWN = -1

    # not part of pymupdf definitions
    REPLACE = 28
    REPLACE_NAME = 'Replace'
    
    REMOVE = 29
    REMOVE_NAME = 'Delete'

    TEXT_SELECT_ANNOTS = {
            HIGHLIGHT,
            STRIKE_OUT,
            SQUIGGLY,
            UNDERLINE,
            REPLACE,
            REMOVE,
        }            
    
    def __init__ (
            self,
            pageno: int,
            page_label: str,
            type: tuple[int, str],
            info: dict,
            xref: int,
            irt_xref: int,
            rect: pymupdf.Rect,
            vertices: list[list[pymupdf.Point]]
    ): 
        self.pageno = pageno
        self.page_label = page_label
        self.type = type
        self.info = info                
        self.xref = xref
        self.irt_xref = irt_xref
        self.rect = rect
        self.vertices = vertices
        
    def __str__ (self):
        return str(
            {
                'pageno':self.pageno,
                'pagelabel':self.page_label,
                'type':self.type,
                'info':self.info['content'],
                'rect':self.rect,
             }
        )
    
    def __repr__ (self):
        return str(
            {
                'pageno':self.pageno,
                'pagelabel':self.page_label,                
                'type':self.type,
                'info':self.info,
                'xref':self.xref,
                'irt_xref':self.irt_xref,
                'rect':self.rect,
                'vertices':self.vertices,
             }
        )
    
@dataclass
class XrefObj:
    FLAG_IN_USE: ClassVar[str] = '30'
    
    MOD_KEY: ClassVar[str] = 'M'
    TITLE_KEY: ClassVar[str] = 'T' # "Human readable title" Adobe acrobat writes the user name here
    IRT_KEY: ClassVar[str] = 'IRT' # In response to xref
    FLAG_KEY: ClassVar[str] = 'F' # flag tells whether the object is in use or free
    STATE_MODEL_KEY: ClassVar[str] = 'StateModel'
    STATE_KEY: ClassVar[str] = 'State'
    
    CHECKMARK_MODEL: ClassVar[str] = 'Marked'
    STATUS_MODEL: ClassVar[str] = 'Review'
    
    CHECKED: ClassVar[str]   = 'Marked'
    UNCHECKED: ClassVar[str] = 'Unmarked'
    
    STATUS_NONE: ClassVar[str]      = 'None'
    STATUS_ACCEPTED: ClassVar[str]  = 'Accepted'
    STATUS_REJECTED: ClassVar[str]  = 'Rejected'
    STATUS_CANCELLED: ClassVar[str] = 'Cancelled'
    STATUS_COMPLETED: ClassVar[str] = 'Completed'
    STATUS_DEFERRED: ClassVar[str]  = 'Deferred'
    STATUS_FUTURE: ClassVar[str]    = 'Future'
    
    xref: int
    state_model: str
    state: str

def get_xref_mod_time(doc: pymupdf.Document, xref: int) -> str:
    type, val = doc.xref_get_key(xref, XrefObj.MOD_KEY)
    return val

def get_xref_state(doc: pymupdf.Document, xref: int) -> str:
    type, val = doc.xref_get_key(xref, XrefObj.STATE_KEY)
    return val
    
def get_xref_statemodel(doc: pymupdf.Document, xref: int) -> str:
    type, val = doc.xref_get_key(xref, XrefObj.STATE_MODEL_KEY)
    return val    

@dataclass
class Edit:
    """
    Represents the information necessary to carry out an edit.
    An edit has the following attributes:
    
    "pageno": the page number the PDF annotation appears on 
    
    "type": annotation type (same as in Annot)
    
    "message": text in the annotation comment box and responses to it
        it is a dict where
        message['comment'] = str of original comment in comment box
        message['responses'] = list[str] of responses in order of creation date
    
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
    pageno: int
    page_label: str
    type: tuple[int, str]
    message: dict[str, str | list[str]]
    selection: str
    selection_bbs: list[pymupdf.Rect] # for debugging
    annot_rect: pymupdf.Rect # used in marktex routines
    xref: int
    related_xref: int
    checkmark: XrefObj
    status: XrefObj
        
    def __str__ (self): 
        return json.dumps({
            "pageno": self.pageno,
            "xref": self.xref,
            "related_xref": str(self.related_xref),
            "checkmark": str(self.checkmark),
            "status": str(self.status),
            "page_label": self.page_label,             
            "type": self.type, 
            "message": {
                "comment": self.message['comment'],
                "responses": self.message['responses']
            },
            "PDF text selection": self.selection
        }, indent=4, ensure_ascii=False)

def pageGetTextClipRect(annot_rect: pymupdf.Rect, page_rect: pymupdf.Rect):
    return pymupdf.Rect(
        page_rect.x0,
        annot_rect.y0 - PAGE_GET_TEXT_VERT_BEFORE_AFTER,
        page_rect.x1,
        annot_rect.y1 + PAGE_GET_TEXT_VERT_BEFORE_AFTER
    )

def adjustCaretRect(caret_rect: pymupdf.Rect, page):
    """
    The bounding boxes of the original caret annotations often extend below the line they
    were inserted on, so they are resized to prevent that.
    """
    CARET_V_PROPORTION = 0.2
    CARET_H_PROPORTION = 0.2

    (x0, y0, x1, y1) = caret_rect

    # do simple adjustment
    extension = CARET_V_PROPORTION * (y1 - y0)
    caret_rect.y1 = y0 + extension
    caret_rect.y0 = y0 - 0.75 * extension
    
    # check intersecting spans
    raw_dict_rect = pageGetTextClipRect(caret_rect, page.rect)
    raw_dict = page.get_text('rawdict', sort=True, clip=raw_dict_rect)
    intersecting_spans = []
    for block in raw_dict.get('blocks'):
        if block.get('lines') is None:
            continue        
        for line in block.get('lines'):
            for span in line.get('spans'):
                if caret_rect.intersects(span['bbox']):
                    intersecting_spans.append(span)
    if len(intersecting_spans) != 1:
        SIMPLE_ADJUST = 3 # in points
        return pymupdf.Rect(
            caret_rect.x0,
            caret_rect.y0-SIMPLE_ADJUST,
            caret_rect.x1,
            caret_rect.y1+SIMPLE_ADJUST
        )
    # set to span's true font height
    else:
        span = intersecting_spans[0]
        a, d, o = span['ascender'], span['descender'], pymupdf.Point(span['origin'])
        r = pymupdf.Rect(span['bbox'])
        descending_ammt = span['size'] * d / (a - d)
        y1 = o.y - descending_ammt
        y0 = y1 - span['size']
        return pymupdf.Rect(caret_rect.x0, y0, caret_rect.x1, y1)

def getRobustAnnots(pdf_file: Path, **opt):
    """
    pymupdf's annotations are kind of fragile---they are
    strongly bound to the page they come from (so when
    the page goes away, so does the annotation), and I've
    encountered issues with using the provided methods
    to update annotation attributes, so I'll just store the
    annotations with my own class which isn't tied to the page.
    """

    # Previously, the x positions of the annotations have been
    # accurate, but now I'm encountering annotations from another
    # tool whose left and right x coordinates are significantly
    # wider than the actual selected text.
    #
    # For now, I'm trying this very hacky and extremely simple
    # and specific response where I just remove a flat ammount
    # from either side. I need to investigate where this
    # discrepancy comes from, but but this has been working
    # surprisingly well so far.
    #
    # But this hack only works (if therere's a problem to begin
    # with and) if the font is cmr10 (or maybe 11 or 12,
    # I don't recall)
    doc = pymupdf.open(pdf_file)
    adjust_annots = opt['adjust_annots']

    if adjust_annots:
        uses_stix = re.search('|'.join(USE_STIX), pdf_file.name, flags=re.IGNORECASE) is not None
        if uses_stix:
            logger.info("Adjusting annots for STIX2")
            annot_adjustment = STIX_ADJUST
        else:
            logger.info("Adjusting annots for cmr10")
            annot_adjustment = CMR10_ADJUST
    
    robust_annots = {pageno:[] for pageno in range(doc.page_count)}
    for pageno, page in enumerate(doc):
        page_label = page.get_label()
        if not page_label:
            page_label = str(pageno+1)
        for annot in page.annots():
            new_ann_rect = pymupdf.Rect(
                annot.rect.top_left,
                annot.rect.bottom_right
            )
            if annot.type[0] == Annot.TEXT:
                robust_annots[pageno].append(
                    Annot(
                        pageno,
                        page_label,
                        annot.type,
                        annot.info,
                        annot.xref,
                        annot.irt_xref,
                        new_ann_rect,
                        annot.vertices
                    )
                )
                continue
            (x0, y0, x1, y1) = new_ann_rect
            
            if annot.type[0] == Annot.CARET:
                new_ann_rect = adjustCaretRect(new_ann_rect, page)

                
            if adjust_annots and annot.type[0] != Annot.CARET:
                # logging.debug(f"before horizontal hack: {new_ann_rect}")                
                new_ann_rect.x0 += annot_adjustment
                new_ann_rect.x1 -= annot_adjustment
                if not new_ann_rect.is_valid:
                    logger.debug(f"annot on page {pageno+1} not valid after adjustment")
                    while not new_ann_rect.is_valid:
                        new_ann_rect.x0 -= 1
                        new_ann_rect.x1 += 1
                # logging.debug(f"after horizontal hack: {new_ann_rect}")

            robust_annots[pageno].append(
                Annot(pageno,
                      page_label,
                      annot.type,
                      annot.info,
                      annot.xref,
                      annot.irt_xref,
                      new_ann_rect,
                      annot.vertices)
            )
    return robust_annots

def getAllResponses(
        robust_annots: dict[int, list[Annot]],
) -> dict[int, list[Annot]]:
    """return dictionary where dict[xref]
           => [annots for which annot.irt_xref == xref]
    i.e., values are list of annots that are in response
    to xref key
    """
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

def getResponses(in_annot, all_responses) -> dict:
    """
    return dictionary where dict[TYPE_CONST] =>
    list of annots where annot.type[0] == TYPE_CONST
    and are a response to in_annot
    """
    if in_annot.xref not in all_responses:
        return dict()

    resps_by_type = dict()
    for resp in all_responses[in_annot.xref]:
        if resp.type[0] not in resps_by_type:
            resps_by_type[resp.type[0]] = [resp]
        else:
            resps_by_type[resp.type[0]].append(resp)

    for ann_type0, resps in resps_by_type.items():
        # sort responses by creation date
        resps_by_type[ann_type0] = sorted(
            resps,
            key = lambda r: r.info['creationDate']
        ) 
    
    return resps_by_type

def getAnnotRects(annot: Annot):
    default = [annot.rect]
    if annot.type[0] not in Annot.TEXT_SELECT_ANNOTS:
        return default
    if annot.vertices is None:
        return default
    if len(annot.vertices) % 4 != 0:
        logger.error( # error because this shouldn't happen for text_select_annots
            f"Multiline annotation vertex count was not a "
            f"multiple of four for annot type {annot.type}"
        )
        return default
    
    multiline_rects = [
        pymupdf.Rect(annot.vertices[i], annot.vertices[i+3])
        for i in range(0, len(annot.vertices), 4)
    ]

    # validate
    to_remove = []
    for rect in multiline_rects:
        if not rect.is_valid:
            logger.debug(
                "Rectangle in multiline annotation on "
                f"page {annot.pageno+1} was not valid {rect}"
            )
            to_remove.append(rect)
            
    for remove in to_remove:
        multiline_rects.remove(remove)

    if not multiline_rects:
        logger.warning(
            "None of the individual rects in multiline annotations"
            f" on page {annot.pageno+1} were valid {annot.info}"
        )
        return default

    return multiline_rects

def getCharCenter(char: dict[str, tuple | str]) -> pymupdf.Point:
    x0, y0, x1, y1 = char['bbox'] 
    return pymupdf.Point(x0 + (x1 - x0)/2, y0 + (y1 - y0)/2)

def AnnotRectsContainChar(
        annot_rects: list[pymupdf.Rect],
        char: dict[str, tuple | str]
):
    char_center = getCharCenter(char)
    for rect in annot_rects:
        if rect.contains(char_center): #or rect.contains(pymupdf.Point(char['origin'])):
            return True
    return False

def charPosRelativeToCaret(
        caret_rect: pymupdf.Rect,
        char: dict[str, tuple | str]
):
    """
    Return 0 if char is not in vertical span of caret_rect
    Return 1 if char is in vertical span and
    is TO THE LEFT  of caret center
    Return 2 if char is in vertical span and
    is TO THE RIGHT of caret center

    If the caret is at the beginning of a line,
    there should be a 0 to 2
    If the caret is in the middle of a line,
    there should be a 1 to 2
    If the caret is at the end of a line,
    there should be a 1 to 0
    """
    char_center = getCharCenter(char)
    if not (caret_rect.y0 <= char_center.y <= caret_rect.y1):
        return 0
    caret_center_x = get2DCenter(caret_rect)[0]
    return 1 if char_center.x < caret_center_x else 2

def charsIterator(page_rawdict):
    for block in page_rawdict.get('blocks'):
        if block.get('lines') is None:
            continue
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    yield char

def pointDistance(p1: tuple, p2: tuple):
    return math.hypot(*[a - b for a, b in zip(p1, p2)])

def closestToCaret(
        caret_rect: pymupdf.Rect,
        inds_and_chars: list[tuple[int, dict]]
):
    caret_center = get2DCenter(caret_rect)
    m = (float('inf'), -1)
    for (idx, char) in inds_and_chars:
        char_center = get2DCenter(pymupdf.Rect(char['bbox']))
        dist = pointDistance(caret_center, char_center)
        if dist < m[0]:
            m = (dist, idx)
    return m[1]

def caretSelectionText(caret_annot, page_rawdict):
    caret_rect = caret_annot.rect
    page_chars = [
        char for char in charsIterator(page_rawdict)
    ]
    relpos_string = [
        charPosRelativeToCaret(caret_rect, char)
        for char in page_chars
    ]
    
    # (idx, char) tuples where idx is left of Caret center and idx+1 is right of Caret center    
    transitions = {
        'mid-line': [],
        'start-line': [],
        'end-line': []
    }

    def addTransition(key, idx):
        transitions[key].append((idx, page_chars[idx]))

    prev = relpos_string[0]
    
    # maybe useful to consider in the future    
    in_vertical_span_indices = [0] if prev > 0 else []
    
    num_page_chars = len(relpos_string)
    
    for i, trit in enumerate(relpos_string):
        if i == 0:
            continue
        prev_idx = i-1
        if prev == 1 and trit == 2:
            addTransition('mid-line', prev_idx)
        elif prev == 0 and trit == 2:
            addTransition('start-line', prev_idx)
        elif prev == 1 and trit == 0:
            addTransition('end-line', prev_idx)
        # it is inserted at the very end of the page            
        elif prev == 1 and trit == 1 and i == num_page_chars-1:
            addTransition('end-line', i)
        if trit > 0:
            in_vertical_span_indices.append(i)
        prev = trit

    all_transitions = [
        pair
        for key in transitions for pair in transitions[key]
    ]
            
    if len(all_transitions) == 0:
        logger.error(f"No caret point detected in {caret_annot}")
        return None
    elif len(all_transitions) > 1:
        logger.debug(f"Multiple insertion indices detected in {caret_annot}")        
        insertion_index = closestToCaret(caret_rect, all_transitions)
    else:
        insertion_index, _ = list(all_transitions)[0]

    # needs rewriting probably    
    page_chars_with_synthetic = []
    synthetic_insert_indices = []
    i, synth_idx = 0, 0
    caret_tag = f'<{Annot.CARET_NAME}>'

    def addSyntheticSpace():
        nonlocal synth_idx
        page_chars_with_synthetic.append(' ')
        synth_idx += 1
        
    for block in page_rawdict.get('blocks'):
        if block.get('lines') is None:
            continue        
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    page_chars_with_synthetic.append(char['c'])
                    synth_idx += 1                    
                    if i == insertion_index:
                        page_chars_with_synthetic.append(caret_tag)
                        synthetic_insert_indices.append(synth_idx)
                        synth_idx += len(caret_tag)
                    i += 1
            addSyntheticSpace()
        addSyntheticSpace()

    assert len(synthetic_insert_indices) == 1
    first_insertion = min(synthetic_insert_indices)
    last_insertion = max(synthetic_insert_indices)

    start_with_context = first_insertion - NUM_SELECTION_CONTEXT_CHARS
    end_with_context = last_insertion + NUM_SELECTION_CONTEXT_CHARS

    if start_with_context >= 0:
        start_char_idx = start_with_context
    else:
        start_char_idx = first_insertion
        
    # start_char_idx = start_with_context if start_with_context >= 0 else first_insertion

    # string [:] retrieval will only ever go as high as it can,
    # there's no issue with giving an upper index out of range
    return ''.join(page_chars_with_synthetic[start_char_idx:end_with_context+1])
    
def newGetSelectionText(annot: Annot, page_rawdict, page_words):
    """
    We iterate through the characters on the page and check
    if it's center (origin) is inside of the annotation.

    So we have two states 0 = outside annotation rectangle
    and 1 = inside annotation rectangle, so iterating through
    the characters gives us binary string. The sequence 01
    (with, say, characters ab) corresponds to the start of the
    tag at `a(b`, and the sequence 10 corresponds to the closing
    tag `a)b` so 010 would make
        a(b)c,
    and 0 1111 0 1 00 1 0 would make
        a(bcde)f(g)hi(j)k

    There's a different logic for caret annotations since they don't
    really 'select' text. They just mark a point between characters
    """
    if annot.type[0] == Annot.CARET:
        return caretSelectionText(annot, page_rawdict)
    
    intersecting_words = [
        word for
        word in page_words
        if annot.rect.intersects(pymupdf.Rect(word[0:4]))
    ]
    
    line_nos = set(iw[6] for iw in intersecting_words)

    if len(line_nos) > 1:
        annot_rects = getAnnotRects(annot)
    else:
        annot_rects = [annot.rect]

    containment_sequence = [
        AnnotRectsContainChar(annot_rects, char)
        for char in charsIterator(page_rawdict)
    ]

    open_tag_transitions  = set()
    close_tag_transitions = set()
    prev_in = None
    for i, curr_in in enumerate(containment_sequence):
        if prev_in is None and curr_in:
            # first char of the page in selection            
            open_tag_transitions.add(0)
            assert i == 0
        elif not prev_in and curr_in:
            open_tag_transitions.add(i)
        elif prev_in and not curr_in:
            close_tag_transitions.add(i-1)
            
        if curr_in and i == len(containment_sequence)-1:
            # last char of the page in selection            
            close_tag_transitions.add(i)
        prev_in = curr_in

    tag_name = utils.SELECTION_TAG
    annot_tags = {
        'open': rf'<{tag_name}>',
        'close': rf'</{tag_name}>'
    }
    
    annotated_pdf_text = []
    i, synth_idx = 0, 0
    
    def addSyntheticSpace():
        nonlocal synth_idx
        annotated_pdf_text.append(' ')
        synth_idx += 1

    insert_indices = []
    for block in page_rawdict.get('blocks'):
        if block.get('lines') is None:
            continue
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    # can definitely refactor this
                    if i in open_tag_transitions and i not in close_tag_transitions:
                        tag_text = annot_tags['open']
                        annotated_pdf_text.append(tag_text)
                        insert_indices.append(synth_idx)
                        synth_idx += 1
                        
                        annotated_pdf_text.append(char['c'])
                        synth_idx += 1
                        i += 1                        
                        
                    elif i in close_tag_transitions and i not in open_tag_transitions:
                        annotated_pdf_text.append(char['c'])
                        synth_idx += 1
                        i += 1

                        tag_text = annot_tags['close']
                        annotated_pdf_text.append(tag_text)
                        synth_idx += 1                        
                        insert_indices.append(synth_idx)

                    elif i in open_tag_transitions and i in close_tag_transitions:
                        tag_text = annot_tags['open']
                        annotated_pdf_text.append(tag_text)
                        insert_indices.append(synth_idx)
                        synth_idx += 1
                        
                        annotated_pdf_text.append(char['c'])
                        synth_idx += 1
                        i += 1
                        
                        tag_text = annot_tags['close']
                        annotated_pdf_text.append(tag_text)
                        synth_idx += 1                        
                        insert_indices.append(synth_idx)
                        
                    else:
                        annotated_pdf_text.append(char['c'])
                        synth_idx += 1
                        i += 1
            addSyntheticSpace()
        addSyntheticSpace()
        
    if not insert_indices:
        if annot.type[0] in Annot.TEXT_SELECT_ANNOTS:
            logger.debug(f"Did not find insert indices for {annot}")
        # print(annot_rects)
        return (f'None, annot.type = <{annot.type[1]}>', annot_rects)
    
    first_tag_insert_idx = insert_indices[0]
    last_tag_insert_idx  = insert_indices[-1]

    # logger.info(f"{''.join(annotated_pdf_text[first_tag_insert_idx:last_tag_insert_idx])}")

    left_text  = ''.join(annotated_pdf_text[:first_tag_insert_idx])
    middle_text = ''.join(annotated_pdf_text[first_tag_insert_idx:last_tag_insert_idx])
    right_text = ''.join(annotated_pdf_text[last_tag_insert_idx:])

    to_left = left_text.split(' ')

    idx = len(to_left) - 1
    nonspace_seen = 0
    while idx >= 0 and nonspace_seen < NUM_CONTEXT_WORDS:
        if re.match(r'^\s*$', to_left[idx]) is None:
            nonspace_seen += 1
        idx -= 1

    left_include = to_left[idx+1:]

    to_right = right_text.split(' ')
    idx = 0
    nonspace_seen = 0
    while idx < len(to_right) and nonspace_seen < NUM_CONTEXT_WORDS:
        if re.match(r'^\s*$', to_right[idx]) is None:
            nonspace_seen += 1
        idx += 1
    right_include = to_right[:idx]

    return (' '.join(left_include) + ''.join(middle_text) + ' '.join(right_include), annot_rects)

def get2DCenter(rect):
    return (rect.x0 + rect.width / 2, rect.y0 + rect.height/2)

def getSelection(
        annot: Annot,
        page_words: list[tuple[int, int, int, int, str, int, int, int]],
        doc: pymupdf.Document
):
    """
    Return: annotation's selected text,
            rectangle for latex source extraction,
            selection bounding boxes for debugging

    page_words is list where
    word[0] = x0: float
    word[1] = y0: float
    word[2] = x1: float
    word[3] = y1: float
    word[4] = pdf text: str
    word[5] = block_no: int
    word[6] = line_no: int
    word[7] = word_no: int
    """
    page = doc[annot.pageno]
    intersecting_words = []

    raw_dict_rect = pageGetTextClipRect(annot.rect, page.rect)
    page_rawdict = page.get_text('rawdict', sort=True, clip=raw_dict_rect)

    # <<< 0.10.1
    # ===============================
    if annot.type[0] == Annot.CARET:
        caret_rect = annot.rect
        caret_center_x = get2DCenter(caret_rect)[0]
        sel_bbs = [
            [pymupdf.Rect(
                caret_center_x,
                caret_rect.y0,
                caret_center_x+.5,
                caret_rect.y1), pymupdf.Rect(0,0,.1,.1)]
        ]
        return (
            newGetSelectionText(
                annot,
                page_rawdict,
                page_words
            ),
            sel_bbs,
            annot.rect
        )
    else:
        selection, annot_rects = newGetSelectionText(
            annot,
            page_rawdict,
            page_words
        )
        return selection, annot_rects, annot.rect

def get_irt_from_doc(doc: pymupdf.Document, xref: int) -> int | None:
    xref_keys = ' '.join(doc.xref_get_keys(xref))
    irt_key = XrefObj.IRT_KEY
    if irt_key not in xref_keys:
        logger.debug(f'{irt_key} not in {xref_keys}')
        return None
    raw_irt = doc.xref_get_key(xref, irt_key)
    type, val = raw_irt
    try:
        if type != 'xref':
            raise ValueError(f"Expected type = 'xref', instead type = {type}")
        return int(val.split(' ')[0])
    except Exception as e:
        logger.error(
            f"Could not read irt_val '{val}' from xref "
            f"'{xref}' in Document '{doc}': {e}"
        )
        return None

def to_xref_obj(doc: pymupdf.Document, xref: int) -> XrefObj:
    return XrefObj(
        xref,
        get_xref_statemodel(doc, xref),
        get_xref_state(doc, xref),
    )

def get_ann_xref_resps(
        doc: pymupdf.Document,
        page: pymupdf.Page,
) -> dict[int, list[XrefObj]]:
    """
    Return dictionary where
            key: xref that belongs to an annotation
            value: list of text annotation xref objects in response to it
                   (typically annotations that represent checkmark or status)
    """
    xref_keys = [
        xref for xref, type, name in page.annot_xrefs()
        if type != Annot.LINK and type != Annot.POPUP # no need for these, never used
    ]
    text_xrefs = [
        xref for xref, type, name in page.annot_xrefs()
        if type == Annot.TEXT
    ]
    return {
        x_key : [
            to_xref_obj(doc, txref) for txref in text_xrefs
            if get_irt_from_doc(doc, txref) == x_key
        ] for x_key in xref_keys
    }
    return res

def _get_checkmark(
        annot_xref: int,
        doc: pymupdf.Document,
        ann_xref_resps: dict[int, list[XrefObj]],
) -> XrefObj | None:
    checkmarks = [
        resp_tann_xref for resp_tann_xref in ann_xref_resps[annot_xref]
        if resp_tann_xref.state_model == XrefObj.CHECKMARK_MODEL
    ]
    if not checkmarks:
        return None
    elif len(checkmarks) == 1:
        [checkmark_xref_obj] = checkmarks
    else:
        logger.error(
            f"Malformed PDF annotations: xref {annot_xref} "
            f"has multiple checkmark annotations {checkmarks}"
        )
        checkmark_xref_obj = max(
            checkmarks, # use last modified one
            key=lambda xr_obj: get_xref_mod_time(doc, xr_obj.xref)
        )
    return checkmark_xref_obj

def _get_status(
        annot_xref: int,        
        doc: pymupdf.Document,
        ann_xref_resps: dict[int, list[XrefObj]],
) -> XrefObj | None:
    status_xref_obj = None
    parent_xref = annot_xref
    children_ta_xref_objs = ann_xref_resps[parent_xref]
    
    while children_ta_xref_objs:
        # For some reason Adobe will put status annotation in response to the check mark ones
        # if one already exists. This is a little bewildering
        statuses = [
            ta_xref_obj for ta_xref_obj in children_ta_xref_objs
            if (ta_xref_obj.state_model == XrefObj.STATUS_MODEL or
                ta_xref_obj.state_model == XrefObj.CHECKMARK_MODEL)
        ]
        if not statuses:
            break
        elif len(statuses) == 1:
            [status_xref_obj] = statuses
        else:
            logger.error(
                f"Malformed PDF annotations: xref {parent_xref} "
                f"has multiple status annotations {statuses}"
            )
            status_xref_obj = max(
                statuses,
                key=lambda xr_obj: get_xref_mod_time(doc, xr_obj.xref),
            )
        parent_xref = status_xref_obj.xref
        children_ta_xref_objs = ann_xref_resps[parent_xref]
    only_checkmark_and_no_status = (
        status_xref_obj is not None and
        status_xref_obj.state_model == XrefObj.CHECKMARK_MODEL
    )
    if only_checkmark_and_no_status:
        return None
    return status_xref_obj

def getEdits(pdf_file: Path, **opt) -> tuple[list[Edit], int]:
    """return a list of Edits. See class Edit."""
    logger.info("Loading PDF annotations...")
    robust_annots = getRobustAnnots(pdf_file, **opt)
    all_responses = getAllResponses(robust_annots)
    logger.info("Done")

    target_num_edits = 0
    logger.info("Turning annotations into edits...")
    num_not_for_comp = 0
    edits = []

    doc = pymupdf.open(pdf_file)    
    num_pages_with_annots_to_extract = len([
        pageno for pageno, _ in enumerate(doc)
        if robust_annots[pageno]
    ])

    bar = utils.TextProgressBar(num_pages_with_annots_to_extract)
    bar.showSize()
    
    for pageno, page in enumerate(doc):
        ann_xref_resps = get_ann_xref_resps(doc, page)
        for annot in robust_annots[pageno]:
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine
                # with another to make an annotation of type 'Replace'
                continue
            
            # For some reason sometimes a text annotation will not be in response to anything but it
            # will have xref key 'StateModel'
            annot_statemodel = get_xref_statemodel(doc, annot.xref)
            if annot_statemodel == XrefObj.STATUS_MODEL or annot_statemodel == XrefObj.CHECKMARK_MODEL:
                continue
            
            target_num_edits += 1
            
            responses = getResponses(annot, all_responses)
            
            checkmark_xref_obj = _get_checkmark(annot.xref, doc, ann_xref_resps)
            status_xref_obj = _get_status(annot.xref, doc, ann_xref_resps)

            text_responses = responses.get(Annot.TEXT, [])
            text_responses = [
                resp.info['content'] for resp in text_responses
                if get_xref_statemodel(doc, resp.xref) == 'null'
                # normal text annotations for replies don't have xref_object key 'StateModel' defined
            ]
            
            message = {
                'comment': annot.info['content'],
                'responses': text_responses
            }

            def isReplaceAnnot(ann, ann_resps):
                if not (ann.type[0] == Annot.STRIKE_OUT or ann.type[0] == Annot.CARET) or ann_resps == []:
                    return False, None
                
                assert ann.type[0] not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type[0]]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = Annot.STRIKE_OUT if ann.type[0] == Annot.CARET else Annot.CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False, None
                other_ann = ann_resps[other_ann_type][0]

                if not (ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == ''):
                    return False, None
                return True, other_ann
                
            is_replace, other_ann = isReplaceAnnot(annot, responses)

            if other_ann is not None:
                related_xref = other_ann.xref
            else:
                related_xref = None
            
            if is_replace:
                if annot.type[0] == Annot.CARET:
                    annot.rect = other_ann.rect
                    annot.vertices = other_ann.vertices
                annot.type = (Annot.REPLACE, Annot.REPLACE_NAME)

            # rename strikeout to remove
            if annot.type[0] == Annot.STRIKE_OUT:
                annot.type = (Annot.REMOVE, Annot.REMOVE_NAME)

            page_words_rect = pageGetTextClipRect(annot.rect, page.rect)
            page_words = page.get_text('words', sort=True, clip=page_words_rect)
            # the sort option doesn't actually sort in lexicographic order... maybe it does it by rectangle positions.
            page_words = list(sorted(page_words, key = lambda w: (w[5], w[6], w[7])))
            
            selection_text, selection_bbs, latex_extraction_bb = getSelection(annot, page_words, doc)
            
            if selection_text is None:
                continue

            selection_text = utils.UnicodeToTeX(selection_text)
            
            edits.append(Edit(
                annot.pageno,
                annot.page_label,
                annot.type,
                message,
                selection_text,
                selection_bbs,
                latex_extraction_bb,
                annot.xref,
                related_xref,
                checkmark_xref_obj,
                status_xref_obj,
            ))

        if robust_annots[pageno]:
            bar.addProgress()
    bar.end()
        
    logger.info(
        f"Created {len(edits)} edit{utils.plural(len(edits))} from "
        f"{target_num_edits} PDF annotations"
    )
    return edits, target_num_edits
