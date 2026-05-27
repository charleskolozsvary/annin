"""Extract annotations from PDF"""
import logging
logger = logging.getLogger(__name__)

import pymupdf
import json
import argparse
import math
import re
from icecream import ic
from enum import Enum

import texpdfedits.utils as utils

# see https://pymupdf.readthedocs.io/en/latest/textpage.html
pymupdf.TOOLS.set_small_glyph_heights(True)

# how many characters to include on either side of caret annotation
NUM_SELECTION_CONTEXT_CHARS = 24

# words to add before and after which are not selected
NUM_CONTEXT_WORDS = 4

# instead of iterating through every character on the page
# to get the selection text of a single annotation, limit
# the chars to those within the given constant number of
# points above and below the annotation
GET_PAGE_TEXT_VERT_SPAN = 15

# in points
CMR10_ADJUST = 2.75
STIX_ADJUST = 4

NUM_VERTICES_PER_RECT = 4

WORD_LINE_NO_IDX = 6
WORD_COORDINATES_END_IDX = 4

MAX_SELECTION_LEN = 150

class AnnotType(Enum):
    """
    I don't know if all of the string versions are
    quite what PyMuPDF saves them as, and, regardless,
    I don't use them for comparison and intend to 
    customize the string representation if needed
    """
    TEXT            = (0, 'Text')
    LINK            = (1, 'Link')  # <=== Link object in PyMuPDF
    FREE_TEXT       = (2, 'FreeText')
    LINE            = (3, 'Line')
    SQUARE          = (4, 'Square')
    CIRCLE          = (5, 'Circle')
    POLYGON         = (6, 'Polygon')     
    POLY_LINE       = (7, 'Polyline')    
    HIGHLIGHT       = (8, 'Highlight')    
    UNDERLINE       = (9, 'Underline')    
    SQUIGGLY        = (10, 'Squiggly')    
    STRIKE_OUT      = (11, 'Strikeout')
    REDACT          = (12, 'Redact')
    STAMP           = (13, 'Stamp')        
    CARET           = (14, 'Caret')
    INK             = (15, 'Ink')        
    POPUP           = (16, 'Popup')
    FILE_ATTACHMENT = (17, 'FileAttachment')
    SOUND           = (18, 'Sound')
    MOVIE           = (19, 'Movie')    
    RICH_MEDIA      = (20, 'RichMedia')
    WIDGET          = (21, 'Widget')  # <===  # <=== Widget object in PyMuPDF
    SCREEN          = (22, 'Screen')  
    PRINTER_MARK    = (23, 'PrinterMark')
    TRAP_NET        = (24, 'TrapNet')    
    WATERMARK       = (25, 'WaterMark')
    _3D             = (26, '3D')   
    PROJECTION      = (27, 'Projection')
    REPLACE         = (28, 'Replace') # Not standard annot (from PyMuPDF or otherwise)
    UNKNOWN         = (-1, 'Unknown')

    def __init__(self, type_id, label):
        self.type_id = type_id
        self.label = label

    @classmethod
    def _from_pymupdf(cls, data: tuple[int, str]) -> "AnnotType":
        type_id, label = data
        for member in cls:
            if member.type_id == type_id:
                return member
        return cls.UNKOWN
    
