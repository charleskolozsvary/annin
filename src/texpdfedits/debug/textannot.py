import pymupdf
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf_file')
    args = parser.parse_args()

    pdf_file = Path(args.pdf_file)
    global doc
    doc = pymupdf.open(pdf_file)

    while True:
        command = input()
        if command.startswith('list'):
            parts = command.split(' ')
            if len(parts) > 1:
                pageno = int(parts[-1])
            else:
                pageno = 0
            list_xrefs(pageno)
        elif command.startswith('pr'):
            xref = command.split(' ')[-1]
            print_xref(int(xref))
        elif command == 'q':
            quit()

def list_xrefs(pageno: int=0):
    global doc
    page = doc[pageno]
    print('\n'.join(str((xref, type)) for xref, type, name in page.annot_xrefs()))

def print_xref(xref: int):
    global doc
    print(doc.xref_object(xref))


