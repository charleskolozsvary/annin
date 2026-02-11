import logging
logger = logging.getLogger(__name__)
import argparse
import pymupdf
import json
import time
import pickle
import re
import sys

from texpdfedits.extract_anns import Edit, getEdits
from texpdfedits.mark_tex import segment, sourceAsString, runDiffpdf, pdfFname, compileLatex, transferTeXFiles, removeDir
from texpdfedits.corr import Correction, getCorrections, toCodeblock

from pathlib import Path

INTERMEDIATE_EXTENSIONS_TO_DELETE = set(".aux .out .log .toc .bbl .blg .thm .synctex.gz .synctex .brf .pdf".split(' '))

def getBetweenLatex(prev_pos: int, char_pos: int, prev_rest_of_line: str, *args):
    (tex_str, charpos_to_kinds_and_corrections, corrected_snippets) = args
    
    between_source_tex = tex_str[prev_pos:char_pos]

    kinds_and_corrs = charpos_to_kinds_and_corrections[char_pos]
    kinds, corrs = zip(*kinds_and_corrs)
    num_ends = kinds.count('end')

    if num_ends == 0:
        return between_source_tex

    # filter out start corrections in the rare case a char_pos is both the start and end of corrections
    kinds, corrs = zip(*[kandc for kandc in kinds_and_corrs if kandc[0] == 'end'])
        
    if not all(k == 'end' for k in kinds) or len(kinds) != num_ends:
        logger.error("Did not succesfully filter out corrections that start at this char_pos")
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
            logger.error(
                "Could not get between latex: "
                "Corrections sharing end positions were not all part of the same group"
            )
            sys.exit(1)    
        if len(set(corrected_snippets[g_key] for g_key in group)) != 1:
            for corrected_snip in [corrected_snippets[g_key] for g_key in group]:
                logger.error(toCodeblock(corrected_snip))
                    
            logger.error(f"Corrections in overlapping group {group} did not have identical corrected snippets")
            sys.exit(1)
        corrected_snip = corrected_snippets[group[0]]
        
    elif len(corrs) == 1:
        # standalone processing
        corrected_snip = corrected_snippets[corrs[0].index]
        group = [corrs[0].index]

    # either none of the snippets in the group were corrected or the standalone snippet wasn't corrected        
    if corrected_snip is None:
        return between_source_tex

    if not re.match(r'^\S$', prev_rest_of_line):
        logger.warning(
            "prev_rest_of_line was not single nonwhitespace as expected; "
            f"correction(s) {group} were not automatically completed (original source used)"
        )
        return between_source_tex

    # The beginning of the corrected_snippets appear to never have any leading white space since
    # they all begin at a markbox command which will always be at a nonwhitespace character,
    # so we're always in the `if re.match(r'\S$', last_char):` case in commentSource
    # and the while not re.match(r'[\r\n\S]' ... ) does not run at all so prev_pos = char_idx = char_pos
    return corrected_snip 