class Annot:
    """
    Slightly revised version of pymupdf's Annot which
    has normalized rectangle and is decoupled from page object
    """
    TEXT_SELECT_ANNOTS = {
            AnnotType.HIGHLIGHT,
            AnnotType.STRIKE_OUT,
            AnnotType.SQUIGGLY,
            AnnotType.UNDERLINE,
            AnnotType.REPLACE,
    }

    @staticmethod
    def to_selection_tag_name(ann: AnnotType):
        if ann == AnnotType.CARET:
            return "CARET"
        else:
            return "SEL"
    
    def __init__ (
            self,
            pageno: int,
            type: AnnotType,
            info: dict,
            xref: int,
            irt_xref: int,
            rect: pymupdf.Rect,
            vertices: list[list[pymupdf.Point]]
    ): 
        self.pageno = pageno        
        self.type = type
        self.info = info                
        self.xref = xref
        self.irt_xref = irt_xref
        self.rect = rect
        self.vertices = vertices
    
    def __repr__ (self):
        return str(
            {
                'pageno':self.pageno,
                'type':self.type,
                'info':self.info,
                'xref':self.xref,
                'irt_xref':self.irt_xref,
                'rect':self.rect,
                'vertices':self.vertices,
             }
        )
    
    def __str__ (self):
        return str(
            {
                'pageno':self.pageno,
                'type':self.type,
                'info':self.info['content'],
                'rect':self.rect,
             }
        )
    
class Edit:
    def __init__ (
            self,
            pageno: int,
            type: AnnotType,
            messages: dict[str, str | list[str]],
            selection: str,
            sync_rect: pymupdf.Rect, # for SyncTeX
            selection_rects: list[pymupdf.Rect], # for debugging
    ):
        self.pageno = pageno 
        self.type = type
        self.messages = messages
        self.selection = selection
        self.selection_rects = selection_rects 
        self.sync_rect = sync_rect 
        
    def __repr__ (self): 
        return json.dumps({
            "pageno": self.pageno, 
            "type": self.type.label, 
            "messages": {
                "comment": self.messages['comment'],
                "responses": self.messages['responses']
            },
            "PDF text selection": self.selection,
            "rectangle": str(self.sync_rect),
        }, indent=4, ensure_ascii=False)
    
    def __str__ (self):
        return repr(self)

def _reduced_pagetext_rect(
        annot_rect: pymupdf.Rect,
        page_rect: pymupdf.Rect
) -> pymupdf.Rect:
    return pymupdf.Rect(
        page_rect.x0,
        annot_rect.y0 - GET_PAGE_TEXT_VERT_SPAN,
        page_rect.x1,
        annot_rect.y1 + GET_PAGE_TEXT_VERT_SPAN
    )

def _adjust_caret_rect(caret_rect: pymupdf.Rect, page):
    """
    The bounding boxes of the original caret annotations often
    extend below the line they were inserted on, so they are
    resized to prevent that
    """
    CARET_V_PROPORTION = 0.2
    CARET_H_PROPORTION = 0.2

    (x0, y0, x1, y1) = caret_rect

    # do simple adjustment
    extension = CARET_V_PROPORTION * (y1 - y0)
    caret_rect.y1 = y0 + extension
    caret_rect.y0 = y0 - 0.75 * extension
    
    # check intersecting spans
    raw_dict_rect = _reduced_pagetext_rect(caret_rect, page.rect)
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
            caret_rect.y0 - SIMPLE_ADJUST,
            caret_rect.x1,
            caret_rect.y1 + SIMPLE_ADJUST
        )
    
    # otherwise set to span's true font height
    # in theory, setting  pymupdf.TOOLS.set_small_glyph_heights(True)
    # should do this kind of calcualtion for text extraction
    # automatically where relevant
    span = intersecting_spans[0]
    a, d, o = span['ascender'], span['descender'], pymupdf.Point(span['origin'])
    r = pymupdf.Rect(span['bbox'])
    descending_ammt = span['size'] * d / (a - d)
    y1 = o.y - descending_ammt
    y0 = y1 - span['size']
    return pymupdf.Rect(caret_rect.x0, y0, caret_rect.x1, y1)

