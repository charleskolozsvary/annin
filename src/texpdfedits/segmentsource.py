# DISCLAIMER: it's possible that it's much easier to track the box positions of words with lualatex
# than pdflatex with pylatexenc, but this appears to be working well enough right now

import argparse
import logging
import re

from pylatexenc.latexwalker import LatexWalker, LatexNode, LatexMacroNode, LatexEnvironmentNode, LatexGroupNode, LatexMathNode, LatexCharsNode, LatexCommentNode
from pylatexenc.macrospec import LatexContextDb, std_macro, std_environment, MacroSpec, ParsedMacroArgs

from itertools import count
from pathlib import Path

import sys
import os
import subprocess

from collections.abc import Callable

import pymupdf
import time


# TEST: ADD IGNORE PARSING >>>
class IgnoreRegionArgsParser:
    def parse_args(self, w, pos, parsing_state, **kwargs):
        r"""Skip until \endignorepylatexenc using get_token
        use in rare circumstances where the pylatexenc parser fails on something (typically in the preamble)
        just add
        \def\startignorepylatexenc{}
        \def\endignorepylatexenc{}

        and then
        \startignorepylatexenc
        ...
        \endignorepylatexenc

        around any problematic code before running segmentsource
        """
        current_pos = pos
        while True:
            try:
                # get_token returns (token_object, new_pos)
                tok = w.get_token(current_pos, parsing_state=parsing_state)
            except:
                raise ValueError("No matching \\endignorepylatexenc found")
            
            if tok.tok == 'macro' and tok.arg == 'endignorepylatexenc':
                end_pos = tok.pos + tok.len
                break
            
            current_pos = tok.pos + tok.len
        
        return (ParsedMacroArgs(argnlist=[]), end_pos, 0)
# <<<

RECOGNIZED_CSNAMES = {'emph': '{',
                      'textup': '{',
                      'textit': '{',
                      'textbf': '{',
                      'textsc': '{',
                      'texttt': '{',
                      'url': '{',
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
                      'dedication' : '{',
                      'title': '[{',
                      'author': '[{',
                      'address': '[{',
                      'curraddr' : '[{',
                      'email': '[{',
                      'keywords': '{',
                      'footnote': '[{', # \footnote[10]{text} sets the footnote to be footnote 10---only a number can be passed
                      'footnotemark': '[',
                      'footnotetext': '[{',
                      'caption': '[{',
                      'item': '[',
                      'renewcommand': '*{[{',
                      'newcommand': '*{[{',
                      'theoremstyle' : '{',
                      'bibitem': '[{',
                      'bib': '{{{',
                      'newtheorem': '*{[{[',
                      'newenvironment': '{[[{{',
                      'cite': '[{',
                      'label': '[{'}# greedily read all possible arguments to newtheorem, even if optional is not quite right, but that's okay

OPTIONAL_ARG = ('[', ']')

REQUIRED_ARG = ('{', '}')

# macros which themselves get marked like \markbox{<key>}{\macro{...}}
MARKED_CSNAMES = {'emph', 'textit', 'textbf', 'textsc', 'underline', 'texttt', 'textup', 'url'}
# any of these fail if they're arguments are abnormal, like a \[...\] in a \textit
# we should probably do some checking for something like that like
# "check nested nodes are valid. They're shouldn't be any display math nodes inside the argument to any of these commands...

# macros whose contents are marked
# MARKED_CONTENTS_MACROS = {'footnote', 'thanks', 'title', 'address', 'email', 'author', 'keywords'} # no, this was a bad idea without further thought

MARK_IDENTIFIERS = {'inline math': 'm'}

TRACKED_ENVIRONMENTS = {'abstract', 'figure', 'table', 'thebibliography', 'biblist'}

METADATA_CSNAMES = {'title', 'author', 'address', 'email', 'thanks', 'subjclass', 'keywords', 'datereceived', 'daterevised', 'commby'}

UNIQUE_FIELDS = {'title', 'subjclass', 'keywords', 'datereceived', 'commby', 'abstract'}

# better to leave out 'abstract' from the marked environments; some journals have the abstract at the end and our marks
# are expected to appear in order.
# this is why we extract the metadata and figures and tables separately, and we'll need to extract the footnotes separately, too
ALLOWED_MARK_ENVIRONMENTS = {'proof', 'enumerate', 'itemize', 'document', 'thebibliography', 'biblist', 'bibdiv', 'bibsec'}

DIFFPDF_DPI = 175

