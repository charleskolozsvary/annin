import logging
import argparse
import pymupdf
from texpdfedits.extract import getEdits, Edit
from texpdfedits.segmentsource import segment, rectangleToLatex

from pathlib import Path

def markdownReplies(replies: list[str]):
    if not replies:
        return ''
    output = '\n\n## Replies '
    for i in range(len(replies)):
        output += f'\n\n### Reply {i+1}\n```text\n{replies[i]}\n```'
    return output

def getPrompts(annot_filename: str, latex_filename: str, write_prompts_md = True):
    edits = getEdits(annot_filename)
    num_boxes, marked_tex, document_word_boxes, all_metadata = segment(latex_filename)

    prompts_filename = f"prompts_{Path(latex_filename).stem}.md"

    prompts = []
    test_info = []
    for edit in edits:
        pageno = edit.pageno
        if pageno not in document_word_boxes:
            logging.warning(f"Page '{pageno}' not in document_word_boxes for edit {edit}")
            continue
        ann_line_rect = edit.ann_line_rect
        latex_source = rectangleToLatex(pageno, ann_line_rect, document_word_boxes, marked_tex)
        if latex_source is None:
            logging.warning(f"Could not extract LaTeX for edit {edit}")
            continue

        test_info.append({'page' : pageno,
                           'selection_bbs' : edit.selection_bbs,
                           'ann_line_rect' : ann_line_rect})
        
        replies = markdownReplies(edit.message['responses'])

        prompts.append(
            fr"""
## Type
{edit.type}

## Comment
```text
{edit.message['comment']}
```{replies}

## PDF selected text
```text
{edit.selection}
```
  
## LaTeX source
```latex
{latex_source}
```

--------------

""")

    if write_prompts_md:
        prompt_dir = Path('markdown_prompts')
        Path.mkdir(prompt_dir, exist_ok=True)
        prompt_savefile = prompt_dir / prompts_filename
        with open(prompt_savefile, 'w') as f:
            f.write(''.join(prompts))

        logging.info(f"The list of prompts have been written to {prompt_savefile}.")

    logging.info(f"Produced {len(prompts)} prompts from {len(edits)} edit annotations.")        


    return prompts, test_info, len(edits)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annot_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    prompts, test_info, len_edits = getPrompts(args.annot_filename, args.latex_filename)
