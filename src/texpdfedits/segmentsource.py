# DISCLAIMER: it's possible that it's much easier to track the box positions of words with lualatex
# than pdflatex with pylatexenc, but this appears to be working well enough right now

import argparse
import logging
import re

from pylatexenc.latexwalker import LatexWalker, LatexNode, LatexMacroNode, LatexEnvironmentNode, LatexGroupNode, LatexMathNode, LatexCharsNode, LatexCommentNode
from pylatexenc.macrospec import LatexContextDb, std_macro, std_environment

from itertools import count
from pathlib import Path

import sys
import os
import subprocess

from collections.abc import Callable

import pymupdf 

RECOGNIZED_CSNAMES = {'emph': '{',
                      'textit': '{',
                      'textbf': '{',
                      'textsc': '{',
                      'texttt': '{',
                      'underline': '{',
                      'markbox': '{{',
                      'part': '*[{',
                      'chapter' : '*[{',
                      'section': '*[{',
                      'subsection': '*[{',
                      'subsubsection': '*[{',
                      'thanks': '{',
                      'subjclass': '[{',
                      'datereceived': '{',
                      'daterevised': '{',
                      'commby': '{',
                      'title': '[{',
                      'author': '[{',
                      'address': '[{',
                      'email': '[{',
                      'keywords': '{',
                      'footnote': '[{', # \footnote[10]{text} sets the footnote to be footnote 10---only a number can be passed
                      'caption': '[{',
                      'item': '[',
                      'renewcommand': '*{[{',
                      'newcommand': '*{[{',
                      'theoremstyle' : '{',
                      'bibitem': '[{',
                      'bib': '{{',
                      'newtheorem': '*{[{['} # greedily read all possible arguments to newtheorem, even if optional is not quite right, but that's okay

OPTIONAL_ARG = ('[', ']')

REQUIRED_ARG = ('{', '}')

# macros which themselves get marked like \markbox{<key>}{\macro{...}}
MARKED_CSNAMES = {'emph', 'textit', 'textbf', 'textsc', 'underline', 'texttt'}
# any of these fail if they're arguments are abnormal, like a \[...\] in a \textit
# we should probably do some checking for something like that like
# "check nested nodes are valid. They're shouldn't be any display math nodes inside the argument to any of these commands...

# macros whose contents are marked
# MARKED_CONTENTS_MACROS = {'footnote', 'thanks', 'title', 'address', 'email', 'author', 'keywords'} # no, this was a bad idea

MARK_IDENTIFIERS = {'inline math': 'm'}

TRACKED_ENVIRONMENTS = {'abstract', 'figure', 'table', 'thebibliography', 'biblist'}

METADATA_CSNAMES = {'title', 'author', 'address', 'email', 'thanks', 'subjclass', 'keywords', 'datereceived', 'daterevised', 'commby'}

UNIQUE_FIELDS = {'title', 'subjclass', 'keywords', 'datereceived', 'commby', 'abstract'}

# better to leave out 'abstract' from the marked environments; some journals have the abstract at the end and our marks
# are expected to appear in order.
# this is why we extract the metadata and figures and tables separately, and we'll need to extract the footnotes separately, too
ALLOWED_MARK_ENVIRONMENTS = {'proof', 'enumerate', 'itemize', 'document', 'thebibliography', 'biblist', 'bibdiv', 'bibsec'}

DIFFPDF_DPI = 175
r"""
so far it appears for some reason \eqrefs produce very small differences in
the PDF output when the \markboxes are inserted
(but from what I can tell nothing else causes differences)

If there are 93 eqrefs on a page less than 50_000 pixels are marxed different
(when using DPI = 175; the larger the DPI, the larger the number of pixel differences)
And if a page breaks early by just one line the difference on that and subsequent pages is at
least 275_000
(based on from `diff-pdf teichmuller.pdf breakteich.pdf -v -s -m -g --output-diff=diff_break.pdf --dpi=175`),
so I think marking a page as not different if it differs by less than 50_000 pixels at this DPI is quite conservative.
"""
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 100_000

SCALED_POINTS_PER_TEX_POINT = 2 ** 16 # 65536

"""
there are 72.27 tex pts in an inch, while there are 
72 bp (what tex calls a big point) in an inch, which is what
pymupdf and other modern pdf systems use
"""
TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO = 72 / 72.27

