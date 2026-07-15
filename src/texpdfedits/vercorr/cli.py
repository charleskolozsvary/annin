import logging
logger = logging.getLogger(__name__)
import argparse
import re
import sys
import subprocess
from pathlib import Path

import texpdfedits.utils as utils
import texpdfedits.vercorr.manu as manu
import texpdfedits.vercorr.apptk as apptk

__version__ = "0.1.0"

EPILOG = """
Example usage:
    %(prog)s --compiler=xelatex annotations.pdf source.tex

    If there's already an existing PDF and .synctex.gz, you can do

    %(prog)s --compiler=xelatex --no-gen-synctex annotations.pdf source.tex

    then source.tex is not recompiled with SyncTeX

GUI shortcuts:
    There are a handful of single key shortcuts while interacting with the GUI.
    They effect/are relative to the current highlighted annotation.

    | Key | Action              |
    |-----|---------------------|
    | n   | next annotation     |
    | p   | previous annotation |
    | m   | check/uncheck       |
    | d   | status "None"       |
    | r   | status "Rejected"   |
    | a   | status "Accepted"   |
    | c   | status "Completed"  |
    | x   | status "Cancelled"  |

"""

SHOW_LONG_HELP = "--long-help" in sys.argv

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='displays status and before and after images for each annotation',
        epilog=EPILOG if SHOW_LONG_HELP else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('annots_pdf')
    parser.add_argument('latex_file')

    parser.add_argument(
        "--long-help",
        action="help",
        help="show extended help and exit",
    )
    
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
        help='set logging level only warnings or greater'
    )
    
    parser.add_argument(
        '--compiler',
        type=str,
        default='pdflatex',
    )
    
    parser.add_argument(
        '--gen-synctex',
        action=argparse.BooleanOptionalAction,
        default=True,
    )    

    args = parser.parse_args()

    return args

def set_up_logger(args: argparse.Namespace):
    script_name = Path(sys.argv[0]).name
    annots_pdf = Path(args.annots_pdf)
    log_file = Path(f'{script_name}_{annots_pdf.stem}.log')
            
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

def program_banner():
    script_name = Path(sys.argv[0]).name
    return f"This is {script_name} version {__version__}"

def main():
    args = _parse_args()
    set_up_logger(args)
    logger.info(program_banner())
    doc = manu.Manuscript(args.annots_pdf, args.latex_file, args)
    logger.debug(f"Before and after images written to {doc.before_after_dir}")
    apptk.run_gui(doc)
    
if __name__ == '__main__':
    main()
