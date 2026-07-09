from texpdfedits.marktex import getSyncInfo, getWordBoxes, unMarkWithPositions
from texpdfedits.corr import rectangleToLatex, getPageLabels
from texpdfedits.utils import sourceAsString, DEFAULT_LATEX_COMPILER, TextProgressBar, fromRoman

import logging
logger = logging.getLogger(__name__)

import argparse
import pymupdf
from pathlib import Path

def parse_rectangle(s):
    """Parse a rectangle string like '(0,0,10,10)' into a tuple of floats."""
    try:
        # Remove parentheses and split by comma
        parts = s.strip('()').split(',')
        if len(parts) != 4:
            raise argparse.ArgumentTypeError("Rectangle must have 4 values: (x0,y0,x1,y1)")
        return tuple(float(x) for x in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("Rectangle values must be numbers")

def drawWordBoxes(pdf_filename, document_word_boxes, output_dir, page_labels):
    save_file_name = Path(output_dir) / f'{Path(pdf_filename).stem}_word_boxes.pdf'
    logging.info(f"Drawing word boxes on {pdf_filename} to {save_file_name}...")
    bar = TextProgressBar(len(document_word_boxes))
    bar.showSize()
    doc = pymupdf.open(pdf_filename)
    for page_label in document_word_boxes:
        pg_no = page_labels.index(page_label)
        page = doc[pg_no]
        for key, rectangle in document_word_boxes[page_label].items():
            try:
                box = page.add_freetext_annot(rectangle, key, text_color=(0,.25,.7), fontsize=1, fontname="Cour")
                box.set_border(width=.3)
                box.update()
            except Exception as e:
                logging.warning(f"Could not draw word box ('{key}', '{rectangle}'); skipping")
        bar.addProgress()
    bar.end()
                            
    doc.save(save_file_name)
    logging.info("Done.")
    return 0

def testRectangleToLatex(
        page_labels: list[str],
        page_label: str,
        in_rectangle: pymupdf.Rect,
        document_word_boxes: dict[int, dict[str, pymupdf.Rect]],
        mark_positions: dict[str, tuple[int, int]],
        tex_str: str,
        pdf_filename: str,
        output_dir: str
) -> None:
    word_boxes_file = Path(output_dir) / f'{Path(pdf_filename).stem}_word_boxes.pdf'    
    save_file_name = Path(output_dir) / f'{Path(pdf_filename).stem}_rectangle_test.pdf'

    if Path(word_boxes_file).exists():
        doc = pymupdf.open(word_boxes_file)
    else:
        doc = pymupdf.open(pdf_filename)

    page = doc[page_labels.index(page_label)]
    
    box = page.add_freetext_annot(in_rectangle, 'in_rectangle', text_color=(1,.25,.7), fontsize=9, fontname="Cour")
    box.set_border(width=.5)
    box.update()

    latex_snippet, source_positions = rectangleToLatex(page_labels, page_label, in_rectangle, document_word_boxes, mark_positions, tex_str)

    logging.info(
        f"Here's the latex extracted by the rectangle drawn on {save_file_name}\n```latex\n"
        rf"{latex_snippet}"
        "\n```"
    )

    if latex_snippet is not None:
        latex_box = page.add_freetext_annot((5,5,580,100), latex_snippet, text_color=(1,.25,.7), fontsize=8, fontname="Cour")
        latex_box.set_border(width=.5)
        latex_box.update()

    doc.save(save_file_name)
    
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tex_filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-db", "--drawboxes", action = "store_true", help='draw individual boxes')

    parser.add_argument(
        "-r", "--rectangle",
        type=parse_rectangle,
        help='Rectangle coordinates as (x0,y0,x1,y1)'
    )

    parser.add_argument(
        "--page_label",
        type=str,
        help='Page label for the rectangle'
    )

    parser.add_argument("-emen", "--extra-marked-environment-names", type=str, help='Comma-separated extra environment names to mark in---last resort')
    parser.add_argument("--compiler", type=str, help='LaTeX compiler', default=DEFAULT_LATEX_COMPILER)
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, help='Delete intermediate LaTeX files and tmp dirs; default=True', default=True)        
    
    args = parser.parse_args()
    
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(encoding='utf-8', level=_level) 

    if args.rectangle:
        in_rectangle = pymupdf.Rect(args.rectangle)
    else:
        in_rectangle = pymupdf.Rect(250, 605, 300, 617)

    if args.page_label:
        in_recpage = args.page_label
    else:
        in_recpage = '1'

    if args.extra_marked_environment_names is not None:
        extra_names = args.extra_marked_environment_names
    else:
        extra_names = ''

    latex_file = Path(args.tex_filename)

    mark_positions, document_word_boxes = getSyncInfo(latex_file, extra_mark_envs=extra_names, compiler=args.compiler, clean=args.clean, validate=True)

    tex_str = sourceAsString(latex_file)

    logging.info("Finished segment().")
    
    output_dir = 'bbox_drawings'
    if not Path(output_dir).exists():
        Path.mkdir(output_dir)

    pdf_filename = Path(latex_file).parent / f'{Path(latex_file).stem}.pdf'

    if not pdf_filename.exists():
        print(f"{pdf_filename} doesn't exist... exiting")
        return

    page_labels = getPageLabels(pdf_filename)
    if '' in page_labels:
        print(f"some page labels were empty")
        return
    
    testRectangleToLatex(page_labels, in_recpage, in_rectangle, document_word_boxes, mark_positions, tex_str, pdf_filename, output_dir)
    
    if args.drawboxes:
        drawWordBoxes(pdf_filename, document_word_boxes, output_dir, page_labels)

if __name__ == '__main__':
    main()
