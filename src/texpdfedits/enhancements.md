# extract 
## Multi-line annotations
`getSelection()` in `extract.py` does best when the annotation selects text limited to one line. As soon as it selects more than one line it performs poorly.

We could still probably improve the behavior when there are multiple lines, though, without trying to do processing to get the real annotation selection bounds.
We just need to add some logic to put the ending HTML-like tag after the last intersected word even if that word is not on the boundary of the annotation rectangle; and the same goes for the starting word and inserting a starting tag.

We need to overall do more testing about the behavior of `getSelection()` when the rectangle spanns multiple lines.

## Other low priority enhancements
- Use opencv to identify the selections for multi-line annotations
- Extract equations images to eventually pass to the LLM (need to research)

# segmentsource
## Intersecting dedicated command word boxes
If we intersect a word box that's in a `\copyrightinfo`, we only return the source that is bounded by the boxes, which is appropriate for the document word boxes, but not for the dedicatd commands, since this often results in insufficient source to carry out the edit. Ideally, we should just supply the entire command if even one of its boxes is intersected (though maybe not if the entire command source is longer than some threshold of characters).

I think the simplest way to do this is to make note of the position when inserting the marks, since we have access to the positions from the pylatexenc parser and we also know the counter information---specifically we know the head value of the macro, so that will be enough to get the direct link.

## Standardizing labels and references
It would be nice if we could have all numbered elements' labels reflect the numbering. So the label to `Lemma 5.9` would be `\label{lem:5.9}`. We could do a convention like `<Name of numbered element with label> <number>` will get label `\label{<first k letters of name>:<number>}`. Off the top of my head I don't see how this could be problematic. The simple approach would be to insert `\typeout` commands after a numbered element like I do in `annotatecounters` (which would be better named addcountercomms) and then look at each `\label` and see the earliest numbered element that comes before it which has `\typeout` information for it written.

Then we just rename that particular label and all instances of said label when passed to `\ref`, `\cref`, `\Cref`, etc. I guess this is where it gets a little hairy because there are many different commands which accept a label key and if the original label key is very simple, it won't be easy to identify it.

Yeah unfortunately an author could do something as simple as
```latex
\newcommand{\leqref}[1]{\stackrel{\leq}{\eqref{#1}}}
```

I guess you could *attempt* to address this by
(1) have a more or less exhaustive list of macros which receive label keys (`\ref`, `\eqref`, `\autoref`, `\cref`, `\Cref`, etc.)
(2) scan all user-defined macro replacement text and add the ones which have a macro in (1) to the list
(3) repeat (2) until the lengthened (1) list (really a set) doesn't change size
(4) replace all identified `\label` arguments changed when they appear as an argument to any of the macros in the lengthened (1) list

That *seems* like it should actually work. Well one "counter example" could be if a label key is a delimited parameter to a `\def`, but if (4) accounts for delimited macro parameters then it isn't an issue, of course. Also I thankfully don't recall encountering delimited macro parameters very often at all.



## Ignored code between macro args
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

## Build correspondence between PDF and segmentsource word boxes
We can extract individual word boxes with pymupdf and we of course create our own, so we should be able to create some kind of correspondence between the two which could help in a number of ways. But what constitutes a 'word' in either case is somewhat different, so we would either need to change segmentsource to usually resemble the pymupdf word boxes or accept that there will be some differences and account for them.

One of the problems this could fix is identifying segmentsource word boxes which break across a line (and whose positional information just goes off past the margin).

# prompt
## rectangleToLatex
### Non-intersecting rectangleToLatex()
The default behavior of `rectangleToLatex` when no marked word boxes are intersected is to return the code between the previous and next document word boxes, which works well when the non-intersecting rectangle is in the body of the page, but not otherwise.

We could be in the running head or in displaymath in a footnote, for example.

We could maybe address the first case with a hacky check to see if we are above the top margin where the running head usually is. But the top and bottom margins might be journal dependent, so, again, it's hacky and low-priority.

As for non-intersecting boxes in a caption or footnote or thanks, this might have a reasonable workaround by using the proximity of marked rectangles.

This would also become much easier to address if we build up a correspondence between the PDF word boxes and the boxes we create through macro insertion in segmentsource.

## Screening responses
Need to reflect on whether there is a way to identify good and bad responses from the LLM---it's also possible that we could cut out the LLM entirely.