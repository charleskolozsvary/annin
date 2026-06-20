# About `annin` 
## Context 
The American Mathematical Society is a nonprofit which, among many other things, publishes a great number of books and journals in mathematics. The AMS is also perhaps unique in that it uses LaTeX all throughout its production process. This is in part because LaTeX is the typesetting program of choice in the mathematics community and also because the AMS has been involved in the development of LaTeX for a long time. 

Everything the AMS publishes goes through several production stages. One of the crucial but more tedious ones is copy editing. The established workflow is that a copy or production editor will annotate a PDF of the rendered LaTeX source, then someone else will read through those annotations and compose the changes directly to the LaTeX. Broken down, composing those changes involves the following (at some point) for every individual annotation (which corresponds to some edit).

1. Read the annotation in the PDF 
2. Find the LaTeX source code that corresponds to it 
3. Make the requested change 
4. Recompile the source and verify the PDF renders as intended.

The most time-consuming step is 2. (maybe also 4.) for simple edits, so the workflow is improved if all the annotations and where they needed to be done were contained to just the LaTeX file. And that (for the most part) is exactly what `annin` does: as its name is supposed to suggest, it **inlines** the **annotations** from the PDF straight into the LaTeX. 

## Challenges
To inline annotations from a PDF into a LaTeX file, there are a few problems that need to be solved
1. Extract the annotations (including chains of replies and selected text) from the PDF
2. Map the PDF coordinates to positions in the LaTeX source
3. Modify the original LaTeX without affecting the output it renders

Problems 1. and 3. are relatively straightforward.[^1] The major challenge is 2., and there actually exists a dedicated program for it called [SyncTeX](https://www.tug.org/TUGboat/tb29-3/tb93laurens.pdf). However, during the early development of the project, I struggled to find its documentation and get working with it, so I implemented my own solution using a Python LaTeX parser called [`pylatexenc`](https://pylatexenc.readthedocs.io/en/latest/).

SyncTeX is now incorporated on the development branch, but it's not ready to be merged---there are still some kinks to work out.

[^1]: Extracting information from the PDF is not a big deal at all with the help from a powerful PDF library, [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/).