# now just setting the tolerance to 50_000. Unfortunately italic correction can be inserted *before* a markbox still, too.
# Take '(\emph{Boundary depletion})' (\markbox{}{\emph{Boundary depletion}}) will prevent space from being inserted after the
# first open parenthesis.
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 50_000

SCALED_POINTS_PER_TEX_POINT = 2 ** 16 # 65536

"""
there are 72.27 tex pts in an inch, while there are 
72 bp (what tex calls a big point) in an inch, which is what
pymupdf and other modern pdf systems use
"""
TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO = 72 / 72.27

"""
allow a few point discrepancy between x0 + width and x1
in boxinfoToPDFRectangle()
"""
WORD_BOX_WIDTH_TOLERANCE = 6

def sourceAsString(filename: Path) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def writeStringToFile(string: str, filename: Path):
    with open(filename, 'w', encoding = 'utf-8') as f:
        f.write(string)
    return 0

def joinNodesVerbatim(nodelist, start: int = 0, end: int | None = None) -> str:
    """return joined verbatim nodes from start to end inclusive"""
    if end is None:
        return ''.join([node.latex_verbatim() for node in nodelist[start:]])
    else:
        return ''.join([node.latex_verbatim() for node in nodelist[start:end+1]])

def getEnunciations(preamble_nodes) -> tuple[list[str], str]:
    enunciations = []
    for i, node in enumerate(preamble_nodes):
        if node.isNodeType(LatexMacroNode) and node.macroname == 'newtheorem':
            node_args = node.nodeargd.argnlist
            len_arg_spec = len(RECOGNIZED_CSNAMES[node.macroname])
            if len(node_args) == len_arg_spec and len_arg_spec > 1:
                arg_one = node_args[1]
                try:
                    # currently fails with \\newtheorem{%\nthm}{Theorem}, which I think is fine
                    enun_name = arg_one.nodelist[0].chars
                except Exception as e: 
                    logging.warning(
                        f"Attempting to extract second argument of '{node.latex_verbatim()}' "
                        f"raised {type(e).__name__}: {e}; "
                        f"node.nodeargs[1] was {arg_one}; ignoring"
                    )
                enunciations.append(
                    {'name': enun_name,
                     'start end': (node.pos, node.pos+node.len),
                     'verbatim': node.latex_verbatim()}
                )
            else:
                logging.warning(
                    f"Malformed {node.macroname}, '{node.latex_verbatim()}', "
                    f"did not match it's argument specification: {RECOGNIZED_CSNAMES[node.macroname]}"
                )
    if not enunciations:
        logging.warning("No enunciations (newtheorem commands) found; continuing without them.")
    return enunciations

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
    metadata_source = joinNodesVerbatim(preamble_nodes, start_idx, end_idx)

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