"""
allow for half a point discrepancy between x0 + width and x1
in boxinfoToPDFRectangle()
"""
WORD_BOX_WIDTH_TOLERANCE = 10

def sourceAsString(filename: Path) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def writeStringToFile(string: str, filename: Path):
    with open(filename, 'w', encoding = 'utf-8') as f:
        f.write(string)
    return 0

def joinLatexVerbatimNodes(nodelist, start: int, end: int):
    return ''.join([node.latex_verbatim() for node in nodelist[start:end+1]])

def getEnunciations(preamble_nodes) -> tuple[list[str], str]:
    enunciation_names = set()
    start_idx, end_idx = -1, -1
    for i, node in enumerate(preamble_nodes):
        if node.isNodeType(LatexMacroNode) and node.macroname in {'theoremstyle', 'newtheorem'}:
            if start_idx < 0:
                start_idx = i
            end_idx = i
            if node.macroname == 'theoremstyle':
                continue
            # otherwise try to process \newtheorem
            node_args = node.nodeargd.argnlist
            len_arg_spec = len(RECOGNIZED_CSNAMES[node.macroname])
            if len(node_args) == len_arg_spec and len_arg_spec > 1:
                arg_one = node_args[1]
                try:
                    # currently fails with \\newtheorem{%\nthm}{Theorem}, which I think is fine for now                                        
                    enunciation_names.add(arg_one.nodelist[0].chars)
                except Exception as e: 
                    logging.warning(
                        f"Attempting to extract second argument of '{node.latex_verbatim()}' "
                        f"raised {type(e).__name__}: {e}; "
                        f"node.nodeargs[1] was {arg_one}; ignoring"
                    )                    
            else:
                logging.warning(
                    f"Malformed {node.macroname}, '{node.latex_verbatim()}', "
                    f"did not match it's argument specification: {RECOGNIZED_CSNAMES[node.macroname]}"
                )
    if start_idx < 0:
        logging.warning("No enunciations (newtheorem commands) found; continuing without them.")
    enunciation_source = joinLatexVerbatimNodes(preamble_nodes, start_idx, end_idx)
    return enunciation_names, enunciation_source

def getEnvironmentSources(node, recognized_environments, environments):
    """recognized environments as a dictionary with keys as the environment names
    and values as a list of verbatim latex_code of said environment
    This should preserve order, even though it's recursive since the nesting of nodes
    is still in document order
    Modify the passed environments dictionary
    """
    if node.isNodeType(LatexEnvironmentNode):
        if node.envname in recognized_environments:
            environments[node.envname] += [node.latex_verbatim()]
        else:
            for nested_node in node.nodelist:
                getEnvironmentSources(nested_node, recognized_environments, environments)
    elif node.isNodeType(LatexGroupNode):
        for nested_node in node.nodelist:
            getEnvironmentSources(nested_node, recognized_environments, environments)
    else:
        return
    
def getMetadataAndSelectEnvironments(preamble_nodes, document_node):
    r"""we probably also want to track \footnotes and \captions, too, but I'll think about that later..."""
    metadata = dict()
    start_idx, end_idx = -1, -1
    # this assumes that there isn't weird nesting in the preamble
    # we'll probably have to account for that later with a recursive approach, like with markNode
    # and in extracting the figures, tables, and abstract
    for i, node in enumerate(preamble_nodes): 
        if node.isNodeType(LatexMacroNode) and node.macroname in METADATA_CSNAMES:
            if start_idx < 0:
                start_idx = i
            end_idx = i
            csname = node.macroname            
            verbatim_contents = node.latex_verbatim()
            if csname in metadata and csname in UNIQUE_FIELDS:
                logging.warning(f"Found more than one instance of unique field '{csname}', overwriting earlier instance.")
                metadata[csname] = verbatim_contents
            elif csname in metadata:
                metadata[csname] = [metadata[csname], verbatim_contents] if type(metadata[csname]) != list else metadata[csname] + [verbatim_contents]
            else:
                metadata[csname] = verbatim_contents
    metadata_source = joinLatexVerbatimNodes(preamble_nodes, start_idx, end_idx)

    environments = {env_name: [] for env_name in TRACKED_ENVIRONMENTS}
    getEnvironmentSources(document_node, TRACKED_ENVIRONMENTS, environments)
    
    num_abstract = len(environments['abstract'])
    if num_abstract == 0:
        logging.warning("No abstract found in getMetadataAndSelectEnvironments()")
    elif num_abstract > 1:
        logging.warninig(f"! Found {num_abstract} abstracts; there should only be one")

    return metadata, metadata_source, environments

