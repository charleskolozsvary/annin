"""Modify the original LaTeX source"""
import logging
logger = logging.getLogger(__name__)
import pymupdf
import re
import sys
from pathlib import Path
from icecream import ic

import texpdfedits.utils as utils
import texpdfedits.formatcomm as formatcomm

from texpdfedits.corr import Correction
from texpdfedits.extract import AnnotType, Annot

MAX_PROGRESSIVE_AUTO_ATTEMPTS = 10
# autocorrect must match at least this many characters
MIN_MATCH_FOR_AUTO = 5 

NONLITERAL_COMMENT = (
    r'\b(pls|please)\s*link\b',
    r'<\s*(pls|please)?link\s*>',
    r'\bCOMP\b',
    r'\bAU\b',
    r'\bPE\b',
    r'\bTEG\b',
    r'\bPTG\b',
    r'\bbreak\b',
)

INLINED_TAG = 'inlined'
AUTO_TAG = 'autocorrected'

def _tags_are_valid(tagged_text: str, annot_type: AnnotType) -> bool:
    tag_regex = r'(</?)([a-zA-Z^‸]+)>'
    all_tags = list(re.finditer(tag_regex, tagged_text))
    if not all_tags:
        logger.warning("string passed for tag validation contained no tags")
        return True
    
    tag_info = [(tag.group(1), tag.group(2)) for tag in all_tags]
    (tag_starts, tag_names) = zip(*tag_info)

    # should have even number for noncaret tags
    if annot_type != AnnotType.CARET and len(tag_info) % 2 != 0:
        return False

    more_than_one_caret = (
        annot_type == AnnotType.CARET
        and tag_names.count(Annot.to_selection_tag_name(annot_type)) > 1
    )
    if more_than_one_caret:
        return False

    # more than one kind of tag (annotation) would be odd
    if len(set(tag_names)) != 1:
        logger.warning(f"Detected more than one kind of tag in selection: {tag_names}")
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
    if prev_start == '<' and annot_type != AnnotType.CARET:
        return False
        
    return True

def _pdf2tex_search_regex(s: str):
    """
    return a regex of the string which we can use to
    search for it literally up to whitespace.

    It's helpful to collapse a line break, single space,
    or (specifically for TeX) tilde for the autocorrect search
    """
    return ''.join(
        r'(?:\s+?|\s*~+\s*)' if re.match(r'^\s$', c) is not None else re.escape(c)
        for c in s
    )

def _matching_text(regex: str, string: str) -> str:
    m = re.search(regex, string)
    return string[m.start():m.end()]

def _growing_context_auto(
        snippet: str,
        comment: str,
        left: str,
        right: str,
        tag_adjacent_regex: str,
) -> str:
    max_left = len(left)
    max_right = len(right)
    max_k = max(max_left, max_right)
    contending_autocorrects = []
    for k in range(1, min(max_k, MAX_PROGRESSIVE_AUTO_ATTEMPTS) + 1):
        left_chars  = left[-k:] if k <= max_left  else None
        right_chars = right[:k] if k <= max_right else None

        if left_chars is not None:
            l_regex = _pdf2tex_search_regex(left_chars)
            m_left = rf'({l_regex}){tag_adjacent_regex}'
            auto_left, ns_left = re.subn(
                m_left,
                rf'\1{comment}',
                snippet,
            )
            if ns_left == 1:
                contending_autocorrects.append(
                    (auto_left, len(_matching_text(m_left, snippet)))
                )

        if right_chars is not None:
            r_regex = _pdf2tex_search_regex(right_chars)
            m_right = rf'{tag_adjacent_regex}({r_regex})'
            auto_right, ns_right = re.subn(
                m_right,
                rf'{comment}\1',
                snippet,
            )
            if ns_right == 1:
                contending_autocorrects.append(
                    (auto_right, len(_matching_text(m_right, snippet)))
                )

        if left_chars is not None and right_chars is not None:
            l_regex = _pdf2tex_search_regex(left_chars)
            r_regex = _pdf2tex_search_regex(right_chars)
            m_ambi = rf'({l_regex}){tag_adjacent_regex}({r_regex})'
            auto_ambi, ns_ambi = re.subn(
                m_ambi,
                rf'\1{comment}\2',
                snippet,
            )
            if ns_ambi == 1:
                contending_autocorrects.append(
                    (auto_ambi, len(_matching_text(m_ambi, snippet)))
                )
    if not contending_autocorrects:
        logger.debug(f"contending_autocorrects empty for {snippet}")
        return None

    (best_auto, len_best_match) = max(
        contending_autocorrects,
        key = lambda contender: contender[1]
    )

    if len_best_match < MIN_MATCH_FOR_AUTO:
        # ic(best_auto, len_best_match)
        return None
    
    return best_auto

