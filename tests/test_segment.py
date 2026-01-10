from texpdfedits.segmentsource import segment, getWordBoxes, rectangleToLatex
import logging
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

def drawWordBoxes(pdf_filename, document_word_boxes, output_dir):
    save_file_name = Path(output_dir) / f'{Path(pdf_filename).stem}_word_boxes.pdf'
    logging.info(f"Drawing word boxes on {pdf_filename} to {save_file_name}... (this can take a while)")
    doc = pymupdf.open(pdf_filename)
    for pg_no in document_word_boxes:
        page = doc[pg_no]
        for key, rectangle in document_word_boxes[pg_no].items():
            try:
                box = page.add_freetext_annot(rectangle, key, text_color=(0,.25,.7), fontsize=3, fontname="Cour")
                box.set_border(width=.3)
                box.update()
            except Exception as e:
                logging.warning(f"Could not draw word box ('{key}', '{rectangle}'); skipping")
                
            
    doc.save(save_file_name)
    logging.info("Done.")
    return 0

def testRectangleToLatex(pageno: int, in_rectangle: pymupdf.Rect, document_word_boxes: dict[int, dict[str, pymupdf.Rect]], marked_document: str, pdf_filename, output_dir):
    word_boxes_file = Path(output_dir) / f'{Path(pdf_filename).stem}_word_boxes.pdf'    
    save_file_name = Path(output_dir) / f'{Path(pdf_filename).stem}_rectangle_test.pdf'

    if Path(word_boxes_file).exists():
        doc = pymupdf.open(word_boxes_file)
    else:
        doc = pymupdf.open(pdf_filename)

    page = doc[pageno]
    
    box = page.add_freetext_annot(in_rectangle, 'in_rectangle', text_color=(1,.25,.7), fontsize=9, fontname="Cour")
    box.set_border(width=.5)
    box.update()

    latex = rectangleToLatex(pageno, in_rectangle, document_word_boxes, marked_document)

    logging.info(
        f"Here's the latex extracted by the rectangle drawn on {save_file_name}\n```latex\n"
        rf"{latex}"
        "\n```"
    )

    if latex is not None:
        latex_box = page.add_freetext_annot((5,5,350,350), latex, text_color=(1,.25,.7), fontsize=8, fontname="Cour")
        latex_box.set_border(width=.5)
        latex_box.update()

    doc.save(save_file_name)
    
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-db", "--drawboxes", action = "store_true", help='draw individual boxes')

    parser.add_argument(
        "-r", "--rectangle",
        type=parse_rectangle,
        help='Rectangle coordinates as (x0,y0,x1,y1)'
    )

    parser.add_argument(
        "--page",
        type=int,
        help='Page number for the rectangle'
    )    
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.rectangle:
        in_rectangle = pymupdf.Rect(args.rectangle)
    else:
        in_rectangle = pymupdf.Rect(500, 405, 550, 417)

    if args.page:
        in_recpage = args.page
    else:
        in_recpage = 0

    num_boxes, marked_tex, document_word_boxes, all_metadata = segment(args.filename)
    
    output_dir = 'bbox_drawings'
    pdf_filename = Path(args.filename).parent / f'{Path(args.filename).stem}.pdf'
        
    testRectangleToLatex(in_recpage, in_rectangle, document_word_boxes, marked_tex, pdf_filename, output_dir)

    if args.drawboxes:
        drawWordBoxes(pdf_filename, document_word_boxes, output_dir)