def get_annots(filename: Path, adjust_annots: bool) -> dict[int, list[Annot]]:
    """
    Convert PyMuPDF annotations to our Annot class,
    normalizing rectangles in the process for
    selection text retrieval later
    """
    doc = pymupdf.open(filename)
    if adjust_annots:
        uses_stix = re.search(
            '|'.join(utils.PDF_WORKFLOW),
            filename,
            flags=re.IGNORECASE
        ) 
        if uses_stix is not None:
            logger.info("Adjusting annots for STIX2")
            annot_adjustment = STIX_ADJUST
        else:
            logger.info("Adjusting annots for CMR10")
            annot_adjustment = CMR10_ADJUST
    
    result = {
        pageno: []
        for pageno in range(doc.page_count)
    }
    
    for pageno, page in enumerate(doc):
        for annot in page.annots():
            ann_rect = pymupdf.Rect(annot.rect.top_left, annot.rect.bottom_right)
            annot_type = AnnotType._from_pymupdf(annot.type)
            
            if annot_type == AnnotType.TEXT: 
                result[pageno].append(Annot(
                    pageno,
                    annot_type,
                    annot.info,
                    annot.xref,
                    annot.irt_xref,
                    ann_rect,
                    annot.vertices
                ))
                continue
            
            (x0, y0, x1, y1) = ann_rect
            
            if annot_type == AnnotType.CARET:
                ann_rect = _adjust_caret_rect(ann_rect, page)

            if annot_type != AnnotType.CARET and adjust_annots:
                ann_rect.x0 += annot_adjustment
                ann_rect.x1 -= annot_adjustment
                if not ann_rect.is_valid:
                    logger.debug(f"annot on page {pageno+1} not valid after adjustment")
                    while not ann_rect.is_valid:
                        ann_rect.x0 -= 1
                        ann_rect.x1 += 1

            result[pageno].append(Annot(
                pageno,
                annot_type,
                annot.info,
                annot.xref,
                annot.irt_xref,
                ann_rect,
                annot.vertices
            ))
    return result

def _get_all_responses(annots: list[Annot]) -> dict[int, list[Annot]]:
    """
    return map from xrefs to lists of annotations
    that are in response to that xref
    """
    result = {}
    for pageno, annots in annots.items():
        for annot in annots:
            if annot.irt_xref == 0:
                continue
            result.setdefault(annot.irt_xref, []).append(annot)
    return result

def _get_responses_by_type(
        in_annot: Annot,
        all_responses: dict[int, list[Annot]]
) -> dict[AnnotType, list[Annot]]:
    """
    return map from annotation type to
    list of annotations in response to in_annot
    of annotation type (and sort by creation date)
    """
    if in_annot.xref not in all_responses:
        return {}

    result = {}
    for response in all_responses[in_annot.xref]:
        result.setdefault(response.type, []).append(response)

    return {
        ann_type: sorted(
            responses,
            key = lambda r: r.info['creationDate']
        )
        for ann_type, responses in result.items()
    }

def _get_multiline_rects(annot: Annot, num_lines: int) -> list[pymupdf.Rect]:
    not_multiline = (
        annot.type not in Annot.TEXT_SELECT_ANNOTS
        or annot.vertices is None
        or num_lines == 1
    )
    if not_multiline:
        return [annot.rect]

    if len(annot.vertices) % 4 != 0:
        raise ValueError(
            f"Vertices of {annot.info} on page "
            f"{annot.pageno+1} were not a multiple of four"
        )
    
    multiline_rects = [
        pymupdf.Rect(annot.vertices[i], annot.vertices[i+NUM_VERTICES_PER_RECT-1])
        for i in range(0, len(annot.vertices), NUM_VERTICES_PER_RECT)
    ]

    multiline_rects = [
        rect for rect in multiline_rects
        if rect.is_valid
    ]

    if not multiline_rects:
        raise ValueError(
            "No multiline rectangles were valid for "
            f"{annot.info} on page {annot.pageno+1}"
        )

    return multiline_rects

def _get_rect_center(rect: pymupdf.rect) -> tuple[float, float]:
    return (rect.x0 + rect.width / 2, rect.y0 + rect.height/2)

def _get_char_center(char: dict[str, tuple | str]) -> pymupdf.Point:
    x0, y0, x1, y1 = char['bbox']
    x = x0 + (x1 - x0)/2
    y = y0 + (y1 - y0)/2
    # maybe use pymupdf.Point(char['origin'])
    # instead that's at the bottom left iirc        
    return pymupdf.Point(x, y)

