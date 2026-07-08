import pymupdf
import argparse
from pathlib import Path

pdf_file = 'statuses_gsm.pdf'
doc = pymupdf.open(pdf_file)

def list_xrefs(pageno: int=0):
    global doc
    page = doc[pageno]
    print('\n'.join(str((xref, type)) for xref, type, name in page.annot_xrefs()))

def print_xref(xref: int):
    global doc
    print(doc.xref_object(xref))


