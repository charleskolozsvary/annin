import logging
logger = logging.getLogger(__name__)
import argparse
import pymupdf
import re
import sys
from pathlib import Path

import texpdfedits.extractanns as extractanns
import texpdfedits.marktex as marktex
import texpdfedits.formatcomm as formatcomm
import texpdfedits.utils as utils

from texpdfedits.corr import Correction, toCodeblock
from texpdfedits.extractanns import Annot

from icecream import ic

MAX_PROGRESSIVE_AUTO_ATTEMPTS = 10
MIN_MATCH_FOR_AUTO = 5 # autocorrect must match at least this many characters

def getBetweenLatex(
        prev_pos: int,
        char_pos: int,
        prev_rest_of_line: str,
        *args
) -> str:
    (tex_str, charpos_to_kinds_and_corrections, corrected_snippets) = args
    
    between_source_tex = tex_str[prev_pos:char_pos]

    kinds_and_corrs = charpos_to_kinds_and_corrections[char_pos]
    kinds, corrs = zip(*kinds_and_corrs)
    num_ends = kinds.count('end')

    if num_ends == 0:
        return between_source_tex

    # filter out start corrections in the rare case a char_pos is both the start and end of corrections
    kinds, corrs = zip(*[
        kandc
        for kandc in kinds_and_corrs
        if kandc[0] == 'end'
    ])
        
    if not all(k == 'end' for k in kinds) or len(kinds) != num_ends:
        logger.critical(
            "Did not succesfully filter out corrections "
            "that start at this char_pos"
        )
        sys.exit(1)
        
    if len(corrs) > 1:
        # group processing
        for c in corrs:
            if c.group is None:
                logger.error(
                    "Could not get between latex: "
                    f"Correction {c} expected to be part of group"
                )
                sys.exit(1)
        group = corrs[0].group
        if not all(c.group == group for c in corrs):
            logger.critical(
                "Could not get between latex: "
                "Corrections sharing end positions "
                "were not all part of the same group"
            )
            sys.exit(1)
        if len(set(corrected_snippets[g_key] for g_key in group)) != 1:
            for corrected_snip in [
                    corrected_snippets[g_key]
                    for g_key in group
            ]:
                logger.error(toCodeblock(corrected_snip))
                    
            logger.critical(
                f"Corrections in overlapping group {group} "
                "did not have identical corrected snippets"
            )
            sys.exit(1)
        corrected_snip = corrected_snippets[group[0]]
        
    elif len(corrs) == 1:
        # standalone processing
        corrected_snip = corrected_snippets[corrs[0].index]
        group = [corrs[0].index]

    # either none of the snippets in the group were corrected or the standalone snippet wasn't corrected        
    if corrected_snip is None:
        return between_source_tex

    return corrected_snip

