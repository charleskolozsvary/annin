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
import texpdfedits.formatcomm as formatcomm

from importlib.metadata import version
__version__ = version('texpdfedits')

INLINED_TAG = 'inlined'
AUTO_TAG = 'autocorrected'

def process_files(*args, **kwargs) -> int:
    annot_filename, tex_filename = args
    
    compiler           = kwargs.get('compiler', utils.DEFAULT_LATEX_COMPILER)
    clean              = kwargs.get('clean', True)    
    validate           = kwargs.get('validate', True)
    do_autocorrections = kwargs.get('autocorrect', False)
    delete_comments    = kwargs.get('delete_comments', False)
    comment_format     = kwargs.get('comment_format', formatcomm.DEFAULT_COMMENT_FORMAT)

    tex_filename = Path(tex_filename)
    tex_str = utils.sourceAsString(tex_filename)    

    if delete_comments:
        logger.info(f"Deleting comments from {tex_filename}...")
        (_, nocomments_file) = formatcomm.deleteComments(tex_filename, comment_format)
        logger.info(f"Done. Written to {nocomments_file}")

        utils.compileValidateClean(tex_filename, nocomments_file, Path('./'), **kwargs)
        return 0

    kwargs['replace'] = False    
        
    corrections, overlapping_keys = corr.getCorrections(
        *args,
        **kwargs,
    )
    
    (char_positions, charpos_to_kinds_and_corrections) = modifytex.getSourcePosToCorrections(corrections)
    
    commented_tex_filename = Path(f"{tex_filename.parent / tex_filename.stem}_{INLINED_TAG}.tex")
    commented_tex_str = modifytex.commentSource(
        tex_str,
        char_positions,
        charpos_to_kinds_and_corrections,
        **kwargs
    )
    utils.writeStringToFile(commented_tex_str, commented_tex_filename)

    cwd = Path('./')

    utils.compileValidateClean(tex_filename, commented_tex_filename, cwd, **kwargs)

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
    autocorrected_tex_filename = Path(f"{tex_filename.stem}_{AUTO_TAG}.tex")
    utils.writeStringToFile(autocorrected_tex_str, autocorrected_tex_filename)

    logger.info(f"Autocorrected {n_corrected:3d}/{len(corrections):3d} corrections")
    logger.info(f"Autocorrected source written to {autocorrected_tex_filename}.")

    return 0

def ProgramBanner():
    script_name = Path(sys.argv[0]).name
    return f"This is {script_name} version {__version__}\n"

def main():
    parser = argparse.ArgumentParser(
        description = r'Writes PDF corrections into the source LaTeX as comments'
    )

    parser.add_argument('annotated_PDF_file')
    parser.add_argument('latex_file', nargs='?', default=None)

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
        help='Merge overlapping correction snippets; default=True',
        default=True
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
        help='Overwrite latex file comments are deleted successfully; default=True',
        default=True
    )
    parser.add_argument(
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
    parser.add_argument(
        "--extra-mark-envs",
        type=str,
        help=(
            'Comma-separated names of additional environments to mark'
        ),
        default=''
    )
    parser.add_argument(
        "--comment-format",
        type=str,
        help=(
            'Customize how comments are inserted. '
            f'Choices: {formatcomm.FORMAT_FRONT}, '
            f'{formatcomm.FORMAT_SPLIT}, and {formatcomm.FORMAT_BACK}; '
            f'default={formatcomm.DEFAULT_COMMENT_FORMAT}'
        ),
        default=formatcomm.DEFAULT_COMMENT_FORMAT
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

    if args.latex_file is None and not args.delete_comments:
        logger.critical("Missing latex_file")
        sys.exit(1)

    if args.delete_comments and args.latex_file is None:
        logger.info(f"Treating {args.annotated_PDF_file} as latex_file")
        latex_file = args.annotated_PDF_file
    else:
        latex_file = args.latex_file    

    if not args.grp_overlap and args.autocorrect:
        logger.critical("Overlapping snippets must be merged to do autocorrections. Please either allow said merging or do not specify --autocorrect.")
        sys.exit(1)

    process_files(
        args.annotated_PDF_file,
        latex_file,
        group_overlapping = args.grp_overlap,
        compiler          = args.compiler,        
        clean             = args.clean,
        autocorrect       = args.auto,
        adjust_annots     = args.adjust_annots,
        extra_mark_envs   = args.extra_mark_envs,
        comment_format    = args.comment_format,
        delete_comments   = args.delete_comments,
        replace           = args.replace,
    )    
    
    # TODO: add a way of automatically removing the inlined correction comments

if __name__ == '__main__':    
    main()
