# run this script with annin's version of python (i.e., pixi run python3 while in /ams/texmf/github/annin/) e.g.,
# for i in NEW*.pdf; do pixi run python3 show_revision.py "$i"; done 
# should show "12345" four times

import sys
from pathlib import Path
import pymupdf
import re

import sys

pdf_file = Path(sys.argv[1])

doc = pymupdf.open(pdf_file)

trailer = doc.pdf_trailer()

info_key = "/Info"

m = re.search(rf"{info_key}\s+(?P<xref>\d+)", trailer)

if not m:
    raise RuntimeError(f"Could not find {info_key} in {pdf_file}'s pdf_trailer:\n{trailer}")

info_xref = int(m.group('xref'))

_, revision = doc.xref_get_key(info_xref, "AMS_SVN_REVISION")

print(revision)
    
