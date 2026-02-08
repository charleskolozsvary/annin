import logging
import argparse
import pymupdf
import json
import time
import pickle
import re
import os, sys

from texpdfedits.extract import getEdits
from texpdfedits.segmentsource import segment, sourceAsString, runDiffpdf, pdfFname, compileLatex, transferTeXFiles
from texpdfedits.makeCorrections import Correction, getCorrections

from pathlib import Path

INTERMEDIATE_EXTENSIONS_TO_DELETE = ".aux .out .log .toc .bbl .blg .thm .toc".split(' ')

def commentSource(tex_str: str, char_positions: list[int], charpos_to_correction: dict[int, list[tuple[str, Correction]]]) -> str:
    """
    Add the corrections to the original source as comments.

    Args:
    tex_str: original LaTeX source as string
    char_positions: sorted character positions of the starts and ends of the LaTeX snippets for each correction.
            important: the positions are simply sorted from smallest to largest, and a position can correspond to a start or end of a snippet
            and it's possible to that snippets can overlap.
    charpos_to_correction: dictionary where keys are members of char_positions and values are lists of string--Correction pairs where the string is
    either 'start' or 'end' and the correction is the corresponding correction object for the position. A list is returned for each key incase
    there are two start/end character positions which are the same. The positions of a non-overlapping correction will return a singleton list.

    In the event that two corrections END at the same position, I'll just write

    %% END OF CORRECTIONS corr_idx1, corr_idx2, ...
    
    If two corrections START at the same position, I'll write

    %% Correction: corr_idx
    %% Type: <type>
    %% PDF selected text:
    %% Comment: (mabye should be 'Instruction:'; see asComment())

    for each correction in order and then
    %% START OF CORRECTIONS corr_idx1, corr_idx2, ...

    Finally, if a start and end are at the same position then I'll write the correction info then say

    %% START of correction ... and END of correction ...
    """
    
    inserted_comments = [] #list of tuples where tuple index 0 is the char_pos and tuple index 1 is the inserted material
    for char_pos in char_positions:
        kinds_and_corrs = charpos_to_correction[char_pos]
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
                assert False, f"A position should only be a start or end. Invalid kind of position '{kind}'."
                
        def writeCallout(corr_idxs: list[int], start_or_end: str):
            sing_plural = 'correction' if len(corr_idxs) == 1 else 'corrections'
            return f'{start_or_end.upper()} of {sing_plural} ' + ', '.join([str(idx) for idx in corr_idxs])
        
        start_end_callout = []
        if start_corr_idxs:
            start_end_callout.append(writeCallout(start_corr_idxs, 'start'))
        if start_corr_idxs and end_corr_idxs:
            start_end_callout.append(' AND ')
        if end_corr_idxs:
            start_end_callout.append(writeCallout(end_corr_idxs, 'end'))

        description_str = ''.join(corr_descriptions)
        callout_str = ''.join(start_end_callout)

        inserted_comments.append((char_pos, f'%%\n{description_str}%% {callout_str}\n')) # orig

    len_tex_str = len(tex_str)
    commented_source = []
    prev_pos = 0
    for (char_pos, inserted_comment) in inserted_comments:
        commented_source.append(tex_str[prev_pos:char_pos])

        curr_char, char_idx = tex_str[char_pos], char_pos
        rest_of_line = [] # rest of line or until non-horizontal space
        while not re.match(r'[\r\n\S]', curr_char):
            if char_idx >= len_tex_str:
                logging.error("Ran out of file while looking for rest_of_line; aborting...")
                sys.exit(1)
            rest_of_line.append(curr_char)
            char_idx += 1
            curr_char = tex_str[char_idx]
        rest_of_line.append(curr_char)
        rest_of_line = ''.join(rest_of_line)

        logging.debug(f"{' '.join(inserted_comment[0:30].split()):30s}  rest_of_line: {repr(rest_of_line)}")

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

    commented_source.append(tex_str[prev_pos:]) # add what remains of the tex file

    return ''.join(commented_source)