def commentSource(
        tex_str: str,
        char_positions: list[int],
        charpos_to_kinds_and_corrections: dict[int, list[tuple[str, Correction]]],
        **kwargs
) -> str:
    """
    Add the corrections to the original source as comments.

    Args:
    tex_str: original LaTeX source as string
    char_positions: sorted character positions of the starts and ends of the LaTeX snippets for each correction.
            important: the positions are simply sorted from least to greatest, and a position can correspond to the start OR end of a snippet
    
    charpos_to_kinds_and_corrections: dictionary where keys are members of char_positions and values are lists of (string, Correction) tuples
    where the string is either 'start' or 'end' and the correction is the corresponding correction object at that position.
    
    A list is returned for each key incase there are two or more start/end character positions which are the same.
    The positions of a non-overlapping correction will return a singleton.

    In the event that two corrections END at the same position, I'll just write

    %% END OF CORRECTIONS corr_idx1, corr_idx2, ...
    
    If two corrections START at the same position, I'll write

    %% Correction: corr_idx
    %% Annotated text:
    %% Comment: 

    for each correction in order and then
    %% START OF CORRECTIONS corr_idx1, corr_idx2, ...

    Finally, if a start AND end are at the same position then I'll write the correction info then say

    %% START of correction ... and END of correction ...
    """

    corrected_snippets = kwargs.get('corrected_snippets', None)
    format             = kwargs.get('comment_format', formatcomm.DEFAULT_COMMENT_FORMAT)
    
    inserted_comments = [] #list of tuples where tuple[0] is the char_pos and tuple[1] is the inserted material
    for char_pos in char_positions:
        kinds_and_corrs = charpos_to_kinds_and_corrections[char_pos]
        corr_descriptions = []
        start_corr_idxs, end_corr_idxs = [], []
        for kind_and_corr in kinds_and_corrs:
            (kind, corr) = kind_and_corr
            if kind == 'start':
                corr_descriptions.append(corr.asCommentStart(format))
                start_corr_idxs.append(corr.index)
            elif kind == 'end':
                corr_descriptions.append(corr.asCommentEnd(format)) # new with 0.12.0
                end_corr_idxs.append(corr.index)
            else:
                assert False, f"Invalid kind of position '{kind}'."
        
        start_end_callout = []

        if end_corr_idxs:
            start_end_callout.append(
                formatcomm.writeCallout(
                    end_corr_idxs,
                    'end',
                    format
                )
            )

        if end_corr_idxs and start_corr_idxs:
            logger.error(
                f"The start of correction(s) {start_corr_idxs} "
                f"coincided with the end of correction(s) {end_corr_idxs} "
                f"merging of the overlapping snippets failed"
            )
            start_end_callout.append('%% double trouble\n')
            
        if start_corr_idxs:
            start_end_callout.append(
                formatcomm.writeCallout(
                    start_corr_idxs,
                    'start',
                    format
                )
            )

        description_str = ''.join(corr_descriptions)
        callout_str = ''.join(start_end_callout)

        if start_corr_idxs:
            inserted_comments.append((
                char_pos,
                f'%%\n{description_str}{callout_str}'
            ))
        elif end_corr_idxs:
            inserted_comments.append((
                char_pos,
                f'%%\n{callout_str}{description_str}'
            ))
        else:
            logger.error(
                "There were neither start or end "
                "correction indices?"
            )
            

    len_tex_str = len(tex_str)
    commented_source = []
    prev_pos, prev_rest_of_line = 0, ''
    for (char_pos, inserted_comment) in inserted_comments:
        between_latex = tex_str[prev_pos:char_pos]
        if corrected_snippets is not None:
            between_latex = getBetweenLatex(
                prev_pos,
                char_pos,
                prev_rest_of_line,
                tex_str,
                charpos_to_kinds_and_corrections,
                corrected_snippets
            )
        
        commented_source.append(between_latex)

        # if char_pos >= len(tex_str):
        #     logger.warning(f"Character position {char_pos} in modifytex >= {len(tex_str)}")
        #     char_pos = len(tex_str)-1
            
        curr_char, char_idx = tex_str[char_pos], char_pos
        rest_of_line = [] # rest of line from char_pos or until non-horizontal space
        while not re.match(r'[\r\n\S]', curr_char):
            if char_idx >= len_tex_str:
                logger.critical(
                    "Ran out of file while looking "
                    "for rest_of_line"
                )
                sys.exit(1)
            rest_of_line.append(curr_char)
            char_idx += 1
            curr_char = tex_str[char_idx]
        rest_of_line.append(curr_char)
        rest_of_line = ''.join(rest_of_line)

        # logger.debug(f"{' '.join(inserted_comment[0:30].split()):30s}  rest_of_line: {repr(rest_of_line)}")

        if re.match(r'\s+', rest_of_line):
            commented_source.append(' ')

        last_char = rest_of_line[-1]

        if re.match(r'\S$', last_char):
            prev_pos = char_idx
        elif re.match(r'[\r\n]$', last_char):
            prev_pos = char_idx + 1
        else:
            prev_pos = char_pos
            
        commented_source.append(inserted_comment)
        prev_rest_of_line = rest_of_line        

    commented_source.append(tex_str[prev_pos:])
    return ''.join(commented_source)