def runPDFlatex(tex_filename: Path, runs: int = 2) -> subprocess.CompletedProcess:
    """Run pdflatex. Run twice by default to resolve cross-references"""
    result = None
    tex_filename_dir = tex_filename.parent
    for i in range(runs):
        logging.info(f"Running pdflatex (pass {i+1}/{runs})")
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', tex_filename.name],
            cwd=tex_filename_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding='latin-1'
        )
        
        if result.returncode != 0:
            logging.error(
                f"pdflatex failed on pass {i+1} of {tex_filename.name}: {result.stderr}."
                f"Output: {result.stdout}"
            )
            sys.exit(1)
        
    return result

def transferTeXFiles(tex_filename: Path, files_to: Path, move_or_copy: str):
    tex_file_dot_star = f"{tex_filename.stem}.*"
    os.system(f"{move_or_copy} {tex_filename.parent / tex_file_dot_star} {files_to}")

def runDiffpdf(first_fname: str, second_fname: str, output_dir: Path) -> subprocess.CompletedProcess:
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = ['diff-pdf',
                          f'--per-page-pixel-tolerance={DIFFPDF_PER_PAGE_PIXEL_TOLERANCE}',
                          f'--dpi={DIFFPDF_DPI}',
                          '--skip-identical',
                          '--grayscale',
                          '--mark-differences',
                          '--verbose',
                          f'--output-diff={diff_fname}',
                          first_fname,
                          second_fname]
    
    logging.info(f"Running `{' '.join(subprocess_command)}`...")
    result = subprocess.run(subprocess_command,
                            cwd=output_dir)
    
    if result.returncode != 0:
        logging.error(f"{first_fname} and {second_fname} are not identical. See {Path(output_dir) / diff_fname}")        
        sys.exit(1)
    else:
        logging.info(f"PDFs are identical according to diff-pdf")

    return result

def markRequiredArg(node: LatexNode, recMark: Callable[[LatexNode], str]) -> str:
    node_verbatim = node.latex_verbatim()
    
    def joinNodelist(transform: Callable[[LatexNode], str]) -> str:
        return '{' + ''.join([transform(nested_node) for nested_node in node.nodelist]) + '}'

    def markify(nested_node: LatexNode):
        return recMark(nested_node)
    
    if node.isNodeType(LatexGroupNode) and node.delimiters == REQUIRED_ARG:
        joined_verbatim_group = joinNodelist(lambda n: n.latex_verbatim())
        if joined_verbatim_group != node_verbatim:
            return node_verbatim
        else:
            return joinNodelist(markify)
    else:
        return node_verbatim

def markArgnlist(argnlist: list[None | LatexNode], recMark) -> str:
    return ''.join([markRequiredArg(node, recMark) if node is not None else '' for node in argnlist])

def markMacro(node: LatexNode, recMark):
    node_verbatim = node.latex_verbatim()
    
    len_arg_spec = len(RECOGNIZED_CSNAMES[node.macroname])
    argnlist = node.nodeargd.argnlist
    joined_verbatim_macro = rf"\{node.macroname}" + ''.join([n.latex_verbatim() if n is not None else '' for n in argnlist])
                
    if node_verbatim != joined_verbatim_macro:
        logging.warning(
            f"{node.macroname} verbatim, '{node_verbatim}', did not match joined verbatim, "
            f"'{joined_verbatim_macro}'; ignoring..."
        )
        return node_verbatim
    elif len(argnlist) != len_arg_spec:
        logging.warning(
            f"{node.macroname}, {node_verbatim}, did not match argspec len: "
            f"{len(argnlist)} != {len_arg_spec}"
        )
        return node_verbatim
    else:
        return rf"\{node.macroname}" + markArgnlist(argnlist, recMark)

