import logging
logger = logging.getLogger(__name__)

from texpdfedits.corr import Correction
import texpdfedits.utils as utils

import re

FORMAT_FRONT = 'before'
FORMAT_SPLIT = 'split'
FORMAT_BACK = 'after'

RECOGNIZED_FORMATS = {FORMAT_FRONT, FORMAT_SPLIT, FORMAT_BACK}

DEFAULT_COMMENT_FORMAT = FORMAT_FRONT

DOWN_SYMBOL = '⭣ '
UP_SYMBOL = '⭡ '

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
                rf"""
                %%                                             \n
                ^%%\ Annotation\ [0-9]+,\ page\ [0-9]+ [^\n]*+ \n
                (?:^% [^\n]*+ \n)+?          
                ^%{re.escape(FRONT_OID)}               [^\n]*+ \n
                (.*?)                                   
                %%                                             \n                                    
                ^%{re.escape(FRONT_CID)}               [^\n]*+ \n
                ([ \t\r]*\n)?+
                """,
                flags=re.VERBOSE | re.DOTALL | re.MULTILINE
        ),
        FORMAT_SPLIT: re.compile(
                rf"""
                %%                                             \n
                ^%%\ Annotation\ [0-9]+,\ page\ [0-9]+ [^\n]*+ \n
                (?:^% [^\n]*+ \n)+?              
                ^%{re.escape(SPLIT_OID)}               [^\n]*+ \n
                (.*?)                    
                %%                                             \n   
                ^%{re.escape(SPLIT_CID)}               [^\n]*+ \n
                (?: ^%%\ Comment [^\n]*+ \n)++
                ([ \t\r]*\n)?+
                """,
                flags=re.VERBOSE | re.DOTALL | re.MULTILINE
        ),
        FORMAT_BACK: re.compile(
                rf"""
                %%                                \n                                            
                ^%{re.escape(BACK_OID)}  [^\n]*+  \n                              
                (.*?)                                                
                %%                                \n                                                 
                ^%{re.escape(BACK_CID)}  [^\n]*+  \n
                (?:
                ^%%                       \n
                ^%%\ Annotation\ [^\n]*+  \n
                ^%%\ [a-zA-Z]+:  [^\n]*+  \n
                ^%%\ Comment:    [^\n]*+  \n
                (?:^%%\ Replies: [^\n]*+  \n)?+
                )++
                ([ \t\r]*\n)?+
                """,
                flags=re.VERBOSE | re.DOTALL | re.MULTILINE
        ),        
}


def get_replies_and_status(corr: Correction, replies: str):
    if replies:
        replies = f'\n%% Replies: "{replies}"'

    status_message = '(AUTOCORRECTED) [ ]' if corr.is_autocorrected else '[ ]'
    return (replies, status_message)
    

def startComment(corr: Correction, format: str, replies: str):
    # c_id = FORMAT_TO_IDENTIFIER[format][0] # [0] since start
    corr_tid, corr_type = corr.type    

    (replies, status_message) = get_replies_and_status(corr, replies)

    if format == FORMAT_FRONT:
        return (
            f"%% Annotation {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%% {corr_type}: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"\n"
            f"%% Comment:   \"{utils.sanitizePdfText(corr.messages['comment'])}\"{replies}\n"
            f"%%\n"
        )
        
    if format == FORMAT_SPLIT:
        return (
            f"%% Annotation {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%% {corr_type}: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"{replies}\n"
        )
        
    if format == FORMAT_BACK:
        return ''

def endComment(corr: Correction, format: str, replies: str):
    # c_id = FORMAT_TO_IDENTIFIER[format][1]
    corr_tid, corr_type = corr.type

    (replies, status_message) = get_replies_and_status(corr, replies)    
        
    if format == FORMAT_FRONT:
        return ''
        
    if format == FORMAT_SPLIT:
        return (
            f"%% Comment {corr.index}: "
            f"\"{utils.sanitizePdfText(corr.messages['comment'])}\"\n"
        )
        
    if format == FORMAT_BACK:
        return (
            f"%%\n"
            f"%% Annotation {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%% {corr_type}: \"{utils.sanitizePdfText(corr.pdf_selected_text)}\"\n"
            f"%% Comment:   \"{utils.sanitizePdfText(corr.messages['comment'])}\"{replies}\n"
        )

def writeCallout(corr_idxs: list[int], start_or_end: str, format: str):
    idx = 0 if start_or_end == 'start' else 1
    c_id = FORMAT_TO_IDENTIFIER[format][idx]
    sing_plural = 'annotation' if len(corr_idxs) == 1 else 'annotations'
    
    if format == FORMAT_FRONT:
        if start_or_end == 'start':
            return f'%{c_id}\n'
        else:
            return (
                f'%{c_id} {start_or_end.upper()} of {sing_plural} '
                + ', '.join(str(idx) for idx in corr_idxs)
                + '\n'
            )
    
    if format == FORMAT_SPLIT:
        return f'%{c_id}\n'
    
    if format == FORMAT_BACK:
        if start_or_end == 'end':
            return f'%{c_id}\n'
        else:
            return (
                f'%{c_id} {start_or_end.upper()} of {sing_plural} '
                + ', '.join(str(idx) for idx in corr_idxs)
                + '\n'
            )

def deleteComments(tex_file: Path, format: str):
    tex_str = utils.sourceAsString(tex_file)
    comment_regex = REMOVE_REGEXES[format]
    n_newnew = 0

    def doReplace(match):
        nonlocal n_newnew
        latex = match.group(1)
        if match.group(2) is not None:
            n_newnew += 1
            start_next = '\n\n'
        else:
            start_next = ''
        return latex + start_next
                        
    nocomments_tex_str, n_subs1 = comment_regex.subn(doReplace, tex_str)
    nocomments_tex_str, n_subs2 = comment_regex.subn(doReplace, nocomments_tex_str)
    
    logger.info(f"Deleted {n_subs1 + n_subs2} comments")
    logger.debug(f"{n_newnew} double newlines")    
    
    nocomments_file = utils.tagFileStem(tex_file, DELETE_TAG)
    utils.writeStringToFile(nocomments_tex_str, nocomments_file)
    return (nocomments_tex_str, nocomments_file)
