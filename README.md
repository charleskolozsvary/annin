# `annin`
## Usage
`annin` is a tool that aids a LaTeX- and PDF-based manuscript correction workflow.[^1] Run 
```shell
annin pdf_file latex_file
```
to write annotations from the PDF as comments at their corresponding locations in a new LaTeX file, `[latex_file]_inlined.tex`.

Here's an example PDF annotation

<img width="1076" height="121" alt="image" src="https://github.com/user-attachments/assets/ceee8317-870b-4f89-987c-a85b57ddf616" />

And this is how its information is written to the LaTeX
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
A general index, the page the annotation appears on, the text selected in the PDF by the annotation, and the contents of the annotation text box are all written to the LaTeX file at the corresponding location (delineated by the down and up arrows).[^2]

### Autocorrections
`annin` tries to automatically carry out three types of annotations if the `--auto` option is supplied
1. Replace
2. Strikeout (remove)
3. Insert (caret)

Running
```shell
annin --auto pdf_file latex_file
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

<!-- There are several other options, too, that are discussed in [notes/option_usage.md](notes/option_usage.md).  -->

<!-- Also, the rest of this example and others can be seen in [notes/annin_examples.md](notes/annin_examples.md). -->

## Installation
If you don't already have a LaTeX distribution, download the latest version of TeX Live at https://www.tug.org/texlive/.
### Linux/Mac
1. Install pixi (the python package and dependency manager): https://pixi.prefix.dev/latest/installation/
2. Install `diff-pdf` (CL tool for comparing PDFs): https://github.com/vslavik/diff-pdf
3. Clone this repository to your machine
4. Run `./install.sh [annin shell script install directory]`, e.g., `./install.sh /usr/local/bin/` at the top-level directory of the cloned repository

Verify it is installed properly with `annin -h`. You should see the usage message.
### Windows
No instructions currently.

## Assumptions and limitations
### Unchanged LaTeX
For the tool to work as intended, the LaTeX file should be unchanged since it generated the PDF which was then annotated. Even relatively small changes could effect pagination and cause a cascade of differences between what the source now renders and the original PDF, which prevents correct mapping from PDF coordinates to positions in the LaTeX source.

If the PDF the current LaTeX generates and the annotated PDF are only out of sync up to a certain page, the `--tex-start` option might be of use. It, along with the other options, are discussed in [option_usage.md](notes/option_usage.md) (incomplete).

### Annotations are precise
As shown in [annin_examples.md](notes/annin_examples.md), the contents of insertion and replacement text are interpreted literally, so correct autocorrections can only happen if the annotations themselves are correct. Additionally, since 'highlight' is too general an annotation, they will never be done automatically. So accurate, dedicated annotations must be used for best results. For more on this, see [notes/annotation_guidelines.md](notes/annotation_guidelines.md).

<!-- ### Annotated PDF has correct page label metadata (if there are roman numeral pages) -->

<!-- ### Edits aren't specified to roman numeral pages -->
<!-- This should be able to be resolved, but since the mapping technique from the PDF to the LaTeX relies on the page numbers TeX generates and a static PDF doesn't always include the correct page label metadata, `annin` cannot currently inline edits to pages that are labelled with roman numerals for their number. -->

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
