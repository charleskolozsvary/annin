# `corrinline`
## Usage
`corrinline` is a tool that aids a LaTeX- and PDF-based manuscript correction workflow.[^1] Run 
```shell
corrinline pdf_file latex_file
```
to write annotations from the PDF as comments at their corresponding locations in a new LaTeX file, `[latex_file]_inlined.tex`.

Here's what that looks like
```latex
the left we mean the $\infty$-category of $\mathbb E_1$-algebras %%
%% Correction 6, page 2 [ ]
%% Selection: "in C[W−1]<Replace> ;</Replace> on the"
%% Comment:   ";"
%%
%⭣ ⭣ ⭣ 
in $\mathsf C[\mathsf W^{-1}]~;$ on %%
%⭡ ⭡ ⭡  END of correction 6
the right, we mean the 1-category of monoid objects in $\mathsf C$,
```
A correction index, the page the annotation appears on, the text selected in the PDF by the annotation, and the contents of the annotation text box are all written to the LaTeX file at the corresponding location (delineated by the down and up arrows).[^2] Here's what the PDF that has the annotation looks like.

<img width="1107" height="578" alt="image" src="https://github.com/user-attachments/assets/52c7af9b-0f1b-43f0-be55-83ec2116f1ef"/>

### Autocorrections
There's an option `--auto` which makes `corrinline` carry out whatever corrections it can. Running
```shell
corrinline --auto pdf_file latex_file
```
outputs `_autocorrected.tex` (in addition to the same `_inlined.tex` file from before) which for this example looks like
```latex
the left we mean the $\infty$-category of $\mathbb E_1$-algebras %%
%% Correction 6, page 2 (AUTOCORRECTED) [ ]
%% Selection: "in C[W−1]<Replace> ;</Replace> on the"
%% Comment:   ";"
%%
%⭣ ⭣ ⭣ 
in $\mathsf C[\mathsf W^{-1}];$ on %%
%⭡ ⭡ ⭡  END of correction 6
the right, we mean the 1-category of monoid objects in $\mathsf C$,
```
There are several other options, too, that are discussed in [notes/option_usage.md](notes/option_usage.md). 

Also, the rest of this example and others can be seen in [notes/corrinline_examples.md](notes/corrinline_examples.md).

## Installation
If you don't already have a LaTeX distribution, download the latest version of TeX Live at https://www.tug.org/texlive/.
### Linux/Mac
1. Install pixi (the python package and dependency manager): https://pixi.prefix.dev/latest/installation/
2. Install `diff-pdf` (CL tool for comparing PDFs): https://github.com/vslavik/diff-pdf
3. Clone this repository to your machine
4. Run `./install.sh [corrinline shell script install directory]`, e.g., `./install.sh /usr/local/bin/` at the top-level directory of the cloned repository

Verify it is installed properly with `corrinline -h`. You should see the usage message.
### Windows
No instructions currently.

## Assumptions and limitations
### Unchanged LaTeX
For best results, the LaTeX file should be unchanged since it generated the PDF which contains the annotations. Even relatively small changes could effect pagination and cause a cascade of differences between what the source now renders and the original PDF, which prevents correct mapping from PDF coordinates to positions in the LaTeX source.

If the PDF the LaTeX renders and the annotated PDF are only out of sync up to a certain page, the `--tex-start` option might be of use. It, along with the other options, are discussed in [option_usage.md](notes/option_usage.md).

### Annotations are precise
As shown in [corrinline_examples.md](notes/corrinline_examples.md), the contents of insertion and replacement text are interpreted literally, so correct autocorrections can only happen if the annotations themselves are correct. Additionally, since 'highlight' is too general an annotation, they will never be done automatically. So accurate, dedicated annotations must be used for best results. For more on this, see [notes/annotation_guidelines.md](notes/annotation_guidelines.md).

### Edits aren't specified to roman numeral pages
This should be able to be resolved, but since the mapping technique from the PDF to the LaTeX relies on the page numbers TeX generates and a static PDF doesn't always include the correct page label metadata, `corrinline` cannot currently inline edits to pages that are labelled with roman numerals for their number.

### Incomplete character maps
Complicated math formulas render beautifully with LaTeX, but their character encoding in the PDF is not great. Take for example this LaTeX
```latex
\begin{equation}
X \mapsto \coprod_{n \geq 0} X^{\otimes n}
\end{equation}
```
it looks like 

<img width="375" height="160" alt="image" src="https://github.com/user-attachments/assets/cc949686-8302-44e1-bfd8-8362b996c5b5" />

in the PDF, but extracting the text from that same PDF only gives
```text
X 7→
 a
 X ⊗n
n≥0
```

Ideally, the text would look something like
```text
𝑋 ↦ ∐_{𝑛≥0} 𝑋^{⊗𝑛}
```
There might be a way to do this, but I haven't thought about it much, and it would probably be fairly difficult. Such a problem is pretty well outside the scope of the tool and would be a large independent enhancement.

[^1]: For more about the project's context and motivation, see [notes/about.md](notes/about.md).
[^2]: Recall that a `~` in LaTeX produces a non-breaking space, but spaces aren't written before punctation like a semicolon, so the edit is to close up that space.
