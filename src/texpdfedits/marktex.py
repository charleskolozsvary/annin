r"""
This module marks the source with
\markbox commands which record box and pdf positioning information which is used to take any (it is hoped) rectangle
produce corresponding source which rendered the text which intersects said rectangle.

The function rectangleToLatex is implemented in corr.py where the correction objects are created
"""

import argparse
import logging
logger = logging.getLogger(__name__)

import re

from pylatexenc.latexwalker import LatexWalker, LatexNode, LatexMacroNode, LatexEnvironmentNode, LatexGroupNode, LatexMathNode, LatexCharsNode, LatexCommentNode
from pylatexenc.macrospec import LatexContextDb, std_macro, std_environment, MacroSpec, ParsedMacroArgs, EnvironmentSpec

from itertools import count
from pathlib import Path

import sys
import os
import subprocess

import pymupdf
import time

class IgnoreRegionArgsParser:
    def parse_args(self, w, pos, parsing_state, **kwargs):
        r"""
        Skip until \endignorepylatexenc using get_token
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

COMPILER_INFO = {
    'pdflatex': (2, 'latin-1', ['--interaction=nonstopmode']),
    'prdlatex': (1, 'latin-1', ['-pdf', '-nonstopmode']),
    'xelatex': (2, 'utf-8', ['--interaction=nonstopmode'])
}

CSNAMES_ARGSPEC = {
    'emph': '{',
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
    'dedicatory' : '{',
    'title': '[{',
    'author': '[{',
    'address': '[{',
    'curraddr' : '[{',
    'urladdr' : '[{',
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
    'label': '[{',
    'copyrightinfo': '{{',
    'translator': '{',
    'vspace': '*{',
    'hspace': '*{',
    'documentclass': '[{',
}

ENVNAMES_ARGSPEC = {
    'enumerate': '[',
    'itemize': '[',
    'description': '[',
}

# macros which get marked as \markbox{<key>}{\macro{...}}, like in-line math
# TODO: can I mark the words in these macros? 
MARKED_ENTIRE_CSNAMES = {
    'emph',
    'textit',
    'textbf',
    'textsc',
    'underline',
    'texttt',
    'textup',
    'url',
}
# any of the above fail if their arguments are abnormal, like a \[...\] in a \textit

# Below are macros whose contents ARE marked, not just the entire macro like the ones above
DISTINCTLY_MARKED_MACROS = {
    'caption': 1,
    'footnote': 1,
    'footnotetext': 1,
    'title': 1,
    'address': 1,
    'curraddr': 1,
    'urladdr': 1,
    'email': 1,
    'thanks': 0,
    'keywords': 0,
    'subjclass': 1,
    'dedicatory': 0,
    'translator': 0,
    'commby': 0,
    'copyrightinfo': 1,
    'bib': 2,
}

# environments which get their own nested numbering
DISTINCTLY_MARKED_ENVIRONMENTS = {'document', 'abstract'}

# Following are only used in getMetadataAndSelectEnvironments(), which is currently unused >>>
TRACKED_ENVIRONMENTS = {'abstract', 'figure', 'table', 'thebibliography', 'biblist', 'bibsection'}

METADATA_CSNAMES = {'title', 'author', 'address', 'curraddr', 'urladdr', 'email', 'thanks',
                    'subjclass', 'keywords', 'datereceived', 'daterevised', 'commby',
                    'translator', 'dedicatory', 'copyrightinfo'}

UNIQUE_FIELDS = {'title', 'subjclass', 'keywords', 'datereceived', 'commby', 'abstract', 'translator', 'dedicatory', 'copyrightinfo'}
# <<<

# the environments whose latex character nodes can be marked
ALLOWED_MARK_ENVIRONMENTS = {
    'document',
    'abstract',
    'proof',
    'enumerate',
    'itemize',
    'description',
    'thebibliography',
    'biblist',
    'bibdiv',
    'bibsection',
    'appendix',
}

# amsrefs bib keys whose values cannot be marked
FORBIDDEN_BIB_KEYS = [
    'author',
    'language',
    'label',
    'date',
    'year',
    'url',
    'arXiv',
    'eprint',
]

# environments which are not marked in full like allowed_mark_environments---here
# only the contents of the \caption macros in said environments can be marked
ONLY_MARK_CAPTION_ENVS = {
    'table',
    'table*',
    'figure',
    'figure*',
    'longtable',
    'longtable*',
    'subfigure',
    'subfigure*'
}

DIFF_PDF_DPI = 175

r"""
The tolerance of 50_000 pixels is a heuristic picked by trial and error.
Unfortunately, italic correction can still be inserted *before* a markbox, too, which will introduce some pixel differences.
Example: '(\emph{Boundary depletion})' (\markbox{}{\emph{Boundary depletion}}) will prevent space from being inserted after the
first open parenthesis if the entire string is in italic font.
"""
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 50_000


"""
There are 72.27 TeX points in an inch, while there are 
72 PDF points (what TeX calls a big point or "bp") in an inch, which is what
pymupdf and other modern pdf systems use, so we need that conversion ratio
"""
TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO = 72 / 72.27

# PdfTeX outputs the PDF positions in scaled points, so this constant is useful
SCALED_POINTS_PER_TEX_POINT = 2 ** 16 # 65536

def sourceAsString(filename: Path) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def writeStringToFile(string: str, filename: Path) -> int:
    with open(filename, 'w', encoding = 'utf-8') as f:
        f.write(string)
    return 0

def joinNodesVerbatim(nodelist: list[LatexNode], start: int = 0, end: int | None = None) -> str:
    """return joined verbatim nodes from start to end inclusive"""
    if end is None:
        return ''.join([node.latex_verbatim() for node in nodelist[start:]])
    else:
        return ''.join([node.latex_verbatim() for node in nodelist[start:end+1]])

def getEnunciations(preamble_nodes) -> tuple[list[str], str]:
    r"""
    Retrieve \newtheorem declarations so we can expand ALLOWED_MARK_ENVIRONMENTS to include
    those enunciations, too.
    """
    enunciations = []
    for i, node in enumerate(preamble_nodes):
        if node.isNodeType(LatexMacroNode) and node.macroname == 'newtheorem':
            node_args = node.nodeargd.argnlist
            len_arg_spec = len(CSNAMES_ARGSPEC[node.macroname])
            if len(node_args) == len_arg_spec and len_arg_spec > 1:
                arg_one = node_args[1]
                try:
                    # this fails with \\newtheorem{%\nthm}{Theorem}, but that's okay
                    enun_name = arg_one.nodelist[0].chars
                except Exception as e: 
                    logger.warning(
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
                logger.warning(
                    f"Malformed {node.macroname}, '{node.latex_verbatim()}', "
                    f"did not match it's argument specification: {CSNAMES_ARGSPEC[node.macroname]}"
                )
    if not enunciations:
        logger.warning("No enunciations (newtheorem commands) found; continuing without them.")
        
    return enunciations

def getEnvironmentSources(node, recognized_environments, environments):
    """
    Only used by getMetadataAndSelectEnvironments, which is currently unused
    
    recognized environments as a dictionary with keys as the environment names
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
    """Currently unused"""
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
                logger.warning(f"Found more than one instance of unique field '{csname}', overwriting earlier instance.")
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
        logger.warning("No abstract found in getMetadataAndSelectEnvironments()")
    elif num_abstract > 1:
        logger.warninig(f"! Found {num_abstract} abstracts; there should only be one")

    return metadata, metadata_source, environments

