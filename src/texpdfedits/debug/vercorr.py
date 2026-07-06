import logging
logger = logging.getLogger(__name__)
import sys
import argparse
from pathlib import Path
import pymupdf
from PIL import Image
from icecream import ic
import time

import texpdfedits.vercorr.manu as manu

from texpdfedits.extractanns import Edit
from texpdfedits.vercorr.manu import Manuscript

__version__ = '0.1.0'

def show_edit_image(doc: Manuscript, edit: Edit):
    pixmap = manu.get_before_pixmap(doc, edit)
    test_name = 'test.png'
    pixmap.save(test_name)
    im = Image.open(test_name)
    im.show()

def show_images_before(doc: Manuscript):
    pixmaps = manu.get_before_pixmaps(doc)
    test_dir = Path('vercorr_im_before')
    Path.mkdir(test_dir, exist_ok=True)
    for i, pix in enumerate(pixmaps):
        test_name = f'{test_dir}/test{i}.png'
        pix.save(test_name)
        # im = Image.open(test_name)
        # im.show()

def show_images_after(doc: Manuscript):
    pixmaps = manu.get_after_pixmaps(doc)
    test_dir = Path('vercorr_im_after')
    Path.mkdir(test_dir, exist_ok=True)
    for i, pix in enumerate(pixmaps):
        test_name = f'{test_dir}/test{i}.png'
        # ic(i, doc.edits[i].xref)
        if pix is not None:
            pix.save(test_name)
        else:
            logger.info(f"test{i} was None")
        # im = Image.open(test_name)
        # im.show()        

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('annots_pdf')
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
    set_up_logger(args)

    start = time.time()
    doc = Manuscript(args.annots_pdf, args.latex_file, args)
    # ic(doc.xref_to_annidx)
    # ic(doc.annidx_to_line)
    # ic(doc.xref_to_line)

    show_images_before(doc)
    show_images_after(doc)
    end = time.time()
    print(end - start)

if __name__ == '__main__':
    main()