def markNode(start_node: LatexNode, allowed_environments: set[str], chars_node_match_regex: str) -> str:
    """Recursively mark the passsed start_node"""
    counter = count(0)
    def markStr(string: str, mark_identifier: str) -> str:
        return rf'\markbox{{{mark_identifier}{next(counter)}}}{{{string}}}'
        
    def recMark(node):
        node_verbatim = node.latex_verbatim()
        if node.isNodeType(LatexEnvironmentNode):
            verbatim_contents = ''.join([n.latex_verbatim() for n in node.nodelist]) #every LatexEnvironmentNode has a nodelist
            joined_whole = rf'\begin{{{node.envname}}}{verbatim_contents}\end{{{node.envname}}}'
            # could maybe only do the following check if the environment is among allowed_environments
            # but it's safer to check every encountered environment
            if node_verbatim != joined_whole:
                logging.error(f"Environment node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                logging.debug(f"{verbatim_contents} != {joined_whole}")                
                sys.exit(1)
            
            if node.envname in allowed_environments:
                marked_contents = ''
                for nested_node in node.nodelist:
                    marked_contents += recMark(nested_node)
                return rf'\begin{{{node.envname}}}{marked_contents}\end{{{node.envname}}}'
            else:
                return joined_whole
        elif node.isNodeType(LatexMacroNode):
            if node.macroname in MARKED_CSNAMES:
                return markStr(node_verbatim, '')
            elif node.macroname == 'item':
                return f'{node_verbatim}{{}}\\leavevmode ' # this helps and I think it's benign (from my testing so far)
            # elif node.macroname in MARKED_CONTENTS_MACROS: 
            #     return markMacro(node, recMark)
            else:
                return node_verbatim
        elif node.isNodeType(LatexMathNode):
            if node.displaytype == 'inline':
                return markStr(node_verbatim, MARK_IDENTIFIERS['inline math'])
            else:
                return node_verbatim
        elif node.isNodeType(LatexCharsNode):
            # mark every span in safe envs
            marked_str, num_subs = re.subn(chars_node_match_regex, lambda m: markStr(m.group(0), ''), node_verbatim)
            return marked_str
        elif node.isNodeType(LatexGroupNode):
            # for the time being this means that naked group blocks are ignored---will need to revisit
            # I have to be careful though, because if I encounter an unrecognized macro then one of 
            # its arguments could be in a group node.
            return node_verbatim
        elif node.isNodeType(LatexCommentNode):
            return node_verbatim
        else:
            logging.warning(f"Unrecognized latex node '{node.nodeType()}' during markNode(); writing node.latex_verbatim(): '{node_verbatim}'")
            return node_verbatim
        
    return recMark(start_node), next(counter)

def getPreambleAndDocument(nodelist):
    """Read in a list of pylatexenc.latexwalker.<Node>s and return the nodes which belong to the
       preamble and document"""
    num_document_envs = len(list(filter(lambda n: n.isNodeType(LatexEnvironmentNode) and n.envname == 'document', nodelist)))
    if num_document_envs != 1:
        logging.error(r"Found more (or less) than one `\begin{document}`s during getPreambleAndDocument().")
        sys.exit(1)

    i = 0
    while nodelist[i].nodeType() != LatexEnvironmentNode:
        i += 1
    preamble_nodes = nodelist[:i]
    document_node = nodelist[i]
    
    if i+1 < len(nodelist):
        logging.debug(f"Discarded {len(nodelist)-(i+1)} latex node(s) after `\\end{{document}}` during getPreambleAndDocument")

    return preamble_nodes, document_node

def texPointsToPDFpoints(tex_pts: float):
    return tex_pts * TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO

def scaledPointsToPDFpoints(sp: int):
    tex_pts = sp / SCALED_POINTS_PER_TEX_POINT
    return texPointsToPDFpoints(tex_pts)

def unzipHbox(hbox):
    return hbox[0], tuple(map(lambda pts: texPointsToPDFpoints(float(pts)), hbox[1:]))

def unzipPos(stend_xy):
    return stend_xy[0], tuple(map(lambda spts: scaledPointsToPDFpoints(int(spts)), stend_xy[1:-1]))

def boxinfoToPDFRectangle(key: str, hbox, start_xy, end_xy):
    pgA, (width, height, depth) = unzipHbox(hbox)
    pgB, (x0, sy) = unzipPos(start_xy)
    pgC, (x1, ey) = unzipPos(end_xy)

    if pgB != pgC:
        logging.debug(f"box '{key}' spanned multiple pages ({pgA} {pgB} {pgC}; ignoring")
        return None
    if sy != ey:
        logging.debug(f"box '{key}' start and end y positions were not equal: '{sy} != {ey}'; ignoring")
        return None
    if abs(x0 + width - x1) > WORD_BOX_WIDTH_TOLERANCE:
        logging.debug(f"box '{key}' abs(x0 + width - x1) = abs({x0 + width} - {x1}) = {abs(x0 + width - x1)} > {WORD_BOX_WIDTH_TOLERANCE}; ignoring")
        return None

    # lower y values are closer to the top of the page
    # return pageno, (x0, y0, x1, y1), where
    # (x0, y0) is the top left corner and
    # (x1, y1) is the bottom right corner of the rectangle
    return pgB, pymupdf.Rect(x0, sy - height, x1, sy + depth)
        
def getWordBoxes(boxpositions_filename: Path, tot_num_boxes):
    word_boxes = dict()
    not_colon = r'([^:]*)'

    with open(boxpositions_filename, 'r') as f:
        line = f.readline().strip()
        line_no = 1
        while line:
            box_info = re.match(fr"^(m?\d+):(pwhd|spxy|epxy):(\d+):{not_colon}:{not_colon}:{not_colon}$", line)
            if box_info is None:
                logging.error(f"Line {line_no} of {boxpositions_filename} '{repr(line)}' did not match the info spec")
                sys.exit(1)
            matches = box_info.groups()
            key, label, values = matches[0], matches[1], tuple(map(lambda m: m.strip('pt'), matches[2:]))
            
            if key in word_boxes:
                if label in word_boxes[key]:
                    # There should be only three labels (and they should each appear at most once):
                    # 'pwhd' for page, width, height, depth; 'spxy' for start, page, x pos, y pos;
                    # and 'epxy' for end, page, x pos, y pos
                    logging.error(f"Key '{key}' with label '{label}' was already in '{word_boxes[key]}'")
                    sys.exit(1)
                word_boxes[key][label] = values
            else:
                word_boxes[key] = {label:values}
            line = f.readline().strip()
            line_no += 1

    if not all(map(lambda x: len(x) == 3, word_boxes.values())):
        # all marks should have exactly three fields, the hbox dimensions, start xy, and end xy positions        
        logging.error(f"Box information in '{boxpositions_filename}' differed from specification")
        sys.exit(1)

    num_used_boxes = 0

    document_word_boxes = dict()
    for key, info in word_boxes.items():
        res = boxinfoToPDFRectangle(key, info['pwhd'], info['spxy'], info['epxy'])
        if res is None:
            continue
        one_indexed_pageno, rectangle = res
        pageno = int(one_indexed_pageno) - 1
        if pageno in document_word_boxes:
            document_word_boxes[pageno][key] = rectangle
        else:
            document_word_boxes[pageno] = {key:rectangle}
        num_used_boxes += 1

    logging.info(f"Used {num_used_boxes}/{tot_num_boxes} marked boxes.")
    return document_word_boxes

def unMark(marked_string: str):
    r"""Remove \markbox commands, keeping only the second argument's contents.
    Maybe a little silly, but this appears to work and I know exactly how I inserted the markbox csnames, so
    this should be fine
    """
    
    def readBalancedBraces(idx, string):
        """Read balanced braces, return (contents without outer braces, chars_read)."""
        contents = ''
        depth = 1  # Already past opening brace
        chars_read = 0
        
        while idx < len(string) and depth > 0:
            char = string[idx]
            if char == '}':
                depth -= 1
            elif char == '{':
                depth += 1
            
            if depth > 0:  # Don't include final closing brace
                contents += char
            
            idx += 1
            chars_read += 1
        
        if depth != 0:
            logging.error('Unbalanced braces in marked string')
            sys.exit(1)
        
        return contents, chars_read
    
    unmarked_str = ''
    idx = 0
    MARKBOX = '\\markbox{'
    
    while idx < len(marked_string):
        if marked_string[idx:].startswith(MARKBOX):
            idx += len(MARKBOX)
            # Skip first arg
            _, chars_read = readBalancedBraces(idx, marked_string)
            idx += chars_read + 1  # +1 for opening brace of second arg
            # Keep second arg
            content, chars_read = readBalancedBraces(idx, marked_string)
            unmarked_str += content
            idx += chars_read
        else:
            unmarked_str += marked_string[idx]
            idx += 1
    
    return unmarked_str

def rectangleToLatex(pageno: int, in_rectangle: pymupdf.Rect, document_word_boxes: dict[int, dict[str, pymupdf.Rect]], marked_document: str) -> str | None:
    r"""
    Args:
        pageno: Zero-indexed page number
        in_rectangle: Rectangle on the page (pymupdf format)
        document_word_boxes: Dictionary from getWordBoxes()
        marked_document: Marked source LaTeX as a string

    Returns: The (unmarked) source latex which "contains" the rectangle.

    Given some rectangle, we find the closest word box before and after that rectangle
    then return all of the LaTeX between (and including) those two word boxes.

    If the inputted rectangle intersects at least one word box, finding the preceding and following word boxes is simple:
    out of the word boxes that intersect find the one with the smallest id and the one with the largest id, then just use the first
    existing id
    
    (because not all \markbox commands make it to the document_work_boxes dictionary) # actually, I insert all the markboxes regardless, they're in
    the source; it's just that some of them don't make it to document_word_boxes, but that doesn't matter---I only need the keys, not the boxes to
    extract the LaTeX.
    
    before the smallest and the next existing id
    after the largest.

    If the inputted rectangle doesn't intersect any document_word_boxes, then the "before" box is the one with the largest id whose baseline (y1) is less than
    (higher up the page) than the baseline of the inputted box, and the "after" box is the one with the smallest id whose baseline is greater than the inputted box.
    """

    page_word_boxes = document_word_boxes[pageno]
    intersecting_word_boxes = {k: rect for k, rect in page_word_boxes.items() if in_rectangle.intersects(rect)} 

    def getNumericComponent(k: str) -> int:
        return int(''.join(filter(str.isdigit, k)))

    def getPrevKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)        
        prev_keys = [k for k in all_keys if getNumericComponent(k) < target_num]
        return max(prev_keys, key = getNumericComponent) if prev_keys else None

    def getNextKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)
        next_keys = [k for k in all_keys if getNumericComponent(k) > target_num]
        return min(next_keys, key = getNumericComponent) if next_keys else None        

    all_keys = [k for page_boxes in document_word_boxes.values() for k in page_boxes.keys()]
    
    if intersecting_word_boxes:
        logging.debug(f"Rectangle {in_rectangle} on page {pageno} did intersect word boxes")
        min_key = min(intersecting_word_boxes.keys(), key = getNumericComponent)
        max_key = max(intersecting_word_boxes.keys(), key = getNumericComponent)
        before_key = getPrevKey(min_key, all_keys)
        after_key = getNextKey(max_key, all_keys)
    else:
        # the boxes before and after are on the same page
        logging.debug(f"No word box was intersected by rectangle {in_rectangle} on page {pageno}")
        boxes_before = {k: rect for k, rect in page_word_boxes.items() if rect.y0 < in_rectangle.y0}
        boxes_after = {k: rect for k, rect in page_word_boxes.items() if rect.y0 > in_rectangle.y0}
        before_key = max(boxes_before.keys(), key=getNumericComponent) if boxes_before else None
        after_key = min(boxes_after.keys(), key=getNumericComponent) if boxes_after else None

    if before_key is None:
        before_key = max(document_word_boxes[pageno-1].keys(), key=getNumericComponent) if pageno-1 in document_word_boxes else None

    if after_key is None:
        after_key = min(document_word_boxes[pageno+1].keys(), key=getNumericComponent) if pageno+1 in document_word_boxes else None

    if before_key is None or after_key is None:
        # This should only happen if the rectangle is before or after ALL marked boxes in the document.
        # This is a situation where we should check metadata, but I'll have to think more about that in general
        logging.warning(f"Cannot extract LaTeX: Rectangle outside marked boxes (before_key={before_key}, after_key={after_key})")
        return None

    logging.debug(f"Before key is {before_key} and after key is {after_key}")

    pattern = rf'(\\markbox\{{{before_key}\}}.*?\\markbox\{{{after_key}\}}.*?)(?:\\markbox|$)'
    m = re.search(pattern, marked_document, re.DOTALL)

    if m is None:
        logging.warning(rf"Cannot extract LaTeX: Regex search for LaTeX between \markbox macros with keys '{before_key}' and '{after_key}' failed")
        return None

    marked_latex = m.group(1)

    return unMark(marked_latex)