def commentSource(tex_str: str, char_positions: list[int], charpos_to_kinds_and_corrections: dict[int, list[tuple[str, Correction]]], **kwargs) -> str:
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
    
    inserted_comments = [] #list of tuples where tuple[0] is the char_pos and tuple[1] is the inserted material
    for char_pos in char_positions:
        kinds_and_corrs = charpos_to_kinds_and_corrections[char_pos]
        corr_descriptions = []
        start_corr_idxs, end_corr_idxs = [], []
        for kind_and_corr in kinds_and_corrs:
            (kind, corr) = kind_and_corr
            if kind == 'start':
                corr_descriptions.append(corr.asComment())
                start_corr_idxs.append(corr.index)
            elif kind == 'end':
                end_corr_idxs.append(corr.index)
            else:
                assert False, f"Invalid kind of position '{kind}'."
                
        def writeCallout(corr_idxs: list[int], start_or_end: str):
            sing_plural = 'correction' if len(corr_idxs) == 1 else 'corrections'
            return f'{start_or_end.upper()} of {sing_plural} ' + ', '.join([str(idx) for idx in corr_idxs])
        
        start_end_callout = []
        if start_corr_idxs:
            start_end_callout.append(writeCallout(start_corr_idxs, 'start'))
        if start_corr_idxs and end_corr_idxs:
            start_end_callout.append(' *AND* ')
        if end_corr_idxs:
            start_end_callout.append(writeCallout(end_corr_idxs, 'end'))

        description_str = ''.join(corr_descriptions)
        callout_str = ''.join(start_end_callout)

        inserted_comments.append((char_pos, f'%%\n{description_str}%% {callout_str}\n')) # orig

    len_tex_str = len(tex_str)
    commented_source = []
    prev_pos, prev_rest_of_line = 0, ''
    for (char_pos, inserted_comment) in inserted_comments:
        ## >>>
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
        ## <<<
        
        commented_source.append(between_latex)

        curr_char, char_idx = tex_str[char_pos], char_pos
        rest_of_line = [] # rest of line from char_pos or until non-horizontal space
        while not re.match(r'[\r\n\S]', curr_char):
            if char_idx >= len_tex_str:
                logger.critical("Ran out of file while looking for rest_of_line; aborting...")
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

def deleteIntermediateLaTeX(tex_filename: Path):
    body = tex_filename.stem
    for extension in INTERMEDIATE_EXTENSIONS_TO_DELETE:
        to_delete = Path(body + extension)
        if to_delete.exists():
            logger.debug(f"Deleted {to_delete}")
            to_delete.unlink()

def tagsAreValid(tagged_text: str) -> bool:
    tag_regex = r'(</?)([a-zA-Z]+)>'
    all_tags = list(re.finditer(tag_regex, tagged_text))
    if not all_tags:
        logger.warning("string passed for tag validation contained no tags")
        return True
    
    tag_info = [(tag.group(1), tag.group(2)) for tag in all_tags]
    tag_starts, tag_names = zip(*tag_info)

    if tag_names.count(Edit.CARET_NAME) > 1:
        return False

    if len(set(tag_names)) != 1:
        return False

    prev_start, prev_name = '', ''
    for (tag_start, tag_name) in tag_info:
        if prev_start == '' and tag_start != '<':
            return False
        if prev_start == '<' and not (tag_start == '</' and tag_name == prev_name):
            return False
        if prev_start == '</' and tag_start != '<':
            return False
        prev_start = tag_start
        prev_name = tag_name
        
    return True

def correctSnippet(corr: Correction, **kwargs):
    if corr.type not in {'Caret', 'Replace', 'Remove'}:
        return None
    
    pdf_selection_text = corr.pdf_selected_text
    if not tagsAreValid(pdf_selection_text):
        return None

    comment_text = corr.messages['comment']

    # expect empty comment with remove annotation
    if corr.type == 'Remove' and comment_text != '':
        return None

    # insertion or replacement text very likely not exact/literal
    if re.search(r'pls\s*link|<\s*link\s*>|comp', comment_text, re.IGNORECASE):
        return None

    tag_name = corr.type if corr.type != 'Caret' else Edit.CARET_NAME

    # TODO: other enhancements/character substitutions like getting a correction
    # Annotated text: "stands for “closed<Replace>”,</Replace> as opposed" to work
    # Check (home)/notes/enhancements.md for more examples

    # TODO: improve this surrounding character check: try to get 0 or more words (up to some maximum).

    nonwhite_left = r'(\S+)?(\s*)'
    nonwhite_right = r'(\s*)(\S+)?'
    if corr.type == 'Caret':
        regex = rf'{nonwhite_left}<{tag_name}>(){nonwhite_right}'
    else:
        regex = rf'{nonwhite_left}<{tag_name}>(.*?)</{tag_name}>{nonwhite_right}'

    tagged_and_surr_text = list(re.finditer(regex, pdf_selection_text, re.DOTALL))
    
    if len(tagged_and_surr_text) != 1:
        return None

    match = tagged_and_surr_text[0]
    left, leftsp, tagged, rightsp, right = [re.escape(m) if m is not None else '' for m in [match.group(i) for i in range(1,6)]]

    # logger.debug(f"Correction {corr.index}:\n{repr(left)}\n{repr(tagged)}\n{repr(right)}")

    l_sp = r'\s+?' if leftsp else ''
    r_sp = r'\s+?' if rightsp else ''
    
    m_left, m_right = rf'({left}{l_sp})({tagged})', rf'({tagged})({r_sp}{right})'

    existing_snippet = kwargs.get('snippet', None)
    latex_snippet = corr.latex_snippet if existing_snippet is None else existing_snippet

    def doSubstitution(sub_left, sub_right):
        cs_left,  ns_left  = re.subn(m_left, sub_left, latex_snippet)
        cs_right, ns_right = re.subn(m_right, sub_right, latex_snippet)
        
        logger.debug(
            f"for Correction {corr.index}\ncs_left  is {repr(cs_left)}\ncs_right is "
            f"{repr(cs_right)}\nns_left  is {ns_left}\nns_right is {ns_right}"
        )
        
        if ns_left == 1 and ns_right == 1:
            return cs_left if cs_left == cs_right else None # could return either; arbitrarily return left sub
        elif ns_left == 1:
            return cs_left
        elif ns_right == 1:
            return cs_right
        else:
            return None

    match corr.type:
        case 'Caret' | 'Replace':
            sub_left = lambda m: m.group(1) + comment_text
            sub_right = lambda m: comment_text + m.group(2)
        case 'Remove':
            sub_left = r'\1'
            sub_right = r'\2'
        case _:
            return None

    return doSubstitution(sub_left, sub_right)