def deleteIntermediateLaTeX(tex_filename: Path):
    body = tex_filename.stem
    for extension in INTERMEDIATE_EXTENSIONS_TO_DELETE:
        to_delete = Path(body + extension)
        if to_delete.exists():
            os.system(f"rm {to_delete}")

def addCorrectionComments(*args, **kwargs) -> int:
    """
    *args are the annotated pdf file name followed by the LaTeX file name
    **kwargs are key word arguments (currently just corrections and group_overlapping)
    """
    annot_filename, tex_filename = args
    
    corrections = kwargs.get('corrections', None)
    group_overlapping = kwargs.get('group_overlapping', True)
    del_intermediate = kwargs.get('del_intermediate', True)
    compiler = kwargs.get('compiler', 'pdflatex')

    if corrections is None or not group_overlapping:
        corrections = getCorrections(*args, group_overlapping=group_overlapping)

    tex_filename = Path(tex_filename)
    commented_tex_filename = Path(f"{tex_filename.parent / tex_filename.stem}_commentcorrs.tex")

    char_positions = []
    charpos_to_correction = dict()
    for corr in corrections:
        (start_pos, end_pos) = corr.snippet_source_positions
        if start_pos in charpos_to_correction:
            charpos_to_correction[start_pos].append(('start', corr))
        else:
            charpos_to_correction[start_pos] = [('start', corr)]
        if end_pos in charpos_to_correction:
            charpos_to_correction[end_pos].append(('end', corr))
        else:
            charpos_to_correction[end_pos] = [('end', corr)]
        char_positions.extend([start_pos, end_pos])

    char_positions = sorted(set(char_positions))

    tex_str = sourceAsString(tex_filename)
    
    commented_source = commentSource(tex_str, char_positions, charpos_to_correction)

    with open(commented_tex_filename, 'w') as f:
        f.write(commented_source)

    cwd = Path('./')        

    # Verify that inserting the comments does not change the PDF
    process1 = compileLatex(tex_filename, compiler=compiler)
    process2 = compileLatex(commented_tex_filename, compiler=compiler)

    transferTeXFiles(tex_filename, cwd, 'cp')
    transferTeXFiles(commented_tex_filename, cwd, 'mv')    
    
    process3 = runDiffpdf(pdfFname(tex_filename), pdfFname(commented_tex_filename), cwd, per_page_tol=0)

    if del_intermediate:
        deleteIntermediateLaTeX(tex_filename)
        deleteIntermediateLaTeX(commented_tex_filename)

    logging.info(f"Original and commented source produce identical PDFs.")
    logging.info(f"Correction comments successfully written to {commented_tex_filename.name}.")

    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annotated_PDF_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-p", "--load-pickle", action="store_true", help='load pickle file of corrections if available')
    parser.add_argument("--grp-overlap", action=argparse.BooleanOptionalAction, help='Extend overlapping correction source positions; default=True', default=True)
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, help='Delete intermediate LaTeX files; default=True', default=True)
    parser.add_argument("--compiler", type=str, help='Specify LaTeX compiler; default=pdflatex', default='pdflatex')    
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    tmp_pickle_dir = Path("tmp_pickle")

    Path.mkdir(tmp_pickle_dir, exist_ok = True)
    corr_file = tmp_pickle_dir / Path(f"{Path(args.latex_filename).stem}_corrections.pkl")
    tmp_prompt_dir = corr_file.parent

    if not (corr_file.exists() and args.load_pickle):
        corrections = getCorrections(args.annotated_PDF_filename, args.latex_filename, group_overlapping = args.grp_overlap)
        with open(corr_file, 'wb') as f:
            pickle.dump(corrections, f)
    else:
        with open(corr_file, 'rb') as f:
            corrections = pickle.load(f)

    addCorrectionComments(
        args.annotated_PDF_filename,
        args.latex_filename,
        corrections = corrections,
        group_overlapping = args.grp_overlap,
        del_intermediate = args.clean,
        compiler=args.compiler
    )

    