def compileLatex(tex_filename: Path, compiler: str = 'pdflatex') -> subprocess.CompletedProcess:
    """Compile .tex file with provided compiler"""
    result = None
    tex_filename_dir = tex_filename.parent
    
    (num_runs, encoding, compile_options) = COMPILER_INFO.get(compiler, (2, 'latin-1', ['--interaction=nonstopmode']))
    command = [compiler, *compile_options, tex_filename.name]    
    for i in range(num_runs):
        logger.info(f"Running {compiler} on {tex_filename} (pass {i+1}/{num_runs})...")
        logger.debug(f"I.e., {' '.join(command)}")        
        result = subprocess.run(
            command,
            cwd=tex_filename_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding=encoding
        )
        
        if result.returncode != 0:
            logger.error(
                f"{compiler} failed on pass {i+1} of {tex_filename.name}: {result.stderr}."
                f"Output: {result.stdout}"
            )
            sys.exit(1)
        
    return result

def transferTeXFiles(tex_filename: Path, files_to: Path, move_or_copy: str):
    logger.debug(f"the tex_filename is {tex_filename}\nfiles_to is {files_to}")    
    if tex_filename.parent == files_to:
        logger.debug("No need to transfer files; they are already in the cwd")
        return
    # glob used to be f'**/{tex_filename.stem}.*', but I actually only want the top-level files in the parent dir        
    tex_dot_star_files = [x for x in tex_filename.parent.glob(f'{tex_filename.stem}.*')]
    for x in tex_dot_star_files:
        logger.debug(f"x is {x}")
        match move_or_copy:
            case 'mv':
                x.move_into(files_to)
            case 'cp':
                x.copy_into(files_to)
            case _:
                logger.critical(f"Could not transfer TeX files: unrecognized action '{move_or_copy}'; exiting")
                sys.exit(1)