def getCorrectedSnippets(corrections: list[Correction], overlapping_keys: list[list[int]]) -> dict[int, str]:
    """ Carry out simple (strikeout, replace, or caret) corrections to the LaTeX source string
    Return corrected_snippets: dictionary of correction keys (correction indicies) -> corrected latex snippets (strings)

    Note: overlapping corrections must be grouped
    """
    key_to_correction = {corr.index: corr for corr in corrections}
    standalone_keys = [corridx for corridx in key_to_correction if corridx not in {idx for group in overlapping_keys for idx in group}]

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
            corrected_snip = correctSnippet(corr, snippet=existing_snippet)
            if corrected_snip is None:
                continue
            corrected_snippets[g_key] = corrected_snip
            corr.is_autocorrected = True
            
            # update all of the corrected snippets in the group
            for g_key in group:
                corrected_snippets[g_key] = corrected_snip
            existing_snippet = corrected_snip               
    
    return corrected_snippets

def addCorrectionComments(*args, **kwargs) -> int:
    """
    *args are the annotated pdf file name followed by the LaTeX file name
    **kwargs are key word arguments (currently just corrections and group_overlapping)
    """
    annot_filename, tex_filename = args
    
    corrections         = kwargs.get('corrections', None)
    overlapping_keys    = kwargs.get('overlapping_keys', None)
    
    group_overlapping   = kwargs.get('group_overlapping', True)
    compiler            = kwargs.get('compiler', 'pdflatex')
    
    clean               = kwargs.get('clean', True)    
    validate            = kwargs.get('validate', True)
    do_autocorrections  = kwargs.get('autocorrect', False)

    if corrections is None and overlapping_keys is None:
        corrections, overlapping_keys = getCorrections(
            *args,
            group_overlapping = group_overlapping,
            compiler          = compiler,            
            clean             = clean
        )

    tex_filename = Path(tex_filename)
    commented_tex_filename = Path(f"{tex_filename.parent / tex_filename.stem}_commentcorrs.tex")

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
    tex_str = sourceAsString(tex_filename)
    
    # comment the source -- no autocorrections    
    commented_source = commentSource(
        tex_str,
        char_positions,
        charpos_to_kinds_and_corrections
    )

    with open(commented_tex_filename, 'w') as f:
        f.write(commented_source)

    cwd = Path('./')

    # Verify that inserting the comments does not change the PDF
    process1 = compileLatex(tex_filename, compiler=compiler)
    process2 = compileLatex(commented_tex_filename, compiler=compiler)

    transferTeXFiles(tex_filename, cwd, 'cp')
    transferTeXFiles(commented_tex_filename, cwd, 'mv')
    
    if validate:
        process3, diff_fname = runDiffpdf(pdfFname(tex_filename), pdfFname(commented_tex_filename), cwd, per_page_tol=0)

    if clean:
        logger.info("Deleting intermediate files...")
        diff_fname.unlink()
        deleteIntermediateLaTeX(tex_filename)
        deleteIntermediateLaTeX(commented_tex_filename)
        logger.info("Done...")

    logger.info(f"Original and commented source produce identical PDFs.")
    logger.info(f"Correction comments successfully written to {commented_tex_filename.name}.")

    if not do_autocorrections:
        return 0

    # comment the source again---now with autocorrections if specified    
    logger.info(f"Carrying out simple corrections...")
    corrected_snippets = getCorrectedSnippets(corrections, overlapping_keys)

    commented_source = commentSource(
        tex_str,
        char_positions,
        charpos_to_kinds_and_corrections,
        corrected_snippets = corrected_snippets
    )
    
    # no validation because we expect pdf differences after autocorrections
    autocorrected_tex_filename = Path(f"{tex_filename.stem}_autocorrected.tex")    
    with open(autocorrected_tex_filename, 'w') as f:
        f.write(commented_source)
    logger.info("Done.")

    n_corrected = sum(1 for corr in corrections if corr.is_autocorrected)

    logger.info(f"Autocorrected {n_corrected:3d}/{len(corrections):3d} corrections")
    logger.info(f"Autocorrected source successfully written to {autocorrected_tex_filename}.")

    return 0

