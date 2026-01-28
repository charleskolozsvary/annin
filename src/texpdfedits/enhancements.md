The first two of these are probably the most important

# Intersecting dedicated command word boxes
If we intersect a word box that's in a `\copyrightinfo`, we only return the source that is bounded by the boxes, which is appropriate for the document word boxes, but for the dedicatd commands, this often results in insufficient source to carry out the edit. Ideally, we should just supply the entire command if even one of its boxes is intersected. This won't be hard to do, really, since we already have the name of the dedicated command and the head_count value to track which particular command we've intersected.

There are a number of ways that we could connect the entire dedicated command source to a single intersected box in one of the dedicated commands, really.


# multi-line annotations
Right now the text extraction from the PDF and the the normalization of the annotation rectangle is fine-tuned for single-line selections---avoiding overlaps with other lines and what not. But when a selection is *supposed* to to be multiple lines, we don't really account for that, so the "normalized" selection rectangle will only include one line.

We probably need to revisit the line and text and rectangle structure and information available to us in the dictionary representation of the page text.


# ignored code between macro args
As of right now pylatexenc ignores the contents between macroargs, which functionally is fine, but is not good when reproducing the original file
```latex
\title[short title]
{complete title}
```
Will become
```latex
\title[short title]{complete title}
```
and the individual marked macro node will be ignored.

To get around this, I would need to reinsert what pylatex enc normally ignores between the arguments in some way. It shouldn't be impossible, but
it will require some thought and I'm not sure how often this really will come up, so I'm not going to focus on it right now.

`arxiv1.tex` demonstrates this.


# non-intersecting rectangle in the running head
The default behavior now is to just return the closest document word boxes, which is reasonable, but maybe we could include a kind of hacky check
if we are in the very top of the page, where the running head usually is. The problem with this is that its possible the position of the running head can change.

So ... this is really just a consideration for later.

This lack of detail also effects rectangles which are selecting displayed math ... in a footnote.

We could maybe add a check that we just look at the surrounding document boxes, unless we are already "surrounded" (which we'll have to make precise) by boxes
which are all numbered the same, and in which case we use said boxes.