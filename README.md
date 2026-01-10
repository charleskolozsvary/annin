# Package management: pixi
Install pixi following the steps here: https://pixi.prefix.dev/latest/installation/

For my own record, here's what I did to set up the project environment. It's amazing how much simpler Pixi is than conda + poetry.
```shell
pixi init [project name] --format pyproject
pixi add python=3.12
pixi add [conda-forge available package]
pixi add --pypi [only-PyPi available package]
```

Pixi is a conda first manager, so it will import a package from conda-forge before anywhere else. If a package is not available in conda-forge, you can install it from PyPI, the python package index, which has a much lower barrier to entry and therefore many many more packages.

## Other dependencies
[diff-pdf](https://github.com/vslavik/diff-pdf)
pdflatex should be installed from TeX Live. I'm running texlive2023, and I may need to test that earlier distributions work, but I doubt they wont.

# Background and goal
The corrections workflow is to open an annotated pdf which specifies tens or dozens or hundreds of edits to make to the source latex and you work through them one at a time, clicking on the edit comment, seeing what it marks in the pdf, finding the corresonding latex source, and making the change. This, obviously, is very time consuming, and many of the edits are quite straightforward: Insert a comma here, change a period to comma at the end of an equation, make this letter uppercase, etc.

The hope is that such simple edits (and then potentially down the line more complicated ones) can be automated with the use of an LLM. I think there is a genuine use case here because the content of the instructions requires general (though simple) reasoning. It would be very hard to explicitly program the correct change to the comment "runin line with preceding paragraph", for example.

The goal then is to package the necessary information from the annotated pdf and the latex source and send it off to an LLM, which will output typically small individual edits which will then need to be composed and applied to the original latex source.

Currently sizable progress has been made in packaging the information that is to be sent to the LLM.
Information in the annotated PDF is extracted by extract.py, and segmentsource.py provides the extraction of the latex source from rectangles in the PDF. `prompt.py` leverages these two scripts to create the individual (markdown) prompts which will be sent to the LLM. No special effort has yet been made toward refining the prompts, but here's a current example of one automatically generated prompt:

--------------


## Type
Highlight

## Comment
```text
COMP: insert comma at end of equation
```

## PDF selected text
```text
<Highlight>Q[u, c1, . . . , ck]</Highlight>
```
  
## LaTeX source
```latex
we have
	\begin{equation}\label{Cohomology of H_times}
		H_{\times}^* := H^*(\mathbb{S}^m \times \mathbb{CG}_{n,k}; \mathbb{Q}) \cong H^*(\mathbb{S}^m; \mathbb{Q}) \otimes H^*(\mathbb{CG}_{n,k}; \mathbb{Q}) \cong \frac{\mathbb{Q}[u, c_1, \dots, c_k]}{\langle u^2, h_{n-k+1}, \dots, h_n \rangle}
	\end{equation}
	where 
```

--------------

And here's the response Gemini 3 Flash gave with minimal context (just "here's an edit: output the verbatim edited latex as a markdown codeblock and nothing else"):

```latex
we have
	\begin{equation}\label{Cohomology of H_times}
		H_{\times}^* := H^*(\mathbb{S}^m \times \mathbb{CG}_{n,k}; \mathbb{Q}) \cong H^*(\mathbb{S}^m; \mathbb{Q}) \otimes H^*(\mathbb{CG}_{n,k}; \mathbb{Q}) \cong \frac{\mathbb{Q}[u, c_1, \dots, c_k]}{\langle u^2, h_{n-k+1}, \dots, h_n \rangle},
	\end{equation}
	where 

```

From my simple testing so far of manually quererying LLMs with prompts like these, the results are fairly promising, especially given how little context I've provided for carrying out the edits. Of course there are many current limitations which make this project very removed from being production-ready, but I think the basic potential is made clear. And I think the limitations can eventually be addressed with more dedicated information retrieval and improved prompting.

An overview of what still needs to be implemented is included below in very roughly decreasing importance.

# Future work
As mentioned above, the project in it's current state mostly demonstrates the potential of automating corrections, but there are a number of critical
components which still need to be addressed for the goal to be accomplished robustly.

## Resolving source update conflicts
The current plan is to give individual prompts to fix each edits (we can maybe expand the scope and give multiple edits at a time later), and this works well when the edits don't overlap. But if there are two edits on the same line of the PDF, the same underlying source will be changed both times, and naively composing the changes would result in a conflict.

Off the top of my head, I see two approaches to this:
(1) cleverly process the conflict resolution
(2) update the source with each edit

(2) seems like the way to go, though it could have a downside of introducing drift between the PDF selection text and the latex source, but maybe that won't actually be an issue. But I haven't spent a lot of time thinking about this issue in general, so it's not worth speculating further right now. 

## Insufficient context
One major limitation right now is when the local latex source around an edit doesn't actually contain what needs to be changed. Like when an item in an enumerate is highlighted and the local source LaTeX extracted doesn't include the `\begin{enumerate}`.

## Identifying edits which should be ignored
Often edits will start with AU: or PE: (for the author or production editor) or will ultimately address someone who is not the current compositor of the corrections. I.e., the edit is not to be acted upon. These should not be hard to identify one way or another, but it still has to be done, so I write it here.

## Dedicated metadata, bibliography, and float processing
Right now the source extraction excells when the comment is in the normal body of the document. But when an edit asks to change something
whose source lives in a metadata command like `\author` or is in a float caption, there's no special handling for those cases and rectangleToLatex will likely fail.

It also looks like source in the bibliography is not getting extracted as consistantly as I would hope.

But thankfully these elements are themselves very specific in form and contained, so I think I can do dedicated processing for them which will work well enough.

## Multi-line selections
When an annotation selects text on more than one line, it's bounding box encompases all lines of selected text, no longer just the marked text (as it would be
if the text selected belonged to just one line).

To handle these cases I would need to
1. Identify highlight, strikeout, or other multi-select annotations whose bounding boxes include more than one line. (with pymupdf)
2. determine the bounding boxes of the actual annotation visual 

From what I can tell, the PDF does not contain the information necessary to determine (2). There's only one bounding box for an annotation and it is incorrect as discussed. It would not be extremely difficult to use some computer vision approach, even if it feels heavy handed. I'll probably use opencv for this when I get around to it.

## Label and reference standardization
As of now, edits which ask to "link" cannot be completed because I'm not keeping track of the labelled elements and what numbers correspond to them.
An approach similar to what I've done with annotate counters could work, but it's worth stepping back and reflecting on what the right way to tackle this would be.
I'm tempted to standardize the labelling scheme entirely in the document, but again, I'll have to think about this more.

