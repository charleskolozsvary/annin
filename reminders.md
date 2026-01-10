arxiv6 uses amsrefs---it will be a good test case later on.

Check if pylatexenc handles `\newenvironment` alright. It fails on `\newcommand{\be}{\begin{equation}}`

Need to add progress output to extract.py and investigate its runtime. It takes a few moments when there are hundreds of annotations which might be unavoidable, but still.