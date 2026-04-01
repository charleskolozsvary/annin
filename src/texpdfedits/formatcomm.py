import logging
logger = logging.getLogger(__name__)

from texpdfedits.corr import Correction
import texpdfedits.utils as utils

import re

FORMAT_FRONT = 'front-load'
FORMAT_SPLIT = 'read-order'
FORMAT_BACK = 'back-load'

DEFAULT_COMMENT_FORMAT = FORMAT_FRONT

DOWN_SYMBOL = '⭣'
UP_SYMBOL = '⭡'

NUM_FB_SYMBOL = 3
NUM_SPLIT_SYMBOL = 3

# all the same right now. leaving just in case I want to change
FORMAT_TO_IDENTIFIER = {
    FORMAT_FRONT: (DOWN_SYMBOL * NUM_FB_SYMBOL, UP_SYMBOL * NUM_FB_SYMBOL),
    FORMAT_SPLIT: (DOWN_SYMBOL * NUM_SPLIT_SYMBOL, UP_SYMBOL * NUM_SPLIT_SYMBOL),
    FORMAT_BACK: (DOWN_SYMBOL * NUM_FB_SYMBOL, UP_SYMBOL * NUM_FB_SYMBOL),
}

FRONT_OID = FORMAT_TO_IDENTIFIER[FORMAT_FRONT][0]
FRONT_CID = FORMAT_TO_IDENTIFIER[FORMAT_FRONT][1]

SPLIT_OID = FORMAT_TO_IDENTIFIER[FORMAT_SPLIT][0]
SPLIT_CID = FORMAT_TO_IDENTIFIER[FORMAT_SPLIT][1]

BACK_OID = FORMAT_TO_IDENTIFIER[FORMAT_BACK][0]
BACK_CID = FORMAT_TO_IDENTIFIER[FORMAT_BACK][1]

DELETE_TAG = 'nocomments'

REMOVE_REGEXES = {
        FORMAT_FRONT: re.compile(
                rf"""%%\n                                      # leading intro
                ^%%\ Correction\ [0-9]+,\ page\ [0-9]+ [^\n]*+ \n  # head
                (?:^% [^\n]*+ \n)+?                            # information
                ^%{FRONT_OID} [^\n]*+ \n                       # last start with id
                (.*?)                                          # LaTeX to preserve
                %%\n                                           # leading exit comment
                ^%{FRONT_CID} [^\n]*+ \n                       # end with id
                ([ \t\r]*\n)?+
                """,
                flags=re.VERBOSE | re.DOTALL | re.MULTILINE
        ),
        FORMAT_SPLIT: re.compile(''), # TODO
        FORMAT_BACK: re.compile('')   # TODO
}

def startComment(corr: Correction, format: str, replies: str):
    c_id = FORMAT_TO_IDENTIFIER[format][0] # [0] since start

    if replies:
        replies = f'\n%% Replies: "{replies}"'

    status_message = '(auto) [✓]' if corr.is_autocorrected else '[ ]'

    if format == FORMAT_FRONT:
        return (
            f"%% Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%% Selection: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"\n"
            f"%% Comment:   \"{utils.sanitizePdfText(corr.messages['comment'])}\"{replies}\n"
            f"%%\n"
        )
        
    if format == FORMAT_SPLIT:
        return (
            f"%% Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%% Selection: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"{replies}\n"
            f"%{c_id}\n"
        )
        
    if format == FORMAT_BACK:
        return ''

def endComment(corr: Correction, format: str, replies: str):
    c_id = FORMAT_TO_IDENTIFIER[format][1]

    if replies:
        replies = f'\n%% Replies: "{replies}"'    
        
    if format == FORMAT_FRONT:
        return ''
        
    if format == FORMAT_SPLIT:
        return (
            f"%{c_id}\n"
            f"%% Comment {corr.index}: "
            f"\"{utils.sanitizePdfText(corr.messages['comment'])}\"\n"
        )
        
    if format == FORMAT_BACK:
        return (
            f"%{c_id} Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%{c_id} Selection: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"\n"
            f"%{c_id} Comment:   \"{utils.sanitizePdfText(corr.messages['comment'])}\"{replies}\n"
            f"%{c_id}\n"
        )

def writeCallout(corr_idxs: list[int], start_or_end: str, format: str):
    idx = 0 if start_or_end == 'start' else 1
    c_id = FORMAT_TO_IDENTIFIER[format][idx]
    sing_plural = 'correction' if len(corr_idxs) == 1 else 'corrections'
    
    if format == FORMAT_FRONT:
        return (
            f'%{c_id} {start_or_end.upper()} of {sing_plural} '
            + ', '.join(str(idx) for idx in corr_idxs)
            + '\n'
        )
    
    if format == FORMAT_SPLIT:
        return ''
    
    if format == FORMAT_BACK:
        return (
            f'%{c_id} {start_or_end.upper()} of {sing_plural} '
            + ', '.join(str(idx) for idx in corr_idxs)
            + '\n'
        )

def deleteComments(tex_file: Path, format: str):
    tex_str = utils.sourceAsString(tex_file)
    comment_regex = REMOVE_REGEXES[format]

    def doReplace(match):
        latex = match.group(1)
        start_next = '\n\n' if match.group(2) is not None else ''
        return latex + start_next
                        
    nocomments_tex_str, n_subs1 = comment_regex.subn(doReplace, tex_str)
    nocomments_tex_str, n_subs2 = comment_regex.subn(doReplace, nocomments_tex_str)
    
    logger.info(f"Deleted {n_subs1 + n_subs2} comments")
    
    nocomments_file = utils.tagFileStem(tex_file, DELETE_TAG)
    utils.writeStringToFile(nocomments_tex_str, nocomments_file)
    return (nocomments_tex_str, nocomments_file)
