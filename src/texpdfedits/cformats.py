from texpdfedits.corr import Correction
import texpdfedits.utils as utils

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

def startComment(corr: Correction, format: str, replies: str):
        c_id = FORMAT_TO_IDENTIFIER[format][0] # [0] since start
        
        if replies:
            replies = f'\n%{c_id} Replies: "{replies}"'

        status_message = '(auto) [✓]' if corr.is_autocorrected else '[ ]'

        if format == FORMAT_FRONT:
            return (
                f"%% Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
                f"%% Selection: \"{utils.replaceNewlines(corr.pdf_selected_text)}\"\n"
                f"%% Comment:   \"{utils.replaceNewlines(corr.messages['comment'])}\" {replies}\n"
                f"%%\n"
            )
        
        if format == FORMAT_SPLIT:
            return (
                f"%% Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
                f"%% Selection: \"{utils.replaceNewlines(corr.pdf_selected_text)}\" {replies}\n"
                f"%{c_id}\n"
            )
        
        if format == FORMAT_BACK:
            return ''

def endComment(corr: Correction, format: str, replies: str):
    c_id = FORMAT_TO_IDENTIFIER[format][1]

    if replies:
        replies = f'\n%{c_id} Replies: "{replies}"'    
        
    if format == FORMAT_FRONT:
        return ''
        
    if format == FORMAT_SPLIT:
        return (
            f"%{c_id}\n"
            f"%% Comment {corr.index}: "
            f"\"{utils.replaceNewlines(corr.messages['comment'])}\n"
        )
        
    if format == FORMAT_BACK:
        return (
            f"%{c_id} Correction {corr.index}, page {corr.pageno+1} {status_message}\n"
            f"%{c_id} Selection: \"{utils.replaceNewlines(corr.pdf_selected_text)}\"\n"
            f"%{c_id} Comment:   \"{utils.replaceNewlines(corr.messages['comment'])}\" {replies}\n"
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

