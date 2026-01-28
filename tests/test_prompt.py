from texpdfedits.prompt import Correction, getCorrections, writeListOfPrompts

import logging
import argparse
import pymupdf

from pathlib import Path
import os

from test_extract import shipPdfFilename

def drawPromptsOnPages(corrections: list[Correction], annotpdf_filename: str, latex_filename: str, output_dir: str, unique_ending = 'draw_prompts') -> None:
    word_boxes_filename = Path('bbox_drawings') / f'{Path(latex_filename).stem}_word_boxes.pdf'
    if Path(word_boxes_filename).exists():
        open_filename = word_boxes_filename
    else:
        open_filename = annotpdf_filename

    logging.info(f"open_filename in drawPromptsOnPages() is {open_filename}")

    save_filename = shipPdfFilename(latex_filename, output_dir, unique_ending)

    single_fname_prefix = Path(output_dir) / f'{Path(latex_filename).stem}_{unique_ending}'
    singlepage_file_names = []

    for i, correction in enumerate(corrections):
        doc = pymupdf.open(open_filename)
        
        pageno = correction.pageno
        selection_bbs = correction.pdf_selection_bbs
        ann_line_rect = correction.pdf_annot_rect
        
        prompt = correction.asMarkdownPrompt()
        
        page_count = doc.page_count
        if pageno < page_count-1:
            doc.delete_pages(from_page=pageno+1)
        if pageno >= 1:
            doc.delete_pages(from_page=0, to_page=pageno-1)
        
        if doc.page_count != 1:
            logging.warning(f"Intermediate pages for prompt {i} only reduced to {doc.page_count} pages, not one; skipping")
            continue
        
        page = doc[0]

        extract_latex_rect = page.add_freetext_annot(ann_line_rect, 'ann rect', text_color=(1,0,0), fontsize=4, fontname="Cour")
        extract_latex_rect.set_border(width=.75)
        extract_latex_rect.update()

        prompt_box = page.add_freetext_annot((3, 0, 500, 350), prompt, text_color=(0,.75,.2), fontsize=6, fontname="Cour")
        prompt_box.set_border(width=.25)
        prompt_box.update()

        single_save = f'{single_fname_prefix}_{i}.pdf'
        doc.save(single_save)
        
        singlepage_file_names.append(single_save)
        logging.info(f'Drew prompt {i+1:3d}/{len(corrections):3d}')

    logging.info(f'Done. Intermediate files written to {output_dir}.')
    logging.info("Combining intermediate files...")    
    combined_doc = pymupdf.open(open_filename)
    ## silly, but I'm not aware of a simpler way
    combined_doc.delete_pages(from_page=0, to_page=combined_doc.page_count-1)
    for single_page in singlepage_file_names:
        single_pdf = pymupdf.open(single_page)
        combined_doc.insert_pdf(single_pdf, annots=True)

    combined_doc_filename = shipPdfFilename(open_filename, output_dir, unique_ending)
    combined_doc.save(combined_doc_filename)
    logging.info(f"Done. Combined document saved to {combined_doc_filename}.")    

    logging.debug("Deleting intermediate PDFs...")
    os.system(f"rm {single_fname_prefix}_*.pdf")
    logging.debug("Done.")
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annotpdf_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-dp", "--draw-prompts", action="store_true", help='draw prompts and selection bounding boxes on pdf pages')    
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    corrections = getCorrections(args.annotpdf_filename, args.latex_filename)

    if args.draw_prompts:
        drawPromptsOnPages(corrections, args.annotpdf_filename, args.latex_filename, 'bbox_drawings')
