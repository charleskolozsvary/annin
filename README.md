# texpdfedits
This goal of this python project is to modify LaTeX source files to aid/automate a correction workflow where copyedits are provided by an annotated PDF.

Normal processing of the changes involves reviewing the PDF and finding and fixing the corresponding LaTeX one annotation at a time. There are tools like SyncTeX to speed up the navigation between output and source, but even then the process is time-consuming and tedious.

The script this project provides, called `inlinecorr`, places the corrections directly into the source LaTeX as comments and carries out whatever corrections it can automatically. See [annotation_guidelines.md](notes/annotation_guidelines.md) for more on the autocorrections.

## Installation
If you don't already have a LaTeX distribution, download the latest version of TeX Live at https://www.tug.org/texlive/.
### Linux/Mac
1. Install pixi (the python package and dependency manager): https://pixi.prefix.dev/latest/installation/

2. Install `diff-pdf` (CL tool for comparing PDFs): https://github.com/vslavik/diff-pdf

3. Clone this repo to your machine

4. Run `./install.sh [binary install directory]`, e.g., `./install.sh /usr/local/bin/`

That should be all! You can then run `inlinecorr [annotated PDF file] [tex file]` anywhere on the machine.


## Examples
For example test files, you can try those under [AnnotatedPDFs](./AnnotatedPDFs) with corresponding LaTeX sources in [TeX](./TeX).

Here's part of `arxiv5_inlined.tex`, the output of `inlinecorr arxiv5_ann.pdf arxiv5.tex`:
```latex
%% Correction 23 [ ]
%% Annotated text: "non-commutative associative algebra<Remove>,</Remove> in which"
%% Comment: "" 
%% 
%% START of correction 23
associative algebra, in %%
%% END of correction 23
which the multiplication $\circ$ is induced from the usual product on $\C[\lambda,\lambda^{-1}][[T_1,T_2,\ldots]]$ and 
\[
\d_x^k\circ f:=\sum_{l=0}^\infty\frac{k(k-1)\ldots(k-l+1)}{l!}\frac{\d^lf}{\d x^l}\d_x^{k-l},
\]
where $k$ is an integer, $f\in\mathbb C[\lambda,\lambda^{-1}][[T_*]]$, and the variable $x$ is identified with $T_1$. Let $r\geq 2$ be %%
%% Correction 24 [ ]
%% Annotated text: "be any integer<Remove>,</Remove> and A"
%% Comment: "" 
%% 
%% START of correction 24
any integer, and %%
%% END of correction 24
$A$ a pseudo-differential operator of the form
\[
A=\partial_x^r+\sum_{n=1}^\infty a_n\partial_x^{r-n},
\]
then $A$ has a unique $r$th root, meaning a unique pseudo-differential operator $A^{\frac{1}{r}}$ of the %%
%% Correction 25 [ ]
%% Annotated text: "<Replace>satisfying</Replace> A 1"
%% Comment: "satisfies" 
%% 
%% START of correction 25
form
\[
A^{\frac{1}{r}}=\partial_x+\sum_{n=0}^\infty b_n\partial_x^{-n}
\]
satisfying $\left(A^{\frac{1}{r}}\right)^r=A$%%
%% END of correction 25
```

And here's the same snippet in `arxiv5_autocorrected.tex`, which is outputted when the `--autocorrect` option is present.
```latex
%% Correction 23 (auto) [✓]
%% Annotated text: "non-commutative associative algebra<Remove>,</Remove> in which"
%% Comment: "" 
%% 
%% START of correction 23
associative algebra in %%
%% END of correction 23
which the multiplication $\circ$ is induced from the usual product on $\C[\lambda,\lambda^{-1}][[T_1,T_2,\ldots]]$ and 
\[
\d_x^k\circ f:=\sum_{l=0}^\infty\frac{k(k-1)\ldots(k-l+1)}{l!}\frac{\d^lf}{\d x^l}\d_x^{k-l},
\]
where $k$ is an integer, $f\in\mathbb C[\lambda,\lambda^{-1}][[T_*]]$, and the variable $x$ is identified with $T_1$. Let $r\geq 2$ be %%
%% Correction 24 (auto) [✓]
%% Annotated text: "be any integer<Remove>,</Remove> and A"
%% Comment: "" 
%% 
%% START of correction 24
any integer and %%
%% END of correction 24
$A$ a pseudo-differential operator of the form
\[
A=\partial_x^r+\sum_{n=1}^\infty a_n\partial_x^{r-n},
\]
then $A$ has a unique $r$th root, meaning a unique pseudo-differential operator $A^{\frac{1}{r}}$ of the %%
%% Correction 25 (auto) [✓]
%% Annotated text: "<Replace>satisfying</Replace> A 1"
%% Comment: "satisfies" 
%% 
%% START of correction 25
form
\[
A^{\frac{1}{r}}=\partial_x+\sum_{n=0}^\infty b_n\partial_x^{-n}
\]
satisfies $\left(A^{\frac{1}{r}}\right)^r=A$%%
%% END of correction 25
```

For this particular paper, 260/411 corrections were completed automatically. 


## Limitations
This script assumes that the LaTeX source is unchanged since the original PDF was generated and annotated. If there is any difference (even of a few words) between the current source and what generated the PDF which was annotated, the script will not work.

Also since annotations only have one associated rectangle, multiline annotation rectangles will typically be the convex hull of marked text, so the region information is lost at the line level. It's possible that annotation software will automatically make multiple annotations to get around this, but this behavior is not accounted for currently. The tool will still mark the correct corresponding location in the source, but the annotated text will not correspond to how the text was actually marked.

Since text is extracted directly from the PDF for producing the "annotated text" rendered math and other special glyphs will not be translated correctly to the
Unicode text in the PDF. For example, even something relatively simple like `''` in the latex source will produce the unicode character `”`.

A straitforward enhancement would be to provide some of these Unicde to TeX mapps, but this is not implemented yet.