def _autocorrect(corr: Correction, latex_snippet: str) -> str | None:
    tag_name = Annot.to_selection_tag_name(corr.type)
    annotated_pdf_text = corr.selection

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

    [m] = match
    between_tags_literal_regex = _pdf2tex_search_regex(m.group(1))
    comment_text = utils.backslash_escape(utils.unicode_to_tex(corr.messages['comment']))

    simple_auto, num_subs = re.subn(
        between_tags_literal_regex,
        comment_text,
        latex_snippet,
    )
    
    if num_subs == 0:
        return None
    if num_subs == 1:
        return simple_auto

    left  = annotated_pdf_text[:m.start()]
    right = annotated_pdf_text[m.end():]

    return _growing_context_auto(
        latex_snippet,
        comment_text,
        left,
        right,
        between_tags_literal_regex,
    )

def _caret_autocorrect(corr: Correction, latex_snippet: str) -> str | None:
    tag_name = Annot.to_selection_tag_name(corr.type)
    annotated_pdf_text = corr.selection

    regex = rf"<{tag_name}>"
    # re.escape in case caret tag_name is ^ not CARET
    match = list(re.finditer(re.escape(regex), annotated_pdf_text))

    if len(match) == 0:
        logger.error(
            "No match despite valid tags from "
            f"'{regex}' on '{annotated_pdf_text}'"
        )
        return None
    
    if len(match) > 1:
        logger.error(
            f"More than one caret in PDF selection text '{annotated_pdf_text}'"
            f"for annot on page {annot.pageno} despite passing tag validation"
        )
        return None
        
    [m] = match
    left = annotated_pdf_text[:m.start()]
    right = annotated_pdf_text[m.end():]
    insert_text = utils.backslash_escape(utils.unicode_to_tex(corr.messages['comment']))

    return _growing_context_auto(
        latex_snippet,
        insert_text,
        left,
        right,
        '',
    )

def _correct_snippet(corr: Correction, snippet: str) -> str | None:
    if corr.type not in {
            AnnotType.CARET,
            AnnotType.REPLACE,
            AnnotType.STRIKE_OUT
    }:
        return None
    
    selection = corr.selection
    if not _tags_are_valid(selection, corr.type):
        raise ValueError(
            f"Invalid selection tags '{selection}'"
            f"for correction {corr.index}"
        )
    logger.debug(f"valid selection tags: '{selection}'")

    # some simple heuristics can inform whether
    # some corrections are worth autocorrecting
    comment = corr.messages['comment']
    if corr.type == AnnotType.STRIKE_OUT and comment:
        return None

    likely_not_literal = re.search(
        '|'.join(NONLITERAL_COMMENT),
        comment,
        flags = re.IGNORECASE,
    )
    
    if likely_not_literal is not None:
        return None

    if corr.type in {AnnotType.REPLACE, AnnotType.STRIKE_OUT}:
        return _autocorrect(corr, snippet)
    else: 
        return _caret_autocorrect(corr, snippet)

