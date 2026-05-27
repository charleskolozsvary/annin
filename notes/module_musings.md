# Module musings
I'll write about my thought process for certain functions or more broadly modules here. Really this should be actual documentation, but it's not nearly clear or precise enough.
## `extract.py`
### `Class Edit`
```python
    """
    Represents the information necessary to carry out an edit.
    An edit has the following attributes:
    
    "pageno": the page number the PDF annotation appears on 
    
    "type": annotation type (same as in Annot)
    
    "message": text in the annotation comment box and responses to it
        it is a dict where
        message['comment'] = str of original comment in comment box
        message['responses'] = list[str] of responses in order of creation date
    
    "selection": selected and surrounding text of the annotation from the PDF.

    Example
    {
      "pageno" : 1, 
      "type" : "Replace" 
      "message": {
                   "comment": "Theorem 3.14", 
                   "responses": ["COMP: pls link"]
                 }
      "selection": "We now prove the <Replace>following theorem</Replace>."
    }

    """
```
### `getRobustAnnots`
```python
    """
    pymupdf's annotations are kind of fragile---they are
    strongly bound to the page they come from (so when
    the page goes away, so does the annotation), and I've
    encountered issues with using the provided methods
    to update annotation attributes, so I'll just store the
    annotations with my own class which isn't tied to the page.
    """

    # Previously, the x positions of the annotations have been
    # accurate, but now I'm encountering annotations from another
    # tool whose left and right x coordinates are significantly
    # wider than the actual selected text.
    #
    # For now, I'm trying this very hacky and extremely simple
    # and specific response where I just remove a flat ammount
    # from either side. I need to investigate where this
    # discrepancy comes from, but but this has been working
    # surprisingly well so far.
    #
    # But this hack only works (if therere's a problem to begin
    # with and) if the font is cmr10 (or maybe 11 or 12,
    # I don't recall)
```
## `sync.py`
### `improve_synctex_line`

SyncTeX is pretty great. However, the lines it gives are not always representative of all the source that would be nice to identify.

We could stop identifying the start and end of the correction (or, in other words, the LaTeX snippet contained to the correction) and be content to just insert a comment near what needs to be corrected, but that seems to be a very helpful idea, so we can try to ehance the lines that SyncTeX provides instead of discarding it because of the cases where the given SyncTeX line doesn't work well. What are those cases? Well, they're not for normal text in the body. Those are almost always picked out well.

The kinds of text which don't get sent to a line number that nicely meets the criterion of "this is all the LaTeX relevant for the correction" are those inside footnotes or captions or those inside display math (and probably other environments) or the bibliography. 

Take for example the result of the default line selection in this bibliography:
```latex
\bibitem[Car85]{Carter85}
R.\,W. Carter, \emph{Finite groups of Lie type. Conjugacy classes
and complex characters}, Pure Appl. Math. (N. Y.) Wiley-Intersci.
Publ. John Wiley \& Sons, Inc., New York, 1985.
 %%
%% Correction 49, page 10 [ ]
%% Highlight: "of Lie type. Conjugacy <SEL>c</SEL>lasses and complex characters,"
%% Comment:   "C"
%%
%% Correction 50, page 10 [ ]
%% Highlight: "type. Conjugacy classes and <SEL>complex characters</SEL>, Pure Appl. Math."
%% Comment:   "uppercase first letter of each word"
%%
%⭣ ⭣ ⭣ 
%%
%⭡ ⭡ ⭡  END of corrections 48, 49
```
It got the right `\bibitem` 100% but it's at the *end* of it. The same thing happens for a `\footnote` or `\caption`. This is a completely reasonable line to choose, granted. I don't want to give the impression that SyncTeX is doing anything I wouldn't want it to. It, from what I can tell, rather predictably goes to the end of relevant macros or environments. So it's just a matter of harnesing that good predictable behavior to segment off a region of the LaTeX which "belongs" to the correction.

Enough preamble,  here's the idea.

Look at the source from the previous ten lines up to the given line.

Parse it with pylatexenc. Look for certain macros including those in `SYNC_MINDFUL_MACROS`.

For some of these, e.g., \footnote, if the argument of the macro ends on the line given by synctex, include up to the line number that starts the macro.

For others like \bibitem, simply use the line of the nearest macro (before).

There are also certain environments or displayed math where we look for the earliest (looking up) start of an environment for the line number that begins the snippet.
