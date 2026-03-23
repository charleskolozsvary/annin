import logging
logger = logging.getLogger(__name__)
import argparse
import re
import sys
from pathlib import Path

import texpdfedits.extractanns as extractanns
import texpdfedits.modifytex as modifytex
import texpdfedits.corr as corr
import texpdfedits.utils as utils
import texpdfedits.cformats as cformats

from importlib.metadata import version
__version__ = version('texpdfedits')

EDITED_SUFFIX = 'inlined'
AUTO_SUFFIX = 'autocorrected'

def process_files(*args, **kwargs) -> int:
    annot_filename, tex_filename = args
    
    compiler            = kwargs.get('compiler', 'pdflatex')
    clean               = kwargs.get('clean', True)    
    validate            = kwargs.get('validate', True)
    do_autocorrections  = kwargs.get('autocorrect', False)

    corrections, overlapping_keys = corr.getCorrections(
        *args,
        **kwargs,
    )
    
    (char_positions, charpos_to_kinds_and_corrections) = modifytex.getSourcePosToCorrections(corrections)

    tex_filename = Path(tex_filename)
    tex_str = utils.sourceAsString(tex_filename)
    
    commented_tex_filename = Path(f"{tex_filename.parent / tex_filename.stem}_{EDITED_SUFFIX}.tex")
    commented_tex_str = modifytex.commentSource(
        tex_str,
        char_positions,
        charpos_to_kinds_and_corrections,
        **kwargs
    )
    utils.writeStringToFile(commented_tex_str, commented_tex_filename)

    cwd = Path('./')

    # Verify that inserting the comments does not change the PDF
    process1 = utils.compileLatex(tex_filename, compiler=compiler)
    process2 = utils.compileLatex(commented_tex_filename, compiler=compiler)

    utils.transferTeXFiles(tex_filename, cwd, 'cp')
    utils.transferTeXFiles(commented_tex_filename, cwd, 'mv')
    
    if validate:
        process3, diff_fname = utils.runDiffpdf(
            utils.pdfFname(tex_filename),
            utils.pdfFname(commented_tex_filename),
            cwd,
            per_page_tol=0
        )

    if clean:
        logger.info("Deleting intermediate files.")
        diff_fname.unlink()
        utils.deleteIntermediateLaTeX(tex_filename)
        utils.deleteIntermediateLaTeX(commented_tex_filename)

    logger.info(f"Original and commented source produce identical PDFs.")
    logger.info(f"Correction comments successfully written to {commented_tex_filename.name}.")

    if not do_autocorrections:
        return 0

    logger.info("Doing autocorrections...")
    corrected_snippets = modifytex.getCorrectedSnippets(corrections, overlapping_keys)
    logger.info("Done.")
    
    autocorrected_tex_str = modifytex.commentSource(
        tex_str,
        char_positions,
        charpos_to_kinds_and_corrections,
        corrected_snippets = corrected_snippets,
        **kwargs
    )
    n_corrected = sum(1 for corr in corrections if corr.is_autocorrected)    
    
    # no validation because we expect pdf differences after autocorrections
    autocorrected_tex_filename = Path(f"{tex_filename.stem}_{AUTO_SUFFIX}.tex")
    utils.writeStringToFile(autocorrected_tex_str, autocorrected_tex_filename)

    logger.info(f"Autocorrected {n_corrected:3d}/{len(corrections):3d} corrections")
    logger.info(f"Autocorrected source successfully written to {autocorrected_tex_filename}.")

    return 0

def ProgramBanner():
    script_name = Path(sys.argv[0]).name
    return f"This is {script_name} version {__version__}\n"

def main():
    parser = argparse.ArgumentParser(
        description = r'Writes annotated PDF corrections into the source LaTeX as comments'
    )

    parser.add_argument('annotated_PDF_filename')
    parser.add_argument('latex_filename')

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help='debugging output'
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help='set logging level to only warnings or greater'
    )
    
    parser.add_argument(
        "--grp-overlap",
        action=argparse.BooleanOptionalAction,
        help='Merge overlapping selected snippets; default=True',
        default=True
    )
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        help='Delete intermediate LaTeX files and tmp dirs; default=True',
        default=True
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help='Automatically carry out simple corrections; default=False'
    )
    parser.add_argument(
        "--adjust-annots",
        action="store_true",
        help=(
            'Adjust non-caret annotation rectangles---a simple patch '
            'to a likely deeper bug; default=False'
        )
    )

    parser.add_argument(
        "--compiler",
        type=str,
        help='Specify the TeX compiler; default=pdflatex',
        default='pdflatex'
    )    
    parser.add_argument(
        "--extra-mark-envs",
        type=str,
        help=(
            'Comma-separated names of additional environments to mark inside. '
            'Example: `--extra-mark-envs="quote,textequation*"`; '
            'default = ""'
        ),
        default=''
    )
    parser.add_argument(
        "--comment-format",
        type=str,
        help=(
            'Specify how comments are inserted into the source. '
            f'Choices: "{cformats.FORMAT_FRONT}", '
            f'"{cformats.FORMAT_SPLIT}", and "{cformats.FORMAT_BACK}"; '
            f'default = `--comment-format="{cformats.DEFAULT_COMMENT_FORMAT}"`'
        ),
        default=cformats.DEFAULT_COMMENT_FORMAT
    )
    
    args = parser.parse_args()
    
    _level = logging.DEBUG if args.debug else logging.INFO
    _level = logging.WARN  if args.quiet else _level
    
    logging.basicConfig(
        encoding='utf-8',
        level=_level,
        format='%(levelname)s:%(module)s:%(message)s'
    ) 

    print(ProgramBanner())

    if not args.grp_overlap and args.autocorrect:
        logger.critical("Overlapping snippets must be merged to do autocorrections. Please either allow said merging or do not specify --autocorrect.")
        sys.exit(1)

    process_files(
        args.annotated_PDF_filename,
        args.latex_filename,
        group_overlapping = args.grp_overlap,
        compiler          = args.compiler,        
        clean             = args.clean,
        autocorrect       = args.auto,
        adjust_annots     = args.adjust_annots,
        extra_mark_envs   = args.extra_mark_envs,
        comment_format    = args.comment_format,
    )    
    
    # TODO: add a way of automatically removing the inlined correction comments

if __name__ == '__main__':    
    main()
