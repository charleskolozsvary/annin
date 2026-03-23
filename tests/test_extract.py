import pymupdf
import argparse
import logging

from texpdfedits.extractanns import getRobustAnnots, getEdits, Annot

import texpdfedits.utils as utils

from pathlib import Path

pymupdf.TOOLS.set_small_glyph_heights(True)

import os

def shipPdfFilename(filename, output_dir, unique_ending):
    out_dir = Path(output_dir)
    Path.mkdir(out_dir, exist_ok=True)
    return out_dir / f'{Path(filename).stem}_{unique_ending}.pdf'

def drawAnnots(filename, output_dir, unique_ending = 'orig_annots'):
    """draw bounding boxes of original annotations in annotated PDF"""
    doc = pymupdf.open(filename)
    save_filename = shipPdfFilename(filename, output_dir, unique_ending)
    logging.info(f"Drawing original annotations to {save_filename}...")
    for page in doc:
        for annot in page.annots():
            if annot.type[0] == Annot.TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(save_filename)
    logging.info(f"Done. Results saved to {save_filename}.")


def drawRobustAnnots(filename, robust_annots, output_dir, unique_ending = 'robust_annots'):
    """draw bounding boxes of robust annotations"""
    doc = pymupdf.open(filename)
    save_filename = shipPdfFilename(filename, output_dir, unique_ending)    
    logging.info(f"Drawing robust annotations to {save_filename}...")    
    for pageno,page in enumerate(doc):
        for annot in annots[pageno]:
            if annot.type[0] == Annot.TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(save_filename)
    logging.info(f"Done. Results saved to {save_filename}")

def drawCharacters(filename, output_dir, unique_ending = 'pymupdf_characters', **kwargs):
    logging.info(f"Drawing character boxes in {filename}...")
    pymupdf.TOOLS.set_small_glyph_heights(True)
    doc = pymupdf.open(filename)
    save_filename = shipPdfFilename(filename, output_dir, unique_ending)

    draw_page = kwargs.get('chars_draw_page', 1)
    
    for i, page in enumerate(doc):
        if i != draw_page:
            continue
        raw_dict = page.get_text('rawdict', sort=True)

        blocks = raw_dict.get('blocks')
        bar = utils.TextProgressBar(len([0 for block in blocks for line in block.get('lines')]))
        bar.showSize()           
        for block in blocks:
            for line in block.get('lines'):
                for span in line.get('spans'):
                    for char in span.get('chars'):
                        # x0, y0, x1, y1 = char['bbox'] 
                        # char_center = (x0 + (x1 - x0)/2, y0 + (y1 - y0)/2)
                        # char_off = (char_center[0]+.0001, char_center[1]+.0001)
                        char_rect = pymupdf.Rect(*char['bbox'])
                        if char_rect.is_valid and not char_rect.is_empty:
                            box = page.add_freetext_annot(char_rect, '', text_color=(1,0,1))
                            box.set_border(width=0.1)
                            box.update()
                            
                            ox, oy = char['origin']
                            # print(ox, oy)
                            origin_rect = pymupdf.Rect(ox, oy, ox+1, oy+1)
                            box2 = page.add_circle_annot(origin_rect)
                            box2.set_border(width=0.25)
                            box2.update()
                            
                bar.addProgress()
        bar.end()
        logging.info(f"Drew character rectangles on page {i:3d} of {filename}")
        break
    doc.save(save_filename)
    logging.info(f"Done. Results saved to {save_filename}.")
        

def drawWords(filename, output_dir, unique_ending = 'pymupdf_words'):
    logging.info(f"Drawing word boxes in {filename}...")
    doc = pymupdf.open(filename)
    save_filename = shipPdfFilename(filename, output_dir, unique_ending)
    for page in doc:
        words = page.get_text('words', sort=True)
        for word in words:
            box = page.add_freetext_annot(word[0:4], f'{word[5]}:{word[6]}:{word[7]}', text_color=(1,0,1), fontsize=2, fontname="Cour")
            box.set_border(width=0.5)
            box.update()
    doc.save(save_filename)
    logging.info(f"Done. Results saved to {save_filename}.")


def drawLines(filename, output_dir, unique_ending = 'lines'):
    """draw the bounding boxes of the lines from page.get_text('dict', sort=True)['blocks']"""
    logging.info(f"Drawing line boxes in {filename}...")
    doc = pymupdf.open(filename)
    save_filename = shipPdfFilename(filename, output_dir, unique_ending)    
    for page in doc:
        blocks = page.get_text('dict', sort=True)['blocks']
        line_bbs = []
        line_bbs = [line['bbox'] for block in blocks for line in block['lines']]        
        for bb in line_bbs:
            box = page.add_freetext_annot(bb, '', text_color=(1,0,0))
            box.set_border(width=.5)
            box.update()
    doc.save(save_filename)
    logging.info(f"Done. Results saved to {save_filename}.")    
    return 0