if __name__ == '__main__':
    clparser = argparse.ArgumentParser()
    clparser.add_argument('annotated_PDF_filename')
    clparser.add_argument('latex_filename')
    
    clparser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    clparser.add_argument("-p", "--load-pickle", action="store_true", help='Load (or create) pickle file of corrections (for debugging)')
    
    clparser.add_argument("--grp-overlap", action=argparse.BooleanOptionalAction, help='Extend overlapping correction source positions; default=True', default=True)
    clparser.add_argument("--compiler", type=str, help='Specify TeX compiler; default=pdflatex', default='pdflatex')
    clparser.add_argument("--clean", action=argparse.BooleanOptionalAction, help='Delete intermediate LaTeX files and tmp dirs; default=True', default=True)    
    clparser.add_argument("--autocorrect", action="store_true", help='Automatically carry out simple corrections; default=False')
    
    args = clparser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(encoding='utf-8', level=_level) # format='%(asctime)s - %(levelname)s - %(message)s'

    if not args.grp_overlap and args.autocorrect:
        logger.critical("Overlapping snippets must be extended to do autocorrections. Please either allow overlap grouping or do not request autocorrections.")
        sys.exit(1)

    if args.load_pickle:
        pickle_dir = Path("pickle")
        Path.mkdir(pickle_dir, exist_ok = True)
        pcorr_file = pickle_dir / Path(f"{Path(args.latex_filename).stem}_corrections.pkl")
    
        if pcorr_file.exists():
            with open(pcorr_file, 'rb') as f:
                (corrections, overlapping_keys) = pickle.load(f)
        else:
            corrections, overlapping_keys = getCorrections(
                args.annotated_PDF_filename,
                args.latex_filename,
                group_overlapping = args.grp_overlap,
                compiler          = args.compiler,
                clean             = args.clean
            )
            with open(pcorr_file, 'wb') as f:
                pickle.dump((corrections, overlapping_keys), f)
    else:
        corrections, overlapping_keys = None, None

    addCorrectionComments(
        args.annotated_PDF_filename,
        args.latex_filename,
        group_overlapping = args.grp_overlap,
        compiler          = args.compiler,        
        clean             = args.clean,
        corrections       = corrections,
        overlapping_keys  = overlapping_keys,        
        autocorrect       = args.autocorrect
    )

    
