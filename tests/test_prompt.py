from texpdfedits.corrinput import getCorrections

import logging
import argparse
import pymupdf

from test_extract import shipPdfFilename

def drawPrompts(corrections, test_info, annotpdf_filename, latex_filename, output_dir, unique_ending = 'prompt_draw'):
    assert len(corrections) == len(test_info)

    open_filename = annotpdf_filename

    save_filename = shipPdfFilename(latex_filename, output_dir, unique_ending)

    out_str = ''
    single_fname_prefix = Path(output_dir) / f'{Path(latex_filename).stem}_{unique_ending}'
    singlepage_file_names = []


    ## INCOMPLETE; pulled over most from test_extract but did not integrate. And that code is hastily written to begin with

    for i in range(len(corrections)):
        doc = pymupdf.open(open_filename)

        t_info = test_info[i]
        pageno = t_info['page']
        selection_bbs = t_info['selection_bbs']
        ann_line_rect = t_info['ann_line_rect']
        
        correction = corrections[i]
        
        page_count = doc.page_count
        if pageno < page_count-1:
            doc.delete_pages(from_page=pageno+1)
        if pageno >= 1:
            doc.delete_pages(from_page=0, to_page=pageno-1)
        assert doc.page_count == 1, "doc.page_count != 1"
        page = doc[0]

        # (rectangle, key, text_color=(0,.25,.7), fontsize=3, fontname="Cour")
        extract_latex_rect = page.add_freetext_annot(ann_line_rect, 'ann_line_rect', text_color=(0,.25,.7), fontsize=5, fontname="Cour")
        extract_latex_rect.set_border(width=.3)
        extract_latex_rect.update()

        prompt_box = page.add_freetext_annot((10, 10, 300, 200), correction, text_color=(1,.25,.7), fontsize=10, fontname="Cour")
        prompt_box.set_border(width=1)
        prompt_box.update()

        #### >>>
        single_save = f'{single_fname_prefix}_{i}.pdf'
        doc.save(single_save)

        out_str += f'{single_save}\n{i} {correction}\n\n'
        
        singlepage_file_names.append(single_save)
        print(f'{i+1:3d}/{len(edits):3d}')

    print(f'done. Files written to {output_dir}')
    combined_doc = pymupdf.open(filename)
    ## silly, but I'm not aware of a simpler way
    combined_doc.delete_pages(from_page=0, to_page=combined_doc.page_count-1)
    for single_page in singlepage_file_names:
        single_pdf = pymupdf.open(single_page)
        combined_doc.insert_pdf(single_pdf, annots=True)

    combined_doc_filename = shipPdfFilename(filename, output_dir, unique_ending)
    combined_doc.save(combined_doc_filename)

    print(f"Combined doc saved to {combined_doc_filename}...")
    print("Deleting intermediate PDFs...")
    
    os.system(f"rm {single_fname_prefix}_*.pdf")
    
    with open(f'{Path(output_dir) / Path(filename).stem}_edits_out.txt', 'w') as f:
        f.write(out_str)

        ### <<<

    return 0
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annotpdf_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    corrections, test_info, len_edits = getCorrections(args.annotpdf_filename, args.latex_filename)

    output_dir = 'bbox_drawings'

    drawPrompts(corrections, test_info, args.annotpdf_filename, args.latex_filename)

    logging.info(f"Acquired {len(corrections)} corrections from {len_edits} edits.")        