def segment(tex_filename: str):
    tex_filename = Path(tex_filename)
    tex_str = sourceAsString(tex_filename)

    # Setup parser context with recognized commands and environments
    latex_context = LatexContextDb()
    _macro_specs = [std_macro(csname, args_format) for csname, args_format in RECOGNIZED_CSNAMES.items()]
    latex_context.add_context_category('segmentspec', macros=_macro_specs)    

    # parse LaTeX file
    logging.info(f"Parsing {tex_filename}...")
    (nodelist, _, _) = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)
    
    if ''.join([node.latex_verbatim() for node in nodelist]) != tex_str:
        logging.error(f"Verbatim string tex source was not preserved after LatexWalker parsing; the parser has likely failed.")
        sys.exit(1)
           
    preamble_nodes, document_node = getPreambleAndDocument(nodelist)
    logging.info("Done.")

    # get metadata
    logging.info("Getting metadata...")
    enunciation_names, enunciation_source = getEnunciations(preamble_nodes)
    metadata, metadata_source, environments = getMetadataAndSelectEnvironments(preamble_nodes, document_node)

    # need to review what the eventual functions of each of these will be
    all_metadata = {'enunciation_names': enunciation_names,
                    'enunciation_source': enunciation_source,
                    'metadata': metadata,
                    'metadata_source': metadata_source,
                    'environments': environments}
    
    logging.info("Done.")

    # mark file
    boxpositions_filename = f'boxpositions_{tex_filename.stem}.txt'
    tex_write_commands = fr"""
\newwrite\markfile
\immediate\openout\markfile={boxpositions_filename}
"""
    markbox_def = r"""
\newcommand{\markbox}[2]{%
  \setbox0=\hbox{#2}%
  \immediate\write\markfile{#1:pwhd:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:spxy:\the\value{page}:\the\pdflastxpos:\number\dimexpr\pdfpageheight-\pdflastypos sp\relax:}%
  #2% 
  \pdfsavepos
  \write\markfile{#1:epxy:\the\value{page}:\the\pdflastxpos:\number\dimexpr\pdfpageheight-\pdflastypos sp\relax:}%
}

"""
    logging.info("Inserting marks...")

    left = r"[\t $(]"
    inside = r"[a-zA-Z0-9!?.,'`/;:\-()]+"
    right = r"[\t $)]"
    chars_node_match_regex = rf"(?<={left}){inside}(?={right})"    

    # old >>>
    # chars_node_match_regex = r"(?<=[\t $])[a-zA-Z0-9!?.,;:\-()]+(?=[\t $])"
    # <<<
    
    marked_document, num_marks = markNode(document_node, ALLOWED_MARK_ENVIRONMENTS.union(enunciation_names), chars_node_match_regex)
    logging.info("Done.")

    preamble_str = ''.join([node.latex_verbatim() for node in preamble_nodes])    
    
    marked_tex = preamble_str + tex_write_commands + markbox_def + marked_document

    # save at first the marked file to the same directory as the input tex_filename, then move it after pdflatex
    marked_filename = tex_filename.parent / f"{tex_filename.stem}_marked{tex_filename.suffix}"

    # write marked file 
    writeStringToFile(marked_tex, marked_filename)

    # run pdflatex
    process1 = runPDFlatex(tex_filename)
    process2 = runPDFlatex(marked_filename)

    # setup tmp directory and transfer files
    tmp_dir = Path('tmp_segmentsource')
    Path.mkdir(tmp_dir, exist_ok = True)

    transferTeXFiles(tex_filename, tmp_dir, 'cp')
    transferTeXFiles(marked_filename, tmp_dir, 'mv')
    
    # move boxpositions file
    os.system(f"mv {tex_filename.parent / boxpositions_filename} {tmp_dir}")

    def pdfFname(tex_fname: Path):
        return f"{tex_fname.stem}.pdf"
    
    process3 = runDiffpdf(pdfFname(tex_filename), pdfFname(marked_filename), tmp_dir)

    document_word_boxes = getWordBoxes(tmp_dir / boxpositions_filename, num_marks)

    # I should delete the tmp directory at this point I guess
    
    return num_marks, marked_tex, document_word_boxes, all_metadata

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python segmentsource.py',
                                     description = r'Segments source TeX by pages and metadata like \title, \author, \address, and abstract.')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    segment(filename)