def _check_spans(spans: list[tuple[int, int]]) -> bool:
    if not spans:
        return
    prev_span = (0, 0)
    for span in spans:
        start, end = span
        if start >= end:
            raise RuntimeError(f"{start} >= {end}")
        prev_start, prev_end = prev_span
        if prev_end >= start:
            raise RuntimeError(f"{prev_span} overlaps with {span}")
        prev_span = span
    return 

def _partition_source(
        tex_str: str,
        corrections: list[list[Correction]],
) -> list[str]:
    spans = [group[0].span for group in corrections]
    # ic(spans)

    _check_spans(spans)
    
    insertions = [
        index for span in spans
        for index in span
    ]

    if len(set(insertions)) != 2 * len(spans):
        raise RuntimeError(
            f"Insertion points for comments from spans contained "
            f"duplicates or unpacked incorrectly"
        )
    insertions.insert(0, 0)
    insertions.append(len(tex_str))
    
    partition = {}
    for i, insert in enumerate(insertions):
        if i == 0:
            continue
        prev = insertions[i-1]
        is_snippet = (prev, insert) in spans
        key = (is_snippet, (prev, insert))
        partition[key] = tex_str[prev:insert]
    # ic(sorted(partition, key=lambda k: k[1]))

    # dictionary should remain ordered
    restored_partition = ''.join(str_splice for str_splice in partition.values())
    if restored_partition != tex_str:
        logger.critical(
            f"Failed to partition:\n'{restored_partition}'\n!=\n'{tex_str}'"
        )
        raise RuntimeError("Could not partition source: source not conserved")
    return partition

def _do_autocorrections(
        corrections: list[list[Correction]],
        partition: dict[tuple[bool, tuple[int, int]], str],
) -> dict[tuple[bool, tuple[int, int]], str]:
    num_corrected = 0
    for group in corrections:
        key = (True, group[0].span)
        snippet = partition[key]
        for corr in group:
            autod = _correct_snippet(corr, snippet)
            if autod is None:
                continue
            snippet = autod
            # latex_snippets updated to reflect
            # state after *their* autocorrect complete
            # for debugging I suppose
            # The actual record of the snippet is in the
            # modified partition
            corr.latex_snippet = autod 
            corr.is_autocorrected = True
            num_corrected += 1
        partition[key] = snippet
    logger.info(f"Performed {num_corrected} autocorrections")
    return partition

def _assemble_with_comments(
        corrections: list[list[Correction]],
        partition: dict[tuple[bool, tuple[int, int]], str],
        autocorrect: bool,
) -> str:
    if autocorrect:
        partition = _do_autocorrections(corrections, partition)
    span_to_group = {
        group[0].span : group
        for group in corrections
    }
    commented_source = []
    for (is_snippet, span), snippet in partition.items():
        if not is_snippet:
            commented_source.append(snippet)
            continue
        group = span_to_group[span]
        corr_idxs = [corr.index for corr in group]
        
        start_callout = formatcomm.write_callout(corr_idxs, 'start')
        comment_body = ''.join(corr.as_comment() for corr in group)
        end_callout = formatcomm.write_callout(corr_idxs, 'end')
        
        commented_source.append(start_callout)
        commented_source.append(comment_body)
        commented_source.append(snippet)
        commented_source.append(end_callout)

    return ''.join(commented_source)
                
def inline_comments(
        latex_file: Path,
        corrections: list[list[Correction]],
        autocorrect: bool = False,
) -> Path:
    tex_str = utils.source_as_string(latex_file)
    
    partition = _partition_source(tex_str, corrections)
    
    source_with_comments = _assemble_with_comments(
        corrections,
        partition,
        autocorrect
    )
    
    tag = AUTO_TAG if autocorrect else INLINED_TAG
    commented_file = utils.new_tagged_fname(latex_file, tag)        
    utils.write_string_to_file(source_with_comments, commented_file)
    
    return commented_file
    