def removeDir(directory: Path):
    if not directory.exists():
        return
    files_in_dir = [f for f in directory.glob('**/*') if f.is_file()]
    if not files_in_dir:
        directory.rmdir()
        return
    for f in files_in_dir:
        f.unlink()
    directory.rmdir()

def runDiffpdf(first_fname: str, second_fname: str, output_dir: Path, per_page_tol: int = DIFFPDF_PER_PAGE_PIXEL_TOLERANCE) -> subprocess.CompletedProcess:
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = ['diff-pdf',
                          f'--per-page-pixel-tolerance={per_page_tol}',
                          f'--dpi={DIFF_PDF_DPI}',
                          '--skip-identical',
                          '--grayscale',
                          '--mark-differences',
                          '--verbose',
                          f'--output-diff={diff_fname}',
                          first_fname,
                          second_fname]
    
    logger.info(f"Running `{' '.join(subprocess_command)}`...")
    result = subprocess.run(
        subprocess_command,
        cwd=output_dir
    )
    
    if result.returncode != 0:
        logger.error(f"{first_fname} and {second_fname} are not identical. See {Path(output_dir) / diff_fname}")        
        sys.exit(1)
        
    return result, Path(diff_fname)

def markNodes(
        to_mark_nodelist: list[LatexNode],
        allowed_environments: set[str],
        chars_node_match_regex: str,
        job_id: str
) -> tuple[str, dict[str, dict[str, int]]]:
    """Recursively mark the passsed node list. Return the marked string and the mark counters"""
    counters = {}

    # macro names where are acceptable to match the beggining of the string when marking a chars node after it
    OTHER_PREV_MACRO_NODE_EXCEPTIONS = {' ', 'item'} # control space or item
    
    def markStr(string: str, parent_counter_keys: list[str]) -> str:
        """
        A mark like document0:15;footnote0:3 corresponds to the fourth markbox in the first footnote which appears after
        the 16th markbox in the first (and only) document environment. So all numbers are zero indexed. The number after the colon
        corresponds to some box counter, and the number before the colon corresponds to the environment/macro counter

        So the general structure is <environment/macro><num>:<num>;<nested enuncation/macro>:<num>;<and so on>

        More than two levels of nesting should be very rare, but I use this format to handle arbitrary nesting

        parent_counter_keys are the names of environments/macros the current mark is to be written in.
        increment_head tells me whether I need to increment the head counter to the currently deepest nested object
        
        The very first time a particular dedicated macro/env is encountered (to mark in), increment_head should not be True, 
        the counter key is automatically initialized (and so there's no head value to reset)
        """
        if not parent_counter_keys:
            logger.critical(f"Could not mark {string}: it is not within any recognized macro/environment; exiting")
            sys.exit(1)
            
        for parent in parent_counter_keys:
            if parent not in counters:
                counters[parent] = {'head': 0, 'value': -1}

        count_key = parent_counter_keys[-1]
        counters[count_key]['value'] += 1
        mark_id = ','.join([
            f"{key.upper()}{counters[key]['head']};{counters[key]['value']}" for key in parent_counter_keys
        ])
        
        return rf'\markbox{{{mark_id}}}{{{string}}}'
        
    def recMark(node, parent_node, prev_node, parent_counter_keys):
        
        node_verbatim = node.latex_verbatim()
        
        # before the subsequent if ... elif block was inside "if parent_counter_keys:"
        # not sure why.... Tentatively removing that check---as it was,
        # the numbering for boxes inside dedicated macros in the preamble were incorrect
        if node.isNodeType(LatexEnvironmentNode):
            node_name = node.envname
            if node_name in DISTINCTLY_MARKED_ENVIRONMENTS and node_name in counters:
                counters[node_name]['head'] += 1
                counters[node_name]['value'] = -1                    
        elif node.isNodeType(LatexMacroNode):
            node_name = node.macroname
            if node_name in DISTINCTLY_MARKED_MACROS and node_name in counters:
                counters[node_name]['head'] += 1
                counters[node_name]['value'] = -1

        parent_is_distinctly_marked_macro = parent_node is not None and parent_node.isNodeType(LatexMacroNode) and parent_node.macroname in DISTINCTLY_MARKED_MACROS
        is_in_only_mark_caption_env = parent_node is not None and parent_node.isNodeType(LatexEnvironmentNode) and parent_node.envname in ONLY_MARK_CAPTION_ENVS
        in_preamble = 'document' not in parent_counter_keys
        in_bib = parent_counter_keys and 'bib' in parent_counter_keys
        
        if isinstance(node, LatexEnvironmentNode):
            env_args = node.nodeargd.argnlist
            logger.debug(f"env_arg = {env_args}")
            verbatim_args = joinNodesVerbatim(env_args) if env_args != [None] else ''

            # every LatexEnvironmentNode has a nodelist            
            verbatim_contents =  joinNodesVerbatim(node.nodelist) 
            joined_whole = rf'\begin{{{node.envname}}}{verbatim_args}{verbatim_contents}\end{{{node.envname}}}'
            
            if node_verbatim != joined_whole:
                logger.error(f"Environment node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                logger.debug(f"{node_verbatim} != {joined_whole}")
                sys.exit(1)
                
            if node.envname in allowed_environments or node.envname in ONLY_MARK_CAPTION_ENVS:
                marked_contents = []
                is_distinct_mark_env = node.envname in DISTINCTLY_MARKED_ENVIRONMENTS
                
                # add parent counter key
                if is_distinct_mark_env:
                    parent_counter_keys.append(node.envname)

                this_prev_node = None
                for nested_node in node.nodelist:
                    marked_contents.append(recMark(nested_node, node, this_prev_node, parent_counter_keys))
                    this_prev_node = nested_node
                    
                # remove parent counter key
                if is_distinct_mark_env:
                    parent_counter_keys.pop()
                    
                return rf"\begin{{{node.envname}}}{verbatim_args}{''.join(marked_contents)}\end{{{node.envname}}}"
            else:
                return joined_whole
            
        elif isinstance(node, LatexMacroNode):
            if node.macroname in MARKED_ENTIRE_CSNAMES and (prev_node is not None) and (not is_in_only_mark_caption_env) and not in_preamble:
                prev_ends_italcorr = re.search(r'[(\[]\s*$', prev_node.latex_verbatim())
                if prev_ends_italcorr is None:
                    return markStr(node_verbatim, parent_counter_keys)
                else:
                    return node_verbatim
            elif node.macroname in DISTINCTLY_MARKED_MACROS:
                if is_in_only_mark_caption_env and node.macroname != 'caption':
                    return node_verbatim

                # do arg processing >>>
                len_arg_spec = len(CSNAMES_ARGSPEC[node.macroname])
                argnlist = node.nodeargd.argnlist
                joined_verbatim_macro = rf"\{node.macroname}" + ''.join([n.latex_verbatim() if n is not None else '' for n in argnlist])
                
                if node_verbatim != joined_verbatim_macro:
                    logger.warning(
                        f"{node.macroname} verbatim, \n```latex\n{node_verbatim}\n```\ndid not match joined verbatim\n"
                        f"```latex\n{joined_verbatim_macro}\n```\nignoring..."
                    )
                    return node_verbatim
                elif len(argnlist) != len_arg_spec:
                    logger.warning(
                        f"{node.macroname}, {node_verbatim}, did not match argspec len: "
                        f"{len(argnlist)} != {len_arg_spec}"
                    )
                    return node_verbatim
                
                parent_counter_keys.append(node.macroname)                
                marked_macro = [rf"\{node.macroname}"]
                this_prev_node = None
                for idx, arg_node in enumerate(argnlist):
                    if arg_node is None:
                        this_prev_node = arg_node
                        continue
                    if idx == DISTINCTLY_MARKED_MACROS[node.macroname]:
                        marked_macro.append(recMark(arg_node, node, this_prev_node, parent_counter_keys))
                    else:
                        marked_macro.append(arg_node.latex_verbatim())
                    this_prev_node = arg_node
                    
                parent_counter_keys.pop()
                
                # logger.debug(''.join(marked_macro))
                # logger.debug("END\n\n")
                
                return ''.join(marked_macro)
                # <<<
            else:
                return node_verbatim

        # this recMark implementation is getting unweildy....
        elif in_preamble and not parent_counter_keys:
            return node_verbatim
        
        elif isinstance(node, LatexMathNode):
            if node.displaytype == 'inline' and not is_in_only_mark_caption_env:
                return markStr(node_verbatim, parent_counter_keys)
            else:
                return node_verbatim
            
        elif isinstance(node, LatexCharsNode):
            if is_in_only_mark_caption_env:
                return node_verbatim

            # don't mark key=chars in bib third argument contents
            if in_bib and '=' in node_verbatim:
                return node_verbatim
            
            # mark every span in safe envs
            pattern = chars_node_match_regex
            if prev_node is not None and (prev_node.isNodeType(LatexMacroNode) or prev_node.isNodeType(LatexGroupNode) or prev_node.isNodeType(LatexCommentNode)):
                if parent_is_distinctly_marked_macro:
                    pass
                elif prev_node.isNodeType(LatexMacroNode) and prev_node.macroname in OTHER_PREV_MACRO_NODE_EXCEPTIONS: 
                    pass
                else:
                    left = r"[\n\t $(~]"
                    inside = r"[a-zA-Z0-9!?.,'`/;:\-()]+"
                    right = r"[\n\t $)~]"
                    pattern = rf"(?<={left}){inside}(?:(?={right})|$)"
            marked_str, num_subs = re.subn(pattern, lambda m: markStr(m.group(0), parent_counter_keys), node_verbatim)
            return marked_str
        
        elif isinstance(node, LatexGroupNode):
            if is_in_only_mark_caption_env:
                return node_verbatim
            
            if prev_node is not None:
                prev_ends_square = re.search(r'[\]\}]\s*$', prev_node.latex_verbatim())
                
                prev_includes_forbidden_mark_bib_keys = re.search('|'.join(FORBIDDEN_BIB_KEYS), prev_node.latex_verbatim(), re.IGNORECASE)
                
                if in_bib and prev_includes_forbidden_mark_bib_keys is not None:
                    return node_verbatim
            
            if (prev_node is not None and prev_node.isNodeType(LatexCharsNode) and prev_ends_square is None) or parent_is_distinctly_marked_macro:
                # logger.debug(f"Prev node in marked group node: {prev_node.latex_verbatim()}")
                verbatim_contents = joinNodesVerbatim(node.nodelist) # every LatexGroupNode has a nodelist
                # logger.debug(f"contents of marked group node: {verbatim_contents}\n")
                
                joined_whole = rf'{{{verbatim_contents}}}'
                if node_verbatim != joined_whole:
                    logger.error(f"Group node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                    logger.debug(f"{verbatim_contents} != {joined_whole}")                
                    sys.exit(1)

                marked_contents = []
                this_prev_node = None
                for nested_node in node.nodelist:
                    marked_contents.append(recMark(nested_node, node, this_prev_node, parent_counter_keys))
                    this_prev_node = nested_node
                return "{" + ''.join(marked_contents) + "}"
            else:
                return node_verbatim
            
        elif isinstance(node, LatexCommentNode):
            return node_verbatim
        
        else:
            logger.warning(
                f"Unrecognized latex node '{node.nodeType()}' during markNode(); "
                f"writing node.latex_verbatim(): '{node_verbatim}'"
            )
            return node_verbatim

    manuscript_marked_contents = []
    outer_prev_node = None
    for start_node in to_mark_nodelist:
        manuscript_marked_contents.append(recMark(start_node, None, outer_prev_node, []))
        outer_prev_node = start_node
    return ''.join(manuscript_marked_contents), counters

def getPreambleAndDocument(nodelist):
    """ Needs review """
    """Read in a list of pylatexenc.latexwalker.<Node>s and return the nodes which belong to the
       preamble and document"""        
    num_document_envs = len(list(filter(lambda n: n.isNodeType(LatexEnvironmentNode) and n.envname == 'document', nodelist)))
    if num_document_envs != 1:
        logger.critical(r"Found more (or less) than one `\begin{document}`s during getPreambleAndDocument().")
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
    However, this means that boxes which break across a line just extend into the margin, which is only 
    a relatively minor inconvenience if the layout is not two-column.
    """
    pgA, (width, height, depth) = unzipHbox(hbox)
    pgB, (x0, sy) = unzipPos(start_xy)
    
    return pgB, pymupdf.Rect(x0, sy - height, x0 + width, sy + depth)
        
def getWordBoxes(boxpositions_filename: Path):
    word_boxes = dict()
    not_colon = r'([^:]*)'

    with open(boxpositions_filename, 'r') as f:
        line = f.readline().strip()
        line_no = 1
        while line:
            box_info = re.match(fr"^{not_colon}:(pwhd|spxy):(\d+):{not_colon}:{not_colon}:{not_colon}$", line)
            if box_info is None:
                logger.critical(f"Line {line_no} of {boxpositions_filename} '{repr(line)}' did not match the info spec")
                sys.exit(1)
            matches = box_info.groups()
            key, label, values = matches[0], matches[1], tuple(map(lambda m: m.strip('pt'), matches[2:]))
            
            if key in word_boxes:
                if label in word_boxes[key] and word_boxes[key][label] != values:
                    # if the title hbox or position appears more than once with new values from being rewritten
                    # in the running head, we just ignore said the new values                    
                    if 'TITLE' in key:
                        line = f.readline().strip()
                        line_no += 1
                        continue
                    # for some reason, when using the prdlatex format (even with texlive2024), caption boxes will appear twice (or perhaps more times)
                    # with different box information, but it looks like the second appearance is correct. This is probably fragile.
                    if 'CAPTION' in key:
                        word_boxes[key][label] = values
                        line = f.readline().strip()
                        line_no += 1
                        continue                    
                    
                    # There should be only two labels (and they should each appear at most once):
                    # it looks like captions are read in twice, so it's okay if a label for a key appears more than once if the values are the same
                    # 'pwhd' for page, width, height, depth; and 'spxy' for start, page, x pos, y pos
                    logger.critical(
                        f"Key '{key}' with label '{label}' was already in '{word_boxes[key]}' and values differed\n"
                        f"current value:\n```python\n{word_boxes[key][label]}\n```\n"
                        f"new value:\n```python\n{values}\n```"
                    )
                    sys.exit(1)
                            
                word_boxes[key][label] = values
            else:
                word_boxes[key] = {label:values}
                
            line = f.readline().strip()
            line_no += 1

    markids_to_delete = set()
    
    for key, info in word_boxes.items():
        if 'spxy' not in info:
            logger.warning(
                f"Could not extract individual box information: "
                f"box with mark id '{key}' is not written to the PDF"
            )
            markids_to_delete.add(key)
            continue            
        if len(info) != 2:
            # all marks should have exactly two fields (except for the ones which don't make it to the page)
            # the hbox dimensions and the start page and xy positions
            logger.error(f"mark id '{key}' in '{boxpositions_filename}' differed from specification")
            sys.exit(1)

    for mark_id in markids_to_delete:
        del word_boxes[mark_id]

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

    logger.info(f"Created {len(word_boxes)} marked boxes.")
    
    return document_word_boxes, markids_to_delete

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
        logger.error('Unbalanced braces in marked string')
        sys.exit(1)
    
    # Extract contents between start and the closing brace
    contents = s[start_idx:idx-1]
    return contents, idx - start_idx

def unMarkWithPositions(marked_string: str, job_id: str, markids_to_delete: set[str]) -> tuple[str, dict[str, tuple[int, int]]]:
    r"""Remove \markbox commands and track positions of marked content.
    
    Returns:
        (unmarked_string, mark_positions) where mark_positions maps mark_id -> (start, end)
        Positions are in the unmarked string, with end being exclusive.
    """
    
    mark_positions = {}
    current_pos = 0  # Position in unmarked string
    idx = 0
    MARKBOX = '\\markbox{'
    MARKBOX_LEN = len(MARKBOX)

    unmarked_parts = []
    
    while idx < len(marked_string):
        if marked_string[idx:idx+MARKBOX_LEN] == MARKBOX:
            idx += len(MARKBOX)
          
            mark_id, chars_read = readBalancedBraces(idx, marked_string)
            idx += chars_read + 1  # +1 for opening brace of second arg
          
            content, chars_read = readBalancedBraces(idx, marked_string)
            
            # Track position in unmarked string
            start_pos = current_pos
            end_pos = current_pos + len(content)
            
            if mark_id not in markids_to_delete:
                mark_positions[mark_id] = (start_pos, end_pos)
            
            unmarked_parts.append(content)
            current_pos += len(content)
            idx += chars_read
        else:
            unmarked_parts.append(marked_string[idx])
            current_pos += 1
            idx += 1
    
    return ''.join(unmarked_parts), mark_positions

# >>>
def numericComponent(s: str) -> int:
    return int(''.join(filter(str.isnumeric, s)))

def alphaComponent(s: str) -> str:
    return ''.join(filter(str.isalpha, s))

def markIdToCountInfo(mark_id: str) -> list[dict[str, int]]:
    counts = mark_id.split(',')
    count_info = []
    for count in counts:
        head_and_stem = count.split(';')
        if len(head_and_stem) != 2:
            raise ValueError(f"A segment of a nested mark, {piece}, was not delimited into two by a semicolon")
        count_name = alphaComponent(head_and_stem[0])
        head_count = numericComponent(head_and_stem[0])
        stem_count = int(head_and_stem[1])
        count_info.append({'name': count_name, 'head': head_count, 'stem': stem_count})
    return count_info

def compareNestedMarkIDs(count_info_1: list[dict[str, int]], count_info_2: list[dict[str, int]]):
    """ Needs review """
    """ return -1 if id_1 < id_2, 0 if they are equal, 1 if id_1 > id_2
        only compares marks that are both within document
    Not sure what the real point of writing this is... This effectively just recovers the
    order the marks are inserted (but more weakly), which is what I already get from mark_positions
    """
    if not (count_info_1[0]['name'] == 'document' and count_info_2[0]['name'] == 'document'):
        raise ValueError(f"Given IDs '{id_1}' and '{id_2}' are not nested within the document")
    
    for idx in range(min(len(count_info_1), len(count_info_2))):
        counter_1 = count_info_1[idx]
        counter_2 = count_info_2[idx]
        if counter_1['name'] != counter_2['name']:
            raise ValueError(
                f"Cannot compare counters '{count_info_1}' and '{count_info_2}': "
                "counter names don't match up"
            )
        
        if counter_1['head'] < counter_2['head']:
            return -1
        elif counter_1['head'] > counter_2['head']:
            return 1

        if counter_1['stem'] < counter_2['stem']:
            return -1
        elif counter_1['stem'] > counter_2['stem']:
            return 1

    if len(count_info_1) < len(count_info_2):
        return -1
    elif len(count_info_1) > len(count_info_2):
        return 1
    else:
        return 0
# <<<

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

    for mark_id in mark_positions:
        count_info = markIdToCountInfo(mark_id)
        if count_info[0]['name'] == 'document' and count_info[0]['head'] != 0:
            raise ValueError(f"Unexpected mark ID '{mark_id}': document head is greater than 0")
    
    # Check each adjacent pair
    for i in range(len(sorted_marks) - 1):
        id_i, (start_i, end_i) = sorted_marks[i]
        id_j, (start_j, end_j) = sorted_marks[i + 1]
        
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

    logger.info("All mark positions are valid.")
    
def pdfFname(tex_fname: Path):
    return f"{tex_fname.stem}.pdf"

def splitPreambleNodes(preamble_nodes: list[LatexNode]):
    for i, node in enumerate(preamble_nodes):
        if isinstance(node, LatexMacroNode) and node.macroname == 'documentclass':
            return preamble_nodes[:i+1], preamble_nodes[i+1:]
    logger.critical("\\documentclass command not found")
    sys.exit(1)
    
def segment(tex_filename: str, **kwargs):
    extra_marked_environment_names = kwargs.get('emen', set()) # set[str]
    clean                          = kwargs.get('clean', True) # delete temporary directory
    compiler                       = kwargs.get('compiler', 'pdflatex')
    if compiler is None:
        compiler = 'pdflatex'
    
    tex_filename = Path(tex_filename)
    tex_str = sourceAsString(tex_filename)

    # Set up parser context with recognized commands and environments
    latex_context = LatexContextDb()
    macro_specs = [std_macro(csname, args_format) for csname, args_format in CSNAMES_ARGSPEC.items()]
    environment_specs = [std_environment(envname, args_format) for envname, args_format in ENVNAMES_ARGSPEC.items()]
    
    latex_context.add_context_category('markspec', macros=macro_specs, environments=environment_specs)

    # Add Ignore Parsing
    custom_macros = [MacroSpec('startignorepylatexenc', args_parser=IgnoreRegionArgsParser())]
    latex_context.add_context_category('ignore-regions', macros=custom_macros, prepend=True)
    
    # Parse LaTeX --> get LaTeX node list 
    logger.info(f"Parsing {tex_filename}...")
    (nodelist, _, _) = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)

    if joinNodesVerbatim(nodelist) != tex_str:
        logger.critical(f"TeX source was not preserved after LatexWalker parsing")
        sys.exit(1)
           
    preamble_nodes, document_node, post_document_nodes = getPreambleAndDocument(nodelist)
    logger.info("Done.")

    # Track \newtheorems
    enunciations = getEnunciations(preamble_nodes)
    enunciation_names = set([enun['name'] for enun in enunciations])

    # Mark file
    boxpositions_filename = f'boxpositions_{tex_filename.stem}.txt'
    tex_write_commands = fr"""
\makeatletter      %% for some reason \leavevmode's expansion of \unhbox\voidb@x is sometimes not read with @ as a letter, resulting in the error
\let\voidb\voidb@x %% `undefined control sequence \voidb<linebreak>@x`. Should probably be looked into.
\makeatother

\newwrite\markfile
\immediate\openout\markfile={boxpositions_filename}
"""
    markbox_def = r"""
\newcommand{\markbox}[2]{%
  \ifvmode\leavevmode\fi%% to get the correct pdfposition, I must leave vmode when marking. Otherwise the position recorded is before the new paragraph
  \setbox0=\hbox{#2}%
  \immediate\write\markfile{#1:pwhd:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:spxy:\the\value{page}:\the\pdflastxpos:\number\dimexpr\pdfpageheight-\pdflastypos sp\relax:}%
  #2% 
}

"""
    job_id = f'segment{int(time.time())}'
    
    logger.info("Inserting marks...")

    left = r"[\n\t $(~]"
    inside = r"[a-zA-Z0-9!?.,'`/;:\-()@]+"
    right = r"[\n\t $)~]"
    chars_node_match_regex = rf"(?:(?<={left})|^){inside}(?:(?={right})|$)"

    all_allowed_mark_environments = ALLOWED_MARK_ENVIRONMENTS.union(enunciation_names).union(extra_marked_environment_names)

    docclass_nodes, preamble_nodes = splitPreambleNodes(preamble_nodes)    

    # job_id may be eventually removed; currently unused    
    marked_preamble, counters = markNodes(
        preamble_nodes,
        all_allowed_mark_environments,
        chars_node_match_regex,
        job_id
    )

    # logger.debug(f"marked preamble:\n{marked_preamble}\n\nEND\n")
        
    marked_document, counters = markNodes(
        [document_node],
        all_allowed_mark_environments,
        chars_node_match_regex,
        job_id
    )
    
    logger.info("Done.")

    post_document_str = joinNodesVerbatim(post_document_nodes)

    docclass_str = joinNodesVerbatim(docclass_nodes)

    # Concatenate marked file out of components
    marked_tex = docclass_str + tex_write_commands + markbox_def + marked_preamble + marked_document + post_document_str

    # Save at first the marked file to the same directory as the input tex_filename, then move it after pdflatex
    marked_filename = tex_filename.parent / f"{tex_filename.stem}_marked{tex_filename.suffix}"

    # Write marked file 
    writeStringToFile(marked_tex, marked_filename)

    # Compile original and marked LaTeX
    process1 = compileLatex(tex_filename, compiler = compiler)
    process2 = compileLatex(marked_filename, compiler = compiler)

    # Set up tmp directory and transfer files
    tmp_dir = Path('tmp_marktex')
    Path.mkdir(tmp_dir, exist_ok = True)

    transferTeXFiles(tex_filename, tmp_dir, 'cp')
    transferTeXFiles(marked_filename, tmp_dir, 'mv')
    
    # Move boxpositions file
    new_boxpositions_fname = (tex_filename.parent/boxpositions_filename).move_into(tmp_dir)

    # Compare original and marked PDFs
    process3, _ = runDiffpdf(pdfFname(tex_filename), pdfFname(marked_filename), tmp_dir)

    logger.info(f"Original and marked sources produce identical PDFs.")

    logger.info("Getting word boxes...")
    document_word_boxes, markids_to_delete = getWordBoxes(tmp_dir / boxpositions_filename)
    logger.info("Done.")    

    # Do not concatenate the inserted preamble definitions
    logger.info("Unmarking LaTeX...")
    unmarked_str, mark_positions = unMarkWithPositions(docclass_str + marked_preamble + marked_document + post_document_str, job_id, markids_to_delete)
    logger.info("Done.")

    if unmarked_str != tex_str:
        logger.critical("Unmarked LaTeX does NOT match original LaTeX!")
        sys.exit(1)

    validateMarkPositions(mark_positions, document_word_boxes)

    if clean:
        removeDir(tmp_dir)

    # Segment should output all the information necessary for rectangleToLatex in makeCorrections.py
    return mark_positions, document_word_boxes

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog = 'python segmentsource.py',
        description = r'Marks small units in source LaTeX to extract source with positional information (i.e., rectangles)'
    )
    
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument(
        "-c",
        "--clean",
        action=argparse.BooleanOptionalAction,
        help='Delete intermediate files (and temporary directories); default=True',
        default=True
    )
    parser.add_argument("--compiler", type=str, help='Specify LaTeX compiler; default=pdflatex', default='pdflatex')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    mark_positions, document_word_boxes = segment(filename, clean=args.clean, compiler=args.compiler)