def tagsAreValid(tagged_text: str, annot_name: str) -> bool:
    tag_regex = r'(</?)([a-zA-Z^‸]+)>'
    all_tags = list(re.finditer(tag_regex, tagged_text))
    if not all_tags:
        logger.warning(
            "string passed for tag validation contained no tags"
        )
        return True
    
    tag_info = [(tag.group(1), tag.group(2)) for tag in all_tags]
    (tag_starts, tag_names) = zip(*tag_info)

    # should have even number for noncaret tags
    if annot_name != Annot.CARET_NAME and len(tag_info) % 2 != 0:
        return False

    caret_focus_tag_name = Annot.to_selection_tag_name(Annot.CARET_NAME)
    if tag_names.count(caret_focus_tag_name) > 1:
        return False

    # we only accept one kind of tag used 
    if len(set(tag_names)) != 1:
        return False

    prev_start = ''
    for tag_start in tag_starts:
        if prev_start == '' and tag_start != '<':
            return False
        # we consider nested tags invalid in this context
        if prev_start == '<' and not tag_start == '</':
            return False
        if prev_start == '</' and tag_start != '<':
            return False
        prev_start = tag_start

    # N.B.: caret tags are just of the form <Caret>, not <Caret></Caret>    
    if prev_start == '<' and annot_name != Annot.CARET_NAME:
        return False
        
    return True

def pdf2texSearchRegex(s: str):
    """
    return a regex of the string which we can use to search for it literally up to whitespace,
    where all individual white space characters are treated the same
    """
    return ''.join(
        r'(?:\s+?|\s*~+\s*)' if re.match(r'^\s$', c) is not None else re.escape(c)
        for c in s
    )


def matchingText(regex, string):
    m = re.search(regex, string)
    return string[m.start():m.end()]

def progressiveAutocorrectAttempt(corr: Correction, **kwargs):
    tag_name = Annot.to_selection_tag_name(corr.annot_name)
    annotated_pdf_text = corr.pdf_selected_text

    existing_snippet = kwargs.get('snippet', None)
    latex_snippet = corr.latex_snippet if existing_snippet is None else existing_snippet

    regex = rf"<{tag_name}>(.*?)</{tag_name}>"
    match = list(re.finditer(regex, annotated_pdf_text, flags=re.DOTALL))

    if len(match) == 0:
        logger.error(
            "No match despite valid tags from "
            f"'{regex}' on '{annotated_pdf_text}'"
        )
        return None
    if len(match) > 1:
        logger.debug(f"More than one set of tags in {annotated_pdf_text}")
        return None

    m = match[0]

    # l for literal
    between_tags_lregex = pdf2texSearchRegex(m.group(1))
    
    comment_text = utils.backslashEscape(
        utils.UnicodeToTeX(corr.messages['comment'])
    )

    # simple attempt first
    simple_auto, num_subs = re.subn(
        between_tags_lregex,
        comment_text,
        latex_snippet,
    )

    # keep track of
    # (new text, length of regex used to make the sub) 
    # tuples
    # We only care about autocorrects which carry out just one substitution,
    # and if there are more than one of those
    # (since we look at the left, right, and left and right text possibilities)
    # take the one which matched the longest length string in the LaTeX

    # This is done to reduce false positives.
    # Better than the greedy approach before
    # and these checks are essentially free. No need
    # to worry about resources here.
    
    if num_subs == 0:
        return None
    if num_subs == 1:
        return simple_auto

    contending_autocorrects = []

    left_context  = annotated_pdf_text[:m.start()]
    right_context = annotated_pdf_text[m.end():]

    # progressive expansion using annotation context
    max_left  = len(left_context)
    max_right = len(right_context)
    max_k = max(max_left, max_right)

    for k in range(1, min(max_k, MAX_PROGRESSIVE_AUTO_ATTEMPTS) + 1):
        left_chars  = left_context[-k:] if k <= max_left  else None
        right_chars = right_context[:k] if k <= max_right else None

        if left_chars is not None:
            l_regex = pdf2texSearchRegex(left_chars)
            m_left = rf'({l_regex})({between_tags_lregex})'
            auto_left, ns_left = re.subn(
                m_left,
                rf'\1{comment_text}',
                latex_snippet,
            )
            if ns_left == 1:
                contending_autocorrects.append(
                    (auto_left, len(matchingText(m_left, latex_snippet)))
                )

        if right_chars is not None:
            r_regex = pdf2texSearchRegex(right_chars)
            m_right = rf'({between_tags_lregex})({r_regex})'
            auto_right, ns_right = re.subn(
                m_right,
                rf'{comment_text}\2',
                latex_snippet,
            )
            if ns_right == 1:
                contending_autocorrects.append(
                    (auto_right, len(matchingText(m_right, latex_snippet)))
                )

        if left_chars is not None and right_chars is not None:
            l_regex = pdf2texSearchRegex(left_chars)
            r_regex = pdf2texSearchRegex(right_chars)
            m_ambi = rf'({l_regex})({between_tags_lregex})({r_regex})'
            auto_ambi, ns_ambi = re.subn(
                m_ambi,
                rf'\1{comment_text}\3',
                latex_snippet,
            )
            if ns_ambi == 1:
                contending_autocorrects.append(
                    (auto_ambi, len(matchingText(m_ambi, latex_snippet)))
                )
    if not contending_autocorrects:
        return None

    (best_auto, len_best_match) = max(
        contending_autocorrects,
        key=lambda cauto: cauto[1]
    )

    if len_best_match < MIN_MATCH_FOR_AUTO:
        # ic(best_auto, len_best_match)
        return None
    
    return best_auto