def _rects_contain_char(
        rects: list[pymupdf.Rect],
        char: dict[str, tuple | str],
) -> bool:
    char_center = _get_char_center(char)
    for rect in rects:
        if rect.contains(char_center): 
            return True
    return False

def _chars_iterator(page_rawdict):
    for block in page_rawdict.get('blocks'):
        if block.get('lines') is None:
            continue
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    yield char

def _get_tag_transitions(
        page_rawdict,
        annot_rects: list[pymupdf.rect]
) -> tuple[set[int], set[int]]:
    containment_sequence = [
        _rects_contain_char(annot_rects, char)
        for char in _chars_iterator(page_rawdict)
    ]

    open_tag_transitions  = set()
    close_tag_transitions = set()
    prev_in = None
    for i, curr_in in enumerate(containment_sequence):
        # first char of page in selection        
        if prev_in is None and curr_in: 
            open_tag_transitions.add(0)
            assert i == 0
        elif not prev_in and curr_in:
            open_tag_transitions.add(i)
        elif prev_in and not curr_in:
            close_tag_transitions.add(i-1)

        # last char of the page in selection              
        if curr_in and i == len(containment_sequence)-1:
            close_tag_transitions.add(i)
            
        prev_in = curr_in
    return open_tag_transitions, close_tag_transitions

def _relative_position_value(
        caret_rect: pymupdf.Rect,
        char: dict[str, tuple | str]
) -> int:
    """
    Return 0 if char is not in vertical span of caret_rect
    Return 1 if char is in vertical span and
    is TO THE LEFT  of caret center
    Return 2 if char is in vertical span and
    is TO THE RIGHT of caret center
    """
    char_center = _get_char_center(char)
    if not (caret_rect.y0 <= char_center.y <= caret_rect.y1):
        return 0
    caret_center_x, _ = _get_rect_center(caret_rect)
    return 1 if char_center.x < caret_center_x else 2

def _point_dist(p1: tuple[float, ...], p2: tuple[float, ...]):
    return math.hypot(*[a - b for a, b in zip(p1, p2)])

def _closest_to_caret(
        caret_rect: pymupdf.Rect,
        inds_and_chars: list[tuple[int, dict]],
) -> int:
    caret_center = _get_rect_center(caret_rect)
    m = (float('inf'), -1)
    for (idx, char) in inds_and_chars:
        char_center = _get_rect_center(pymupdf.Rect(char['bbox']))
        dist = _point_dist(caret_center, char_center)
        if dist < m[0]:
            m = (dist, idx)
    return m[1]

def _get_caret_transition(
        annot: Annot,
        relpos_sequence: list[int],
        page_chars: list[dict],
) -> int:
    # (idx, char) tuples where idx is left of Caret
    # center and idx+1 is right of Caret center
    # only use char for _closest_to_caret
    transitions = {
        'mid-line': [],
        'start-line': [],
        'end-line': []
    }

    def addTransition(key, idx):
        transitions[key].append((idx, page_chars[idx]))

    prev = relpos_sequence[0]
    
    # maybe useful to consider in the future    
    in_vertical_span_indices = [0] if prev > 0 else []
    
    num_page_chars = len(relpos_sequence)
    
    for i, trit in enumerate(relpos_sequence):
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
        raise ValueError(f"No caret point detected in {annot}")
    elif len(all_transitions) > 1:
        logger.debug(f"Multiple insertion indices detected in {annot}")
        insertion_index = _closest_to_caret(annot.rect, all_transitions)
    else:
        insertion_index, _ = list(all_transitions)[0]
    return insertion_index

