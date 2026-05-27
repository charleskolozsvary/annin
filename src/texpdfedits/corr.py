import logging
logger = logging.getLogger(__name__)

import argparse
import pymupdf
import json
import re
import sys
from pathlib import Path
from icecream import ic

import texpdfedits.extract as extract
import texpdfedits.utils as utils
import texpdfedits.sync as sync
from texpdfedits.extract import Edit, AnnotType

PROG_DISPLAY_FACTOR = 10

def _markdown_codeblock(string: str, language: str = 'latex') -> str:
    return f"```{language}\n{string}\n```"

class Correction(Edit):
    @classmethod
    def _from_edit(cls, edit, index, latex_snippet, span, synctex_lineno):
        return cls(
            edit.pageno,
            edit.type,
            edit.messages,
            edit.selection,
            edit.sync_rect,
            edit.selection_rects,
            index,
            latex_snippet,
            span,
            synctex_lineno
        )
        
    def __init__(
            self,
            pageno: int, 
            type: AnnotType,
            messages: dict[str, str | list[str]], 
            selection: str, 
            sync_rect: pymupdf.Rect,
            selection_rects: list[pymupdf.Rect], 
            index: int, # zero indexed correction id no. 
            latex_snippet: str,
            span: tuple[int, int], # character level
            synctex_lineno: int,
    ):
        super().__init__(pageno, type, messages, selection, sync_rect, selection_rects)
        self.index          = index
        self.latex_snippet  = latex_snippet
        self.span           = span
        self.synctex_lineno = synctex_lineno

        self.is_autocorrected = False
        self.group = None

    def __repr__ (self): 
        return json.dumps({
            "index" : self.index,
            "pageno": self.pageno,
            "type": self.type.label,
            "messages": {
                "comment": self.messages['comment'],
                "responses": self.messages['responses']
            },
            "Selection": self.selection,
            "PDF rectangle": str(self.pdf_annot_rect),
            "LaTeX snippet": self.latex_snippet,
            "Snippet positions": self.span,
            "SyncTeX line no.": self.synctex_lineno,
        }, indent=4, ensure_ascii=False)

    def as_comment(self) -> str:
        import texpdfedits.formatcomm as formatcomm
        replies = '", "'.join(
            utils.sanitize_pdf_text(reply)
            for reply in self.messages['responses']
        )
        return formatcomm.start_comment(self, replies)
    
    def as_codeblock(self) -> str:
        return f"```latex\n{self.latex_snippet}\n```"

    @staticmethod
    def _markdown_replies(replies: list[str]) -> str:
        if not replies:
            return ''
        items = [
            f'\n\n### Reply {i}\n```text\n{reply}\n```'
            for i, reply in enumerate(replies, start=1)
        ]
        return '\n\n### Replies ' + ''.join(items)    
    
    def as_markdown(self) -> str:
        replies = self._markdown_replies(self.messages['responses'])
        return rf"""### Annotation: {self.type.label}

### Comment
```text
{self.messages['comment']}
```{replies}

### PDF selected text
```text
{self.selection}
```
  
### LaTeX snippet
```latex
{self.latex_snippet}
```"""
    
    def _update_snippet(self, span: tuple[int, int], snippet: str) -> None:
        self.span = span
        self.latex_snippet = snippet

def _group_overlapping(keyed_spans: dict[int, tuple[int, int]]) -> list[list[int]]:
    """
    Args:
        keyed_spans: dictionary from keys int
                          to start and end values tuple[int, int]
    Returns:
        list of lists of keys whose start and end values overlap
        (singleton [[key], ...] doesn't overlap)
    """
    if not keyed_spans:
        return []

    keys = sorted([k for k in keyed_spans], key=lambda k: keyed_spans[k])

    groups = []
    curr_group = [keys[0]]
    _, curr_group_end = keyed_spans[keys[0]]
    for i, key in enumerate(keys):
        if i == 0:
            continue
        start, end = keyed_spans[key]
        if start <= curr_group_end:
            curr_group.append(key)
            curr_group_end = max(curr_group_end, end)
        else:
            groups.append(curr_group)
            curr_group = [key]
            curr_group_end = end
    groups.append(curr_group)
    return groups