def newCaretAutocorrect(corr: Correction, **kwargs):
    """should be refactored with progressiveAutocorrectAttempt"""
    tag_name = Annot.to_selection_tag_name(Annot.CARET_NAME)
    annotated_pdf_text = corr.pdf_selected_text

    existing_snippet = kwargs.get('snippet', None)
    latex_snippet = corr.latex_snippet if existing_snippet is None else existing_snippet

    regex = rf"<{tag_name}>"
    match = list(re.finditer(
            re.escape(regex),
            annotated_pdf_text,
    ))

    if len(match) == 0:
        logger.error(
            "No match despite valid tags from "
            f"'{regex}' on '{annotated_pdf_text}'"
        )
        return None
    
    if len(match) > 1:
        logger.error(
            f"More than one caret in PDF selection text '{annotated_pdf_text}'"
            f"for annot on page {annot.pageno} despite passing tag"
            "validation"
        )
        return None
        
    m = match[0]
    left_text = annotated_pdf_text[:m.start()]
    right_text = annotated_pdf_text[m.end():]

    max_left = len(left_text)
    max_right = len(right_text)
    max_k = max(max_left, max_right)

    insert_text = utils.backslashEscape(
        utils.UnicodeToTeX(corr.messages['comment'])
    )

    contending_autocorrects = []

    for k in range(1, min(max_k, MAX_PROGRESSIVE_AUTO_ATTEMPTS) + 1):
        left_chars = left_text[-k:] if k <= max_left else None
        right_chars = right_text[:k] if k <= max_right else None

        if left_chars is not None:
            l_regex = pdf2texSearchRegex(left_chars)
            m_left = rf'({l_regex})'
            auto_left, ns_left = re.subn(
                m_left,
                rf'\1{insert_text}',
                latex_snippet,
            )
            if ns_left == 1:
                contending_autocorrects.append(
                    (auto_left, len(matchingText(m_left, latex_snippet)))
                )
        if right_chars is not None:
            r_regex = pdf2texSearchRegex(right_chars)
            m_right = rf'({r_regex})'
            auto_right, ns_right = re.subn(
                m_right,
                rf'{insert_text}\1',
                latex_snippet,
            )
            if ns_right == 1:
                contending_autocorrects.append(
                    (auto_right, len(matchingText(m_right, latex_snippet)))
                )
        if left_chars is not None and right_chars is not None:
            l_regex = pdf2texSearchRegex(left_chars)
            r_regex = pdf2texSearchRegex(right_chars)
            m_ambi = rf'({l_regex})({r_regex})'
            auto_ambi, ns_ambi = re.subn(
                m_ambi,
                rf'\1{insert_text}\2',
                latex_snippet,
            )
            if ns_ambi == 1:
                contending_autocorrects.append(
                    (auto_ambi, len(matchingText(m_ambi, latex_snippet)))
                )
    if not contending_autocorrects:
        return None
        
    (best_auto, len_best_match) = max(
        contending_autocorrects,
        key=lambda cauto: cauto[1]
    )

    if len_best_match < MIN_MATCH_FOR_AUTO:
        # ic(best_auto, len_best_match)        
        return None
    
    return best_auto

