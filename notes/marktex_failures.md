segmentsource.py fails if a `\textit{...}`'s contents include a displayed equation, `\[\]`. Which really shouldn't happen, but anyway.... This came up when origianlly running on arxiv2.

Just a reminder: segmentsource assumes the contents are flattened (no external latex) which they should be since the papers are already cleaned....

Also: if the height of a box is zero we can't draw it with pymupdf obviously, but I don't think it will actually cause an issue with rectangleToLatex. Source: arxiv4, `$\smash{\widehat{\mathbf S}^c}$`.


Something like
```latex
\newcommand{\be}{\begin{equation}}
\newcommand{\ee}{\end{equation}}

\newcommand{\bes}{\begin{equation*}}
\newcommand{\ees}{\end{equation*}}
```
in the preamble breaks pylatex enc. But this also shouldn't be an issue (it is dealt with by normalizetex).

Also something like
```latex
\leavevmode\vrule height 2pt depth -1.6pt width 23pt,
```
will break segment source because it wraps the arguments to the `\vrule` in a `\markbox`, but again, these shouldn't be in the source at all under normal circumstances. This came up in arxiv7