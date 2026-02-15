# texpdfedits
The script provided by this python project, `inlinecorr`, modifies LaTeX source files to aid/automate a correction workflow where copyedits are specified by an annotated PDF.

Normal processing of the changes involves reviewing the PDF and finding and fixing the corresponding LaTeX one annotation at a time. There are tools like SyncTeX to speed up the navigation between output and source, but even then the process is time-consuming and tedious.

`inlinecorr` places the corrections directly into the source LaTeX as comments and carries out whatever corrections it can automatically.

## Installation
If you don't already have a LaTeX distribution, download the latest version of TeX Live at https://www.tug.org/texlive/.
### Linux/Mac
1. Install pixi (the python package and dependency manager): https://pixi.prefix.dev/latest/installation/

2. Install `diff-pdf` (CL tool for comparing PDFs): https://github.com/vslavik/diff-pdf

3. Clone this repo to your machine

4. Run `./install.sh [binary install directory]`, e.g., `./install.sh /usr/local/bin/`

That should be all! You can then run `inlinecorr [annotated PDF file] [tex file]` anywhere on your machine.


## Example output
For example test files, you can try those under [AnnotatedPDFs](./AnnotatedPDFs) with corresponding LaTeX sources in [TeX](./TeX).

Here's part of `arxiv5_inlined.tex`, the output of `inlinecorr arxiv5_ann.pdf arxiv5.tex`:
```latex
%% Correction 28 [ ]
%% Annotated text: "fr−2 given by<Remove>:</Remove>"
%% Comment: "" 
%% 
%% START of correction 28
given by:
\begin{equation}
    \label{eq:GD_hier}
\frac{\partial L}{\partial T_n}=\lambda^{n-1}[(L^{n/r})_+,L],\quad n\geq 1.
\end{equation}

Denote %%
%% END of correction 28
by $L$ the solution of the system specified by the initial %%
%% Correction 29 [ ]
%% Annotated text: "x + λ rrx<Replace>,</Replace>"
%% Comment: "." 
%% 
%% START of correction 29
condition
\begin{equation}\label{eq:init_cond_L}
L|_{T_{\geq 2}=0}=\partial_x^r+\lambda^{-r}rx,
\end{equation}
Witten's %%
%% END of correction 29
```

And here's the same snippet in `arxiv5_autocorrected.tex`, which is outputted when the `--autocorrect` option is present.
```latex
%% Correction 28 (auto) [✓]
%% Annotated text: "fr−2 given by<Remove>:</Remove>"
%% Comment: "" 
%% 
%% START of correction 28
given by
\begin{equation}
    \label{eq:GD_hier}
\frac{\partial L}{\partial T_n}=\lambda^{n-1}[(L^{n/r})_+,L],\quad n\geq 1.
\end{equation}

Denote %%
%% END of correction 28
by $L$ the solution of the system specified by the initial %%
%% Correction 29 (auto) [✓]
%% Annotated text: "x + λ rrx<Replace>,</Replace>"
%% Comment: "." 
%% 
%% START of correction 29
condition
\begin{equation}\label{eq:init_cond_L}
L|_{T_{\geq 2}=0}=\partial_x^r+\lambda^{-r}rx.
\end{equation}
Witten's %%
%% END of correction 29
```

For this particular paper, **260/411 corrections were completed automatically!** 

Finally, here are two pages side by side, one from `arxiv5_ann.pdf`, the other from `arxiv5_autocorrected.pdf`, demonstrating the result of several automatic corrections.

<img width="400" alt="annotated" src="https://github.com/user-attachments/assets/912e4c1d-efb9-4fa4-a404-0ced2869e2c1" />
<img width="400" alt="autocorrected" src="https://github.com/user-attachments/assets/4dcc4ff8-d3e1-4300-9262-3c401e3fd1e5" />

You might notice that one of the automatic corrections resulted in "satisfyit." That happened because the contents of the comment for that correction was just "it" (no space before).

## Assumptions/Limitations
### Unchanged LaTeX
This script assumes that the LaTeX source is unchanged since the original PDF was generated and annotated. If there is any difference (even of a few words) between the current source and what generated the PDF which was annotated, the script will not work.

### Multiline annotations
Also since annotations only have one associated rectangle, multiline annotation rectangles will typically be the convex hull of marked text, so the region information is lost at the line level. It's possible that annotation software will automatically make multiple annotations to get around this, but this behavior is not accounted for currently. The tool will still mark the correct corresponding location in the source, but the annotated text will not correspond to how the text was actually marked.

### Incomplete character mapping
Since text is extracted directly from the PDF for producing the "annotated text" rendered math and other special glyphs will not be translated correctly to the
Unicode text in the PDF. For example, even something relatively simple like `''` in the latex source will produce the unicode character `”`.

A straitforward enhancement would be to specify some of these Unicde to TeX character mappings, but this is not implemented yet.

### Annotations are precise
As shown in the above screenshots, the contents of insertion and replacement text is interpreted literally. Additionally, since 'highlight' is too general an annotation, said annotations will never be done automatically, even if they are used in place of a replacement or strikeout annotation. So dedicated annotations must be used for best results.
