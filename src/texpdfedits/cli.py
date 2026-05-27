import logging
logger = logging.getLogger(__name__)
import argparse
import re
import sys
from pathlib import Path

import texpdfedits.extract as extract
import texpdfedits.corr as corr
import texpdfedits.modify as modify
import texpdfedits.utils as utils

from importlib.metadata import version
__version__ = version('texpdfedits')

def _process_files(*args, delete_comments: bool, **kwargs) -> int:
    if delete_comments:
        _delete_comments(*args, **kwargs)
    else:
        _inline_corr(*args, **kwargs)
    return 0

def _delete_comments(
        pdf_file: Path,
        latex_file: Path,
        *,
        replace: bool,
        **_,
):
    formatcomm.delete_comments(latex_file, replace)

def _inline_corr(
        pdf_file: Path,
        latex_file: Path,
        *,
        compiler: str,
        adjust_annots: bool,
        autocorrect: bool,
        clean: bool,
        **_,
):
    # extract PDF information    
    edits = extract.get_edits(pdf_file, adjust_annots)
    
    # map PDF coordinates to LaTeX
    orig_output = utils.compile_latex(latex_file, compiler)
    corrections = corr.get_corrections(latex_file, orig_output, edits)
    
    # modify LaTeX, inserting corrections as comments
    inlined = modify.inline_comments(
        latex_file,
        corrections,
    )
    inlined_out = utils.compile_latex(inlined, compiler)

    # validate visually identical
    utils.run_diff_pdf(orig_output, inlined_out)

    if autocorrect:
        _ = modify.inline_comments(
            latex_file,
            corrections,
            autocorrect = True,
        )

    if clean:
        utils.delete_intermediate_latex(latex_file)

def _program_banner():
    script_name = Path(sys.argv[0]).name
    return f"This is {script_name} version {__version__}"

def main():
    parser = argparse.ArgumentParser(
        description = f'Writes PDF corrections into the source LaTeX as comments'
    )

    parser.add_argument('latex_file')
    parser.add_argument('pdf_file', nargs='?', default=None)

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

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
        "--clean",
        action=argparse.BooleanOptionalAction,
        help='Delete intermediate LaTeX files and tmp dirs; default=True',
        default=True
    )
    
    parser.add_argument(
        "--replace",
        action=argparse.BooleanOptionalAction,
        help='Overwrite latex file when comments are deleted successfully; default=True',
        default=True
    )
    
    parser.add_argument(
        "-a",
        "--auto",
        action="store_true",
        help='Do simple corrections automatically; default=False'
    )
    
    parser.add_argument(
        "--adjust-annots",
        action="store_true",
        help=('Adjust annotation rectangles')
    )
    
    parser.add_argument(
        "-dc",
        "--delete-comments",
        action="store_true",
        help=('Remove inserted comments from LaTeX.'),
    )

    parser.add_argument(
        "--compiler",
        type=str,
        help='TeX compiler; default=pdflatex',
        default=utils.DEFAULT_LATEX_COMPILER
    )
    
    args = parser.parse_args()
        
    log_file = utils.new_tagged_fname(
        Path(args.latex_file),
        'corrinline',
        new_suffix='.log',
        put_front=True,
    )
            
    logger_level = logging.DEBUG if args.debug else logging.INFO
    logger_level = logging.WARN  if args.quiet else logger_level
    
    logging.basicConfig(
        encoding='utf-8',
        level=logger_level,
        format='%(levelname)-8s | %(module)-11s | %(message)s',
        handlers = [
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding='utf-8', mode='w'),
        ],
    )

    logger.info(_program_banner())

    if args.pdf_file is None and not args.delete_comments:
        logger.critical("Missing pdf_file")
        sys.exit(1)

    latex_file = Path(args.latex_file)
    
    if args.pdf_file is None:
        pdf_file = Path()
    else:
        pdf_file = Path(args.pdf_file)

    if not pdf_file.exists():
        logger.critical(f"{pdf_file} does not exist")
        sys.exit(1)
        
    if not latex_file.exists():
        logger.critical(f"{latex_file} does not exist")
        sys.exit(1)

    _process_files(
        pdf_file,
        latex_file,
        compiler        = args.compiler,
        clean           = args.clean,
        autocorrect     = args.auto,
        adjust_annots   = args.adjust_annots,
        delete_comments = args.delete_comments,
        replace         = args.replace,
    )

if __name__ == '__main__':    
    main()
