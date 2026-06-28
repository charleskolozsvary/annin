import logging
logger = logging.getLogger(__name__)
import pymupdf

class Annot():
    def __init__(self, doc: pymupdf.Document, page: pymupdf.Page, xref: int):
        

class Document():
    def __init__(self, pdf_file: str | Path):
        self.doc = pymupdf.open(pdf_file)
        