def _build_caret(
        annot: Annot,
        caret_index: int,
        page_rawdict,
) -> tuple[str, str, str]:
    page_chars_with_synthetic = []
    synth_car_idx = -1
    i, synth_idx = 0, 0
    
    tag_name = Annot.to_selection_tag_name(annot.type)
    caret_tag = f'<{tag_name}>'

    def _add_synth_space():
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
                    if i == caret_index:
                        page_chars_with_synthetic.append(caret_tag)
                        synth_car_idx = synth_idx 
                        synth_idx += len(caret_tag)
                    i += 1
            _add_synth_space()
        _add_synth_space()
        
    end_car_idx = synth_car_idx + len(caret_tag)
    
    left  = page_chars_with_synthetic[:synth_car_idx]
    caret = page_chars_with_synthetic[synth_car_idx:end_car_idx]
    right = page_chars_with_synthetic[end_car_idx:]

    assert left + caret + right == page_chars_with_synthetic, "what"

    return ''.join(left), ''.join(caret), ''.join(right)

def _get_caret_text(annot: Annot, page_rawdict) -> str:
    """
    If the caret is at the beginning of a line,
    there should be a 0 to 2 (in the relpos_sequence
    
    If the caret is in the middle of a line,
    there should be a 1 to 2
    
    If the caret is at the end of a line,
    there should be a 1 to 0    
    """
    if annot.type != AnnotType.CARET:
        raise ValueError(f"Expected caret annotation, not {annot.type}")

    caret_rect = annot.rect
    page_chars = [char for char in _chars_iterator(page_rawdict)]
    relpos_sequence = [
        _relative_position_value(caret_rect, char)
        for char in page_chars
    ]

    insertion_index = _get_caret_transition(annot, relpos_sequence, page_chars)
    left, caret, right = _build_caret(annot, insertion_index, page_rawdict)

    left  = _limit_text(left, direction='left')
    right = _limit_text(right, direction='right')

    return left + caret + right

def _build_noncaret(
        page_rawdict,
        open_trans: set[int],
        close_trans: set[int],
        tag_name: str,
) -> tuple[str, str, str]:
    """
    We iterate through the characters on the page and check
    if it's center (origin) is inside of the annotation.

    So we have two states 0 = outside annotation rectangle
    and 1 = inside annotation rectangle

    So iterating through the characters gives us binary string.
    The sequence 01 (with, say, characters ab) corresponds to
    the start of the tag at `a(b`, and the sequence 10
    corresponds to the closing tag `a)b` so 010 would make
        a(b)c,
    and 0 1111 0 1 00 1 0 would make
        a(bcde)f(g)hi(j)k

    There's a different procedure for caret annotations since they don't
    really 'select' text. They just mark a point between characters

    Also in desperate need of refactoring
    """
    open_tag = f'<{tag_name}>'
    close_tag = f'</{tag_name}>'
    
    selection = []
    i, synth_idx = 0, 0
    
    def _add_synth_space():
        nonlocal synth_idx
        selection.append(' ')
        synth_idx += 1

    insert_indices = []
    # can't use char iterator here since we need to insert
    # synthetic spaces ourselves. Well atleast not the
    # iterator as it is written now
    for block in page_rawdict.get('blocks'):
        if block.get('lines') is None:
            continue
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    if i in open_trans and i not in close_trans:
                        selection.append(open_tag)
                        insert_indices.append(synth_idx)
                        synth_idx += 1
                        
                        selection.append(char['c'])
                        synth_idx += 1
                        i += 1         
                    elif i in close_trans and i not in open_trans:
                        selection.append(char['c'])
                        synth_idx += 1
                        i += 1

                        selection.append(close_tag)
                        synth_idx += 1                        
                        insert_indices.append(synth_idx)
                    elif i in open_trans and i in close_trans:
                        selection.append(open_tag)
                        insert_indices.append(synth_idx)
                        synth_idx += 1
                        
                        selection.append(char['c'])
                        synth_idx += 1
                        i += 1
                        
                        selection.append(close_tag)
                        synth_idx += 1                        
                        insert_indices.append(synth_idx)
                    else:
                        selection.append(char['c'])
                        synth_idx += 1
                        i += 1
            _add_synth_space()
        _add_synth_space()
        
    if not insert_indices:
        raise ValueError("No selection insert indices found")

    first_insert = insert_indices[0]
    last_insert  = insert_indices[-1]

    # ic(f"{''.join(selection[first_insert:last_insert])}")

    left   = selection[:first_insert]
    middle = selection[first_insert:last_insert]
    right  = selection[last_insert:]
    
    return ''.join(left), ''.join(middle), ''.join(right)

