arxiv6 uses amsrefs---it will be a good test case later on.

<s>Check if pylatexenc handles `\newenvironment` alright. It fails on `\newcommand{\be}{\begin{equation}}`<s>
pylatexenc generally struggles with oddly nested environments, but I've added `\startignorepylatexenc` and `\endignorepylatexenc` as last resorts.

Also added as a last resort is the `-emen` or `--extra-marked-environment-names` option to `test_segmentsource.py` which in the case of
arxiv14.tex is used like this: `python test_segment.py ../TeX/arxiv14/arxiv14.tex -emen='prf*,prt,rqm'`

<s>Need to add progress output to extract.py and investigate its runtime. It takes a few moments when there are hundreds of annotations which might be unavoidable, but still.</s> Done.


The next paper I'll annotate will be arxiv5. It has figures, footnotes, and subcaption figures, too. I might update their address and email to use the correct coding (which would already have been done during cleanup).