def markNode(start_node: LatexNode, allowed_environments: set[str], chars_node_match_regex: str, job_id: str) -> str:
    """Recursively mark the passsed start_node"""
    counter = count(0)
    def markStr(string: str, mark_identifier: str) -> str:
        return rf'\markbox{{{mark_identifier}{next(counter)}}}{{{string}}}'
        
    def recMark(node, parent_node, prev_node):
        node_verbatim = node.latex_verbatim()
        if node.isNodeType(LatexEnvironmentNode):
            verbatim_contents =  joinNodesVerbatim(node.nodelist) # every LatexEnvironmentNode has a nodelist
            joined_whole = rf'\begin{{{node.envname}}}{verbatim_contents}\end{{{node.envname}}}'
            # could maybe only do the following check if the environment is among allowed_environments
            # but it's safer to check every encountered environment
            if node_verbatim != joined_whole:
                logging.error(f"Environment node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                logging.debug(f"{verbatim_contents} != {joined_whole}")                
                sys.exit(1)
            
            if node.envname in allowed_environments:
                marked_contents = ''
                this_prev_node = None
                for nested_node in node.nodelist:
                    marked_contents += recMark(nested_node, node, this_prev_node)
                    this_prev_node = nested_node
                return rf'\begin{{{node.envname}}}{marked_contents}\end{{{node.envname}}}'
            else:
                return joined_whole
        elif node.isNodeType(LatexMacroNode):
            if node.macroname in MARKED_CSNAMES and prev_node is not None:
                prev_ends_italcorr = re.search(r'[(\[]\s*$', prev_node.latex_verbatim())
                if prev_ends_italcorr is None:
                    return markStr(node_verbatim, '')
                else:
                    return node_verbatim
            elif node.macroname == 'item':
                return node_verbatim
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
            pattern = chars_node_match_regex
            if prev_node is not None and (prev_node.isNodeType(LatexMacroNode) or prev_node.isNodeType(LatexGroupNode) or prev_node.isNodeType(LatexCommentNode)):
                    left = r"[\n\t $(~]"
                    inside = r"[a-zA-Z0-9!?.,'`/;:\-()]+"
                    right = r"[\n\t $)~]"
                    pattern = rf"(?<={left}){inside}(?:(?={right})|$)"
                    
            marked_str, num_subs = re.subn(pattern, lambda m: markStr(m.group(0), ''), node_verbatim)
            return marked_str
        elif node.isNodeType(LatexGroupNode):
            if prev_node is not None:
                prev_ends_square = re.search(r'[\]\}]\s*$', prev_node.latex_verbatim())
            
            if prev_node is not None and prev_node.isNodeType(LatexCharsNode) and prev_ends_square is None:
                # logging.debug(f"Prev node in marked group node: {prev_node.latex_verbatim()}")
                verbatim_contents =  joinNodesVerbatim(node.nodelist) # every LatexGroupNode has a nodelist
                # logging.debug(f"contents of marked group node: {verbatim_contents}\n")
                
                joined_whole = rf'{{{verbatim_contents}}}'
                if node_verbatim != joined_whole:
                    logging.error(f"Group node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                    logging.debug(f"{verbatim_contents} != {joined_whole}")                
                    sys.exit(1)

                marked_contents = ''
                this_prev_node = None
                for nested_node in node.nodelist:
                    marked_contents += recMark(nested_node, node, this_prev_node)
                    this_prev_node = nested_node
                return rf'{{{marked_contents}}}'
            else:
                return node_verbatim
        elif node.isNodeType(LatexCommentNode):
            return node_verbatim
        else:
            logging.warning(f"Unrecognized latex node '{node.nodeType()}' during markNode(); writing node.latex_verbatim(): '{node_verbatim}'")
            return node_verbatim
        
    return recMark(start_node, None, None), next(counter)

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
    post_document_nodes = nodelist[i+1:]

    return preamble_nodes, document_node, post_document_nodes

def texPointsToPDFpoints(tex_pts: float):
    return tex_pts * TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO

def scaledPointsToPDFpoints(sp: int):
    tex_pts = sp / SCALED_POINTS_PER_TEX_POINT
    return texPointsToPDFpoints(tex_pts)

def unzipHbox(hbox):
    return hbox[0], tuple(map(lambda pts: texPointsToPDFpoints(float(pts)), hbox[1:]))

def unzipPos(stend_xy):
    return stend_xy[0], tuple(map(lambda spts: scaledPointsToPDFpoints(int(spts)), stend_xy[1:-1]))

def boxinfoToPDFRectangle(key: str, hbox, start_xy):
    """No longer using the end position to avoid minor issues with italic correction.
    However, this also means that boxes which actually break across a line just extend into the margin, which is fine
    if the layout is not two-column.
    """
    pgA, (width, height, depth) = unzipHbox(hbox)
    pgB, (x0, sy) = unzipPos(start_xy)
    # pgC, (x1, ey) = unzipPos(end_xy)

    # if pgB != pgC:
    #     logging.debug(f"ignoring box '{key}': spanned multiple pages ({pgA} {pgB})")
    #     return None
    
    # if sy != ey:
    #     logging.debug(f"ignoring box '{key}': start and end y positions were not equal: '{sy} != {ey}'")
    #     return None
    
    # if abs(x0 + width - x1) > WORD_BOX_WIDTH_TOLERANCE:
    #     logging.debug(f"ignoring box '{key}': abs(x0 + width - x1) = {abs(x0 + width - x1)} > {WORD_BOX_WIDTH_TOLERANCE}")
    #     return None

    # lower y values are closer to the top of the page
    # return pageno, (x0, y0, x1, y1), where
    # (x0, y0) is the top left corner and
    # (x1, y1) is the bottom right corner of the rectangle
    return pgB, pymupdf.Rect(x0, sy - height, x0 + width, sy + depth)
        
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

    if not all(map(lambda x: len(x) == 2, word_boxes.values())):
        # all marks should have exactly two fields, the hbox dimensions and the start xy
        logging.error(f"Box information in '{boxpositions_filename}' differed from specification")
        sys.exit(1)

    num_used_boxes = 0

    document_word_boxes = dict()
    for key, info in word_boxes.items():
        res = boxinfoToPDFRectangle(key, info['pwhd'], info['spxy'])
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

def readBalancedBraces(idx: int, s: str) -> tuple[str, int]:
    """Read unescaped balanced braces, return (contents without outer braces, chars_read)."""
    depth = 1  # Already past opening brace
    start_idx = idx
        
    while idx < len(s) and depth > 0:
        if s[idx] == '\\' and idx + 1 < len(s):
            idx += 2
        else:
            if s[idx] == '}':
                depth -= 1
            elif s[idx] == '{':
                depth += 1
            idx += 1
            
    if depth != 0:
        logging.error('Unbalanced braces in marked string')
        sys.exit(1)
    
    # Extract contents between start and the closing brace
    contents = s[start_idx:idx-1]
    return contents, idx - start_idx

def unMarkWithPositions(marked_string: str, job_id: str) -> tuple[str, dict[str, tuple[int, int]]]:
    r"""Remove \markbox commands and track positions of marked content.
    
    Returns:
        (unmarked_string, mark_positions) where mark_positions maps mark_id -> (start, end)
        Positions are in the unmarked string, with end being exclusive.
    """
    # remove the '{}\segmentgobble{<job_id>}\leavevmode ' from marked_string first
    marked_string, num_subs = re.subn(rf'\{{\}}\\segmentgobble\{{{job_id}\}}\\leavevmode ', '', marked_string)
    logging.debug(rf"Removed {num_subs} '{{}}\segmentgobble{{{job_id}}}\leavevmode 's")

    unmarked_str = ''
    mark_positions = {}
    current_pos = 0  # Position in unmarked string
    idx = 0
    MARKBOX = '\\markbox{'
    MARKBOX_LEN = len(MARKBOX)

    unmarked_parts = []
    
    while idx < len(marked_string):
        if marked_string[idx:idx+MARKBOX_LEN] == MARKBOX:
            idx += len(MARKBOX)
            # Read first arg (mark_id)
            mark_id, chars_read = readBalancedBraces(idx, marked_string)
            idx += chars_read + 1  # +1 for opening brace of second arg
            # Read second arg (content)
            content, chars_read = readBalancedBraces(idx, marked_string)
            
            # Track position in unmarked string
            start_pos = current_pos
            end_pos = current_pos + len(content)
            mark_positions[mark_id] = (start_pos, end_pos)
            
            # Add content to unmarked string
            unmarked_parts.append(content)
            current_pos += len(content)
            idx += chars_read
        else:
            unmarked_parts.append(marked_string[idx])
            current_pos += 1
            idx += 1
    
    return ''.join(unmarked_parts), mark_positions

def validateMarkPositions(mark_positions: dict[str, tuple[int, int]], document_word_boxes: dict[int, dict[str, pymupdf.Rect]]) -> None:
    """Verify that no mark positions overlap and that the mark position keys are a superset of the document word box keys. Raises ValueError if they do.
    Also verify that document_word_boxes.keys() is a subset of in mark_positions.keys()
    Args:
        mark_positions: dict mapping mark_id -> (start, end) positions
    Raises:
        ValueError: if any two marks overlap
    """
    # Sort by start position
    sorted_marks = sorted(mark_positions.items(), key=lambda x: x[1][0])

    def numericComponent(k: str) -> int:
        return int(''.join(filter(str.isdigit, k)))
    
    # Check each adjacent pair
    for i in range(len(sorted_marks) - 1):
        id_i, (start_i, end_i) = sorted_marks[i]
        id_j, (start_j, end_j) = sorted_marks[i + 1]

        if numericComponent(id_i) >= numericComponent(id_j):
            raise ValueError(
                f"mark ids '{id_i}' and '{id_j}' are not in source string position order: "
                f"mark id '{start_i}' has start pos '{start_i}' and mark id '{id_j}' has start pos '{start_j}'"
            )
        
        # Validity check for current mark
        if start_i >= end_i:
            raise ValueError(
                f"Invalid mark position for '{id_i}': "
                f"start ({start_i}) >= end ({end_i})"
            )
        
        # Since sorted by start, only need to check if previous end > next start
        if start_j < end_i:
            raise ValueError(
                f"Mark positions overlap: "
                f"mark '{id_i}' at [{start_i}, {end_i}) overlaps with "
                f"mark '{id_j}' at [{start_j}, {end_j})"
            )
    
    # Check last mark validity
    if sorted_marks:
        id_last, (start_last, end_last) = sorted_marks[-1]
        if start_last >= end_last:
            raise ValueError(
                f"Invalid mark position for '{id_last}': "
                f"start ({start_last}) >= end ({end_last})"
            )

    # check that mark_positions.keys() is a superset of all document_word_boxes mark_ids
    for page_boxes in document_word_boxes.values():
        for mark_id in page_boxes.keys():
            if mark_id not in mark_positions:
                raise ValueError(
                    f"mark_id '{mark_id}' not in mark_positions. "
                    "mark_positions.keys() is not a superset of all mark_ids in document_word_boxes."
                )

    logging.info("All mark positions are valid.")

def segment(tex_filename: str, extra_marked_environment_names: set[str] = set()):
    tex_filename = Path(tex_filename)
    tex_str = sourceAsString(tex_filename)

    # Setup parser context with recognized commands and environments
    latex_context = LatexContextDb()
    _macro_specs = [std_macro(csname, args_format) for csname, args_format in RECOGNIZED_CSNAMES.items()]
    latex_context.add_context_category('segmentspec', macros=_macro_specs)

    # TEST: ADD IGNORE PARSING >>>
    custom_macros = [MacroSpec('startignorepylatexenc', args_parser=IgnoreRegionArgsParser())]
    latex_context.add_context_category(
        'ignore-regions',
        macros=custom_macros,
        prepend=True
    )
    # <<<
    
    # parse LaTeX file
    logging.info(f"Parsing {tex_filename}...")
    (nodelist, _, _) = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)

    if joinNodesVerbatim(nodelist) != tex_str:
        logging.error(f"Verbatim string tex source was not preserved after LatexWalker parsing; the parser has likely failed.")
        sys.exit(1)
           
    preamble_nodes, document_node, post_document_nodes = getPreambleAndDocument(nodelist)
    logging.info("Done.")

    # get metadata
    logging.info("Getting metadata...")
    enunciations = getEnunciations(preamble_nodes)
    enunciation_names = set([enun['name'] for enun in enunciations])
    
    metadata, metadata_source, environments = getMetadataAndSelectEnvironments(preamble_nodes, document_node)

    # need to review what the eventual functions of each of these will be
    all_metadata = {'enunciation_names': enunciation_names,
                    'enunciation_source': '',
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
    markbox_defs = r"""
\newcommand{\markbox}[2]{%
  \leavevmode%
  \setbox0=\hbox{#2}%
  \immediate\write\markfile{#1:pwhd:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:spxy:\the\value{page}:\the\pdflastxpos:\number\dimexpr\pdfpageheight-\pdflastypos sp\relax:}%
  #2% 
%% \pdfsavepos
%% \write\markfile{#1:epxy:\the\value{page}:\the\pdflastxpos:\number\dimexpr\pdfpageheight-\pdflastypos sp\relax:}%
}

\newcommand{\segmentgobble}[1]{}

"""
    job_id = f'segment{int(time.time())}'
    
    logging.info("Inserting marks...")

    left = r"[\n\t $(~]"
    inside = r"[a-zA-Z0-9!?.,'`/;:\-()]+"
    right = r"[\n\t $)~]"
    chars_node_match_regex = rf"(?:(?<={left})|^){inside}(?:(?={right})|$)"
    
    marked_document, num_marks = markNode(
        document_node,
        ALLOWED_MARK_ENVIRONMENTS.union(enunciation_names).union(extra_marked_environment_names),
        chars_node_match_regex,
        job_id
    ) # job_id will probably be deprecated
    logging.info("Done.")

    preamble_str = joinNodesVerbatim(preamble_nodes)
    post_document_str = joinNodesVerbatim(post_document_nodes)
    
    marked_tex = preamble_str + tex_write_commands + markbox_defs + marked_document + post_document_str

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

    logging.info("Getting word boxes...")
    document_word_boxes = getWordBoxes(tmp_dir / boxpositions_filename, num_marks)
    logging.info("Done.")    

    # I should eventually delete the tmp directory at this point

    # do not concatenate the inserted preamble definitions
    logging.info("Unmarking LaTeX...")    
    unmarked_str, mark_positions = unMarkWithPositions(preamble_str + marked_document + post_document_str, job_id)
    logging.info("Done.")

    if unmarked_str != tex_str:
        logging.error("Unmarked LaTeX does NOT match original LaTeX!")
        sys.exit(1)

    logging.info("Validating mark positions...")
    validateMarkPositions(mark_positions, document_word_boxes)
    logging.info("Done.")    

    # segment should output all the information necessary for rectangleToLatex in prompt.py
    
    return num_marks, marked_tex, unmarked_str, mark_positions, document_word_boxes, all_metadata

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