def correctSnippet(corr: Correction, **kwargs):
    if corr.annot not in {
            Annot.CARET,
            Annot.REPLACE,
            Annot.REMOVE
    }:
        return None
    
    pdf_selection_text = corr.pdf_selected_text
    if not tagsAreValid(pdf_selection_text, corr.annot_name):
        logger.warning(
            f"Invalid tags: {pdf_selection_text} "
            f"for corr on page {corr.pageno} with comment"
            f" {corr.messages['comment']}"
        )
        return None
    else:
        logger.debug(f"'{pdf_selection_text}' is valid!")

    comment_text = corr.messages['comment']

    # expect empty comment with remove annotation
    if corr.annot == Annot.REMOVE and comment_text != '':
        logger.debug(
            f"Remove annotation on page {corr.pageno} "
            "did not have empty comment text"
        )
        return None

    # some insertion/replacement text is 
    # very likely not literal
    not_literal = '|'.join((
        r'\b(pls|please)\s*link\b',
        r'<\s*(pls|please)?link\s*>',
        r'\bCOMP\b',
        r'\bAU\b',
        r'\bPE\b',
        r'\bTEG\b',
        r'\bPTG\b',
        r'\bbreak\b',
    )) 
    
    if re.search(not_literal, comment_text, flags=re.IGNORECASE):
        return None

    if corr.annot in {Annot.REPLACE, Annot.REMOVE}:
        return progressiveAutocorrectAttempt(corr, **kwargs)
    else: 
        return newCaretAutocorrect(corr, **kwargs)

def getCorrectedSnippets(
        corrections: list[Correction],
        overlapping_keys: list[list[int]]
) -> dict[int, str]:
    """ Carry out simple (strikeout, replace, or caret) corrections to the LaTeX source string
    Return corrected_snippets: dictionary of correction keys (correction indicies) -> corrected latex snippets (strings)

    Note: overlapping corrections must be grouped
    """
    key_to_correction = {corr.index: corr for corr in corrections}
    standalone_keys = [
        corridx
        for corridx in key_to_correction
        if corridx not in {idx for group in overlapping_keys for idx in group}
    ]

    corrected_snippets = {corr.index: None for corr in corrections}
    
    for s_key in standalone_keys:
        corr = key_to_correction[s_key]
        corrected_snip = correctSnippet(corr)
        if corrected_snip is not None:
            corrected_snippets[s_key] = corrected_snip            
            corr.is_autocorrected = True

    for group in overlapping_keys:
        existing_snippet = None
        for g_key in group:
            corr = key_to_correction[g_key]
            corrected_snip = correctSnippet(
                corr,
                snippet=existing_snippet
            )
            if corrected_snip is None:
                continue
            
            corrected_snippets[g_key] = corrected_snip
            corr.is_autocorrected = True
            
            # update all of the corrected snippets in the group
            for g_key in group:
                corrected_snippets[g_key] = corrected_snip
                
            existing_snippet = corrected_snip
    
    return corrected_snippets