def _limit_text(text: str, direction: str):
    if direction == 'left':
        to_left = text.split(' ')

        idx = len(to_left) - 1
        nonspace_seen = 0
        while idx >= 0 and nonspace_seen < NUM_CONTEXT_WORDS:
            if re.match(r'^\s*$', to_left[idx]) is None:
                nonspace_seen += 1
            idx -= 1

        left_include = to_left[idx+1:]
        return ' '.join(left_include)
    
    if direction != 'right':
        raise ValueError("_limit_text direction must be either 'left' or 'right'")

    to_right = text.split(' ')
    idx = 0
    nonspace_seen = 0
    while idx < len(to_right) and nonspace_seen < NUM_CONTEXT_WORDS:
        if re.match(r'^\s*$', to_right[idx]) is None:
            nonspace_seen += 1
        idx += 1
    right_include = to_right[:idx]
    return ' '.join(right_include)

def _get_annot_rects(
        annot: Annot,
        page_words: tuple[float, float, float, float, str, int, int, int],
) -> list[pymupdf.Rect]:
    """
    Get rectangles that make up annotation
    there can be mre than one if multiple lines of text are selected
    """
    intersecting_words = [
        word for word in page_words
        if annot.rect.intersects(pymupdf.Rect(word[0:4]))
    ]

    num_lines = len({iw[WORD_LINE_NO_IDX] for iw in intersecting_words})

    try:
        annot_rects = _get_multiline_rects(annot, num_lines)
    except ValueError as e:
        logger.error(e)
        annot_rects = [annot.rect]
    return annot_rects
    
def _get_noncaret_text(
        annot: Annot,
        page_rawdict,
        page_words: tuple[float, float, float, float, str, int, int, int],
) -> tuple[str, list[pymupdf.Rect]]:
    annot_rects = _get_annot_rects(annot, page_words)
    open_trans, close_trans = _get_tag_transitions(page_rawdict, annot_rects)

    tag_name = Annot.to_selection_tag_name(annot.type)

    try:
        left, middle, right = _build_noncaret(
            page_rawdict,
            open_trans,
            close_trans,
            tag_name,
        )
    except ValueError as e:
        if annot.type in Annot.TEXT_SELECT_ANNOTS:
            logger.warning(f"{e} for {annot}")
        return 'None', annot_rects

    # the left and right text is typically longer than we want,
    # so we reduce either side of text to only NUM_CONTEXT_WORDS

    left  = _limit_text(left, direction='left')
    right = _limit_text(right, direction='right')

    return left + middle + right, annot_rects

def _get_selection(
        annot: Annot,
        page_words: list[tuple[float, float, float, float, str, int, int, int]],
        doc: pymupdf.Document,
) -> tuple[str, pymupdf.Rect, list[pymupdf.Rect] | None]:
    """
    Return: annotation's selected text,
            rectangle for latex source extraction,
            selection rectangles for debugging

    page_words is list where
    word[0] = x0: float
    word[1] = y0: float
    word[2] = x1: float
    word[3] = y1: float
    word[4] = pdf_text: str
    word[5] = block_no: int
    word[6] = line_no: int
    word[7] = word_no: int
    """
    page = doc[annot.pageno]

    raw_dict_rect = _reduced_pagetext_rect(annot.rect, page.rect)
    page_rawdict = page.get_text('rawdict', sort=True, clip=raw_dict_rect)

    if annot.type == AnnotType.CARET:
        caret_selection = _get_caret_text(annot, page_rawdict)
        return caret_selection, None
    
    selection, annot_rects = _get_noncaret_text(
        annot,
        page_rawdict,
        page_words,
    )
    return selection, annot_rects

