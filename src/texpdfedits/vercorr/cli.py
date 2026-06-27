import logging
logger = logging.getLogger(__name__)
import argparse
import re
import sys
import subprocess
from pathlib import Path

import texpdfedits.utils as utils
from texpdfedits.vercorr.help import EPILOG

__version__ = "0.0.0"

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='displays status and before and after images for each annotation',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument('pdf_file')
    parser.add_argument('latex_file')
    
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
        "--clean",
        action=argparse.BooleanOptionalAction,
        help='delete intermediate files; default=True',
        default=True
    )
    parser.add_argument(
        "--update",
        action=argparse.BooleanOptionalAction,
        help='update annotation statuses; default=True',
        default=True
    )

    parser.add_argument(
        "-f",
        "--filter",
        type=str,
        help='comma-separated key=value pairs for filtering annotations',
        default='',
    )

    args = parser.parse_args()

    return args

def set_up_logger(args: argparse.Namespace):
    script_name = Path(sys.argv[0]).name
    log_file = Path(f'{script_name}_{args.pdf_file.stem}.log')
            
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

def process_files(args: argparse.Namespace):
    raise NotImplementedError()

def main():
    args = _parse_args()
    set_up_logger(args)
    logger.info(program_banner())
    process_files(args)
    
if __name__ == '__main__':
    main()
