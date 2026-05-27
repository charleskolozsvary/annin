import logging
logger = logging.getLogger(__name__)

from texpdfedits.corr import Correction
import texpdfedits.utils as utils

import re

DOWN_SYMBOL = '⭣ '
UP_SYMBOL = '⭡ '

NUM_SYMBOL = 3

IDENTIFIER = (DOWN_SYMBOL * NUM_SYMBOL, UP_SYMBOL * NUM_SYMBOL)

(FRONT_OID, FRONT_CID) = IDENTIFIER

DELETE_TAG = 'nocomments'

REMOVE_REGEX = re.compile(
    rf"""
    ^%%\ Correction\ [0-9]+,\ page\ [0-9]+ [^\n]*+ \n
    (?:^% [^\n]*+ \n)+?
    ^%{re.escape(FRONT_OID)}               [^\n]*+ \n
    (.*?)
    ^%{re.escape(FRONT_CID)}               [^\n]*+ \n
    ([ \t\r]*\n)?+
    """,
    flags=re.VERBOSE | re.DOTALL | re.MULTILINE
)

def get_replies_and_status(corr: Correction, replies: str):
    if replies:
        replies = f'\n%% Replies: "{replies}"'

    status_message = '(AUTOCORRECTED) [ ]' if corr.is_autocorrected else '[ ]'
    return (replies, status_message)
    
def start_comment(corr: Correction, replies: str):
    (replies, status_message) = get_replies_and_status(corr, replies)

    return (
        f"%% Correction {corr.index}, page {corr.pageno+1} {status_message}\n" # + 1 on pageno for 1, not 0 indexed
        f"%% {corr.type.label}: \"{utils.sanitize_pdf_text(corr.selection)}\"\n"
        f"%% Comment:   \"{utils.sanitize_pdf_text(corr.messages['comment'])}\"{replies}\n"
        f"%%\n"
    )

def write_callout(corr_idxs: list[int], start_or_end: str):
    idx = 0 if start_or_end == 'start' else 1
    c_id = IDENTIFIER[idx]
    sing_plural = f'correction{utils.plural(len(corr_idxs))}'
    
    if start_or_end == 'start':
        return f'%{c_id}\n'
    else:
        return (
            f'%{c_id} {start_or_end.upper()} of {sing_plural} '
            + ', '.join(str(idx) for idx in corr_idxs)
            + '\n'
        )

def delete_comments(tex_file: Path, replace: bool) -> Path:
    tex_str = utils.sourceAsString(tex_file)
    comment_regex = REMOVE_REGEX
    n_newnew = 0

    def do_sub(match):
        nonlocal n_newnew
        latex = match.group(1)
        if match.group(2) is not None:
            n_newnew += 1
            start_next = '\n\n'
        else:
            start_next = ''
        return latex + start_next
                        
    nocomments_tex_str, n_subs1 = comment_regex.subn(do_sub, tex_str)
    nocomments_tex_str, n_subs2 = comment_regex.subn(do_sub, nocomments_tex_str)
    
    logger.info(f"Deleted {n_subs1 + n_subs2} comments")
    logger.debug(f"{n_newnew} double newlines")    
    
    nocomments_file = utils.tagFileStem(tex_file, DELETE_TAG)
    utils.writeStringToFile(nocomments_tex_str, nocomments_file)

    if replace:
        # overwrite first file with second 
        nocomments_file.move(tex_file)
        logger.info(f"Overwrote {tex_file} with {nocomments_file}")
        
    return nocomments_file