def _validate_merge(corrections: list[Correction], merged_corrs: list[list[Correction]]) -> None:
    num = 0
    for group in merged_corrs:
        for corr in group:
            if corr not in corrections:
                logger.critical(f"{corr} not in {corrections}")
                raise RuntimeError("Merged corrections invalid: missing member")
            num += 1
    if len(corrections) != num:
        logger.critical(f"{len(corrections)} != {num}")
        raise RuntimeError("Merged corrections invalid: nonequal lengths")
    len_sets_of_spans = [
        len(set(corr.span for corr in group))
        for group in merged_corrs
    ]
    all_ones = [
        1 for group in merged_corrs
    ]
    if len_sets_of_spans != all_ones:
        raise RuntimeError("merged_corr spans invalid")
    spans = [
        group[0].span
        for group in merged_corrs
    ]
    # ic(spans)
    prev_span = spans[0]
    for i, span in enumerate(spans):
        if i == 0:
            continue
        p_start, p_end = prev_span
        start, end = span
        if not (p_start < p_end and start < end):
            raise RuntimeError("Spans invalid, starts not less than ends")
        if not p_start < start:
            raise RuntimeError(f"Merged spans {prev_span} and {span} out of order")
        if not p_end < start:
            raise RuntimeError(f"Merged spans {prev_span} and {span} overlap")
        prev_span = span
    return 

def _merge_corrections(corrections: list[Correction], tex_str: str) -> list[list[Correction]]:
    """
    Merge overlapping corrections
    Returns:
        list of lists of correction indices which are merged
    
    Updates the passed correction objects themselves
    Maybe should return new list of corrections instead
    """    
    if not corrections:
        return []

    key_to_correction = {corr.index: corr for corr in corrections}
    key_to_span = {corr.index: corr.span for corr in corrections}
    groups = _group_overlapping(key_to_span)

    for group in groups:
        if len(group) == 0:
            raise RuntimeError("Unexpected empty group while merging corrections")
        elif len(group) == 1:
            continue
        spans_in_group = sorted(key_to_span[key] for key in group)
        min_start, _ = spans_in_group[0]
        _, max_end   = spans_in_group[-1]
        containing_snippet = tex_str[min_start:max_end]
        for key in group:
            correction = key_to_correction[key]
            if not correction.latex_snippet in containing_snippet:
                logger.critical(
                     "Could not merge corrections: "
                    f"a snippet \n{correction.as_codeblock()}\n was not in its"
                    f" spanning snippet \n{_markdown_codeblock(containing_snippet)}\n"
                )
                raise RuntimeError("Could not merge corrections")
            correction._update_snippet((min_start, max_end), containing_snippet)
            correction.group = group
    merged_corrs = sorted(
        [[key_to_correction[key] for key in group]
        for group in groups],
        key=lambda g: g[0].span
    )
    _validate_merge(corrections, merged_corrs)
    return merged_corrs

def _make_correction(
        line2pos: dict[int, int],
        tex_str: str,
        input_file: Path,
        output_file: Path,        
        edit: Edit,
        i: int,
) -> Correction:
    logger.debug(f"Getting latex snippet for edit {edit}...")
    # if it's worth handling individual correction
    # exceptions, do it here
    latex_snippet, span, synctex_lineno = sync.rectangle_to_latex(
        edit.pageno,
        edit.sync_rect,
        line2pos,
        tex_str,
        input_file,
        output_file,
    )
    logger.debug(f"Done")    
    return Correction._from_edit(edit, i, latex_snippet, span, synctex_lineno)

def get_corrections(
        tex_file: Path,
        compilation_output: Path,        
        edits: list[Edit],
) -> list[list[Correction]]:
    tex_str = utils.source_as_string(tex_file)
    line2pos = sync.build_line_map(tex_file)

    logger.info("Running SyncTeX to make correction objects...")
    corrections = []
    
    progress_len = len(edits) // PROG_DISPLAY_FACTOR
    bar = utils.TextProgressBar(progress_len)
    bar.show_size()
    
    for i, edit in enumerate(edits, start=1):
        corr = _make_correction(
            line2pos,
            tex_str,
            tex_file,
            compilation_output,
            edit,
            i, 
        )
        corrections.append(corr)
        if i % PROG_DISPLAY_FACTOR == 0:
            bar.add_progress()
    bar.end()
    logger.info("Done")

    logger.info(
        f"Produced {len(corrections)} corrections from "
        f"{len(edits)} edit annotations"
    )

    corrections = _merge_corrections(corrections, tex_str)

    return corrections