def _is_replace_annot(
        ann: Annot,
        ann_resps: dict[AnnotType, list[Annot]]
) -> tuple[bool, Annot | None]:
    
    if not ann_resps:
        return False, None
    
    is_caret_or_strikeout = ann.type in {
        AnnotType.STRIKE_OUT,
        AnnotType.CARET,
    }
    
    if not is_caret_or_strikeout:
        return False, None

    if ann.type in ann_resps:
        raise ValueError(
            f"Annotation {ann} has responses to it of "
            f"the same type {ann_resps[ann.type]}"
        )
    
    if len(ann_resps.keys()) >= 3:
        raise ValueError(f"Annotation {ann} has responses of more than two types {ann_resps.keys()}")
                
    other_ann_type = AnnotType.STRIKE_OUT if ann.type == AnnotType.CARET else AnnotType.CARET

    other_type_in_resps_and_only_one = len(ann_resps.get(other_ann_type, [])) == 1
    if not other_type_in_resps_and_only_one:
        return False, None
    
    [other_ann] = ann_resps[other_ann_type]

    intersect_and_other_empty = (
        ann.rect.intersects(other_ann.rect)
        and not other_ann.info['content']
    )

    if not intersect_and_other_empty:
        return False, None
    
    return True, other_ann    

def get_edits(filename: Path, adjust_annots: bool) -> list[Edit]:
    """return a list of Edits. See class Edit."""
    logger.info("Loading PDF annotations...")
    
    doc = pymupdf.open(filename)
    annots = get_annots(filename, adjust_annots)
    all_responses = _get_all_responses(annots)
    
    logger.info("Done")

    num_edits_made = 0
    logger.info(f"Processing {len(annots)} pages of annotations...")
    
    result = []

    num_pages_with_annots_to_extract = sum(
        1 for pageno, _ in enumerate(doc)
        if annots[pageno]
    )

    expected_num_edits = 0

    bar = utils.TextProgressBar(num_pages_with_annots_to_extract)
    bar.show_size()
    
    for pageno, page in enumerate(doc):
        for annot in annots[pageno]:
            # only true for text responses and annotations which combine
            # with another to make an annotation of type 'Replace'            
            if annot.irt_xref != 0:
                continue
            expected_num_edits += 1
            
            responses = _get_responses_by_type(annot, all_responses)

            text_responses = responses.get(AnnotType.TEXT, [])
            text_responses = [response.info['content'] for response in text_responses]
            
            messages = {
                'comment': annot.info['content'],
                'responses': text_responses,
            }

            try:
                is_replace, other_ann = _is_replace_annot(annot, responses)
            except ValueError as e:
                logger.error(e)
                continue
            
            if is_replace:
                if annot.type == AnnotType.CARET:
                    annot.rect = other_ann.rect
                    annot.vertices = other_ann.vertices
                annot.type = AnnotType.REPLACE 

            page_words_rect = _reduced_pagetext_rect(annot.rect, page.rect)
            page_words = page.get_text('words', sort=True, clip=page_words_rect)
            page_words = list(sorted(page_words, key = lambda w: (w[5], w[6], w[7])))
            
            selection, selection_rects = _get_selection(annot, page_words, doc)
            
            if selection is None:
                continue

            selection = utils.unicode_to_tex(selection)
            
            result.append(Edit(
                annot.pageno,
                annot.type,
                messages,
                selection,
                annot.rect,
                selection_rects,
            ))

        if annots[pageno]:
            bar.add_progress()
    bar.end()
        
    logger.info(
        f"Created {len(result)} edit{utils.plural(len(result))} from "
        f"{expected_num_edits} PDF annotations"
    )
    return result