def getSourcePosToCorrections(corrections: list[Correction]):
    char_positions = []
    charpos_to_kinds_and_corrections = dict()
    for corr in corrections:
        (start_pos, end_pos) = corr.snippet_source_positions
        if start_pos in charpos_to_kinds_and_corrections:
            charpos_to_kinds_and_corrections[start_pos].append(('start', corr))
        else:
            charpos_to_kinds_and_corrections[start_pos] = [('start', corr)]
        if end_pos in charpos_to_kinds_and_corrections:
            charpos_to_kinds_and_corrections[end_pos].append(('end', corr))
        else:
            charpos_to_kinds_and_corrections[end_pos] = [('end', corr)]
        char_positions.extend([start_pos, end_pos])

    char_positions = sorted(set(char_positions))
    return (char_positions, charpos_to_kinds_and_corrections)

def insert_comments(
        inserts: list[int],
        comments: list[str],
        tex_str: str,
) -> str:
    """Insert comment at the beginning of a line

    tex_str before the comment
    comment
    tex_str after comment
    """
    if len(inserts) != len(comments):
        logger.error("number of comments and insertion points don't match")
        return tex_str
    
    for insert in inserts:
        if insert >= len(tex_str) or insert < 0:
            logger.error(f"Insert idx out of range: {insert}")
            return tex_str
        
    for comment in comments: 
        expected_comment_format = re.match(
            r"^(^\s* % .*? \n)+$",
            comment,
            flags = re.MULTILINE | re.VERBOSE,
        )
        if expected_comment_format is None:
            logger.warning(f"Comment formatted incorrectly: {comment}")
            return tex_str

    inserts.insert(0, 0)

    tex_with_comments = []
    for i in range(1, len(comments)+1):
        tex_with_comments.extend(
            (
                tex_str[inserts[i-1]:inserts[i]],
                comments[i-1],
            )
        )
    tex_with_comments.extend(tex_str[inserts[-1]:])

    return ''.join(tex_with_comments)

def new_comment_source(
        tex_str: str,
        char_positions: list[int],
        charpos_to_kinds_and_corrections: dict[int, list[tuple[str, Correction]]],
        **kwargs
) -> str:

    corrected_snippets = kwargs.get('corrected_snippets', None)
    format             = kwargs.get('comment_format', formatcomm.DEFAULT_COMMENT_FORMAT)
    
    inserted_comments = [] #list of tuples where tuple[0] is the char_pos and tuple[1] is the inserted material
    for char_pos in char_positions:
        kinds_and_corrs = charpos_to_kinds_and_corrections[char_pos]
        corr_descriptions = []
        start_corr_idxs, end_corr_idxs = [], []
        for kind_and_corr in kinds_and_corrs:
            (kind, corr) = kind_and_corr
            if kind == 'start':
                corr_descriptions.append(corr.asCommentStart(format))
                start_corr_idxs.append(corr.index)
            elif kind == 'end':
                corr_descriptions.append(corr.asCommentEnd(format)) # new with 0.12.0
                end_corr_idxs.append(corr.index)
            else:
                assert False, f"Invalid kind of position '{kind}'."
        
        start_end_callout = []

        if end_corr_idxs:
            start_end_callout.append(
                formatcomm.writeCallout(
                    end_corr_idxs,
                    'end',
                    format
                )
            )

        if end_corr_idxs and start_corr_idxs:
            logger.error(
                f"The start of correction(s) {start_corr_idxs} "
                f"coincided with the end of correction(s) {end_corr_idxs} "
                f"merging of the overlapping snippets failed"
            )
            start_end_callout.append('%% double trouble\n')
            
        if start_corr_idxs:
            start_end_callout.append(
                formatcomm.writeCallout(
                    start_corr_idxs,
                    'start',
                    format
                )
            )

        description_str = ''.join(corr_descriptions)
        callout_str = ''.join(start_end_callout)

        if start_corr_idxs:
            inserted_comments.append((
                char_pos,
                f'{description_str}{callout_str}'
            ))
        elif end_corr_idxs:
            inserted_comments.append((
                char_pos,
                f'{callout_str}{description_str}'
            ))
        else:
            logger.error(
                "There were neither start or end "
                "correction indices?"
            )

    inserts = [
        char_pos
        for char_pos, _ in inserted_comments
    ]
    comments = [
        comment
        for _, comment in inserted_comments
    ]
    return insert_comments(inserts, comments, tex_str)