def drawEdits(filename, output_dir, edits, unique_ending = 'edit_selections'):
    """draw the bounding boxes for extracting the selected text and the Edit json for each annotation
       yes this is more messy than it needs to be
    """
    single_fname_prefix = Path(output_dir) / f'{Path(filename).stem}_{unique_ending}'
    singlepage_file_names = []

    logging.info("Drawing edit selections on PDF...")
    for i, edit in enumerate(edits):
        doc = pymupdf.open(filename)
        page_count = doc.page_count
        if edit.pageno < page_count-1:
            doc.delete_pages(from_page=edit.pageno+1)
        if edit.pageno >= 1:
            doc.delete_pages(from_page=0, to_page=edit.pageno-1)
        assert doc.page_count == 1, "doc.page_count != 1"
        page = doc[0]
        selection_bbs = edit.selection_bbs

        box2 = page.add_freetext_annot(edit.annot_rect, '', fontsize=8, text_color=(1,.5,1))
        box2.set_border(width=.25)
        box2.update()
        
        for bbs in selection_bbs:
            if len(bbs) == 2:
                colors = [(1,0,0), (0,0,1)]
            elif len(bbs) == 3:
                colors = [(1,.25,.25), (.25,1,.25), (.25,.25,1)]
            else:
                logging.warning("an individual selection bb did not have two or three members when drawing...; continuing")
                continue
            for j, bb in enumerate(bbs):
                if bb.width == 0:
                    continue
                if bb.height == 0:
                    logging.warning("bb height was zero that ... shouldn't happen, continuing with modified height")
                    bb.y1 = bb.y0 + 5 ## see endomorphism_ann page 13
                box = page.add_freetext_annot(bb, '', text_color=colors[j])
                box.set_border(width=.75)
                box.update()
        
        box = page.add_freetext_annot((5,5,500,350), str(edit), fontsize=8, fontname="Cour", text_color=(.5, 0, .75))
        box.update()

        single_save = f'{single_fname_prefix}_{i}.pdf'
        doc.save(single_save)
        
        singlepage_file_names.append(single_save)
        logging.info(f'Drew edit selection {i+1:3d}/{len(edits):3d}')

    logging.info(f'Done. Intermediate files written to {output_dir}.')
    logging.info("Combining intermediate files...")
    combined_doc = pymupdf.open(filename)
    ## silly, but I'm not aware of a simpler way
    combined_doc.delete_pages(from_page=0, to_page=combined_doc.page_count-1)
    for single_page in singlepage_file_names:
        single_pdf = pymupdf.open(single_page)
        combined_doc.insert_pdf(single_pdf, annots=True)

    combined_doc_filename = shipPdfFilename(filename, output_dir, unique_ending)
    combined_doc.save(combined_doc_filename)
    logging.info(f"Done. Combined document saved to {combined_doc_filename}.")
    
    logging.debug("Deleting intermediate PDFs...")
    os.system(f"rm {single_fname_prefix}_*.pdf")
    logging.debug("Done.")

    return 0
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf_filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-c", "--draw-chars", action="store_true", help='draw character boxes')            
    parser.add_argument("-w", "--draw-words", action="store_true", help='draw word boxes')        
    parser.add_argument("-l", "--draw-lines", action="store_true", help='draw line boxes')
    parser.add_argument("-a", "--draw-annots", action="store_true", help='draw original and robust annot boxes')    
    parser.add_argument("-e", "--draw-edits", action="store_true", help='draw edit selections')
    parser.add_argument("--adjust-annots", action="store_true", help='Try adjusting the widths of the noncaret Annots; default=False')
    parser.add_argument("--chars-draw-page", type=int, help='page (zero indexed) to draw individual char rectangles if specified; default=1', default=1)
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')    

    filename = args.pdf_filename
    
    bb_dir = Path('bbox_drawings')

    kwargs = dict()
    if args.chars_draw_page:
        kwargs['chars_draw_page'] = args.chars_draw_page

    if args.draw_chars:
        drawCharacters(filename, bb_dir, **kwargs)

    if args.draw_words:
        drawWords(filename, bb_dir)

    if args.draw_lines:
        drawLines(filename, bb_dir)

    if args.draw_annots:
        drawAnnots(filename, bb_dir)

        doc = pymupdf.open(filename)
        annots = getRobustAnnots(doc, adjust_annots=args.adjust_annots) # from extract.py    
        drawRobustAnnots(filename, annots, bb_dir)


    logging.info(f'Running getEdits({filename})...')
    edits = getEdits(filename, adjust_annots=args.adjust_annots)
    logging.info("Done.")
        
    if args.draw_edits:    
        drawEdits(filename, bb_dir, edits)

    json_edits_dir = Path('extracted_edit_txts')
    Path.mkdir(json_edits_dir, exist_ok=True)

    json_edits_filename = f'{Path(json_edits_dir) / Path(filename).stem}_edits.txt'
    logging.info(f"Writing list of json edits to {json_edits_filename}")
    edits_str = ''
        
    for i, edit in enumerate(edits):
        edits_str += f'{i} {edit}\n\n'
    with open(json_edits_filename, 'w') as f:
        f.write(edits_str)
    logging.info("Done.")

    
    
