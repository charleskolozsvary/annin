# update rectangleToLatex
Use the new nested marking system in `prompt.py`

If only document boxes are intersected, nothing new needs to be done: Look up the box before the earliest intersection and the box after the latest intersection.

If all the boxes intersected are nested the same, nothing new really needs to be done: use the box before the earliest intersection and the box after the latest intersection at the furthest level of nesting.

If the intersecting boxes are at different levels of nesting I can't extract the latex. Or at least I don't see why it would be useful. Most likely the rectangle is not reasonable.

Different levels would also mean that the head values are different so 'DOCUMENT0;0,FOOTNOTE0;0' and 'DOCUMENT0;0,FOOTNOTE1;0' are different

If I don't intersect anything, I just look at the earliest document box before the rectangle and the next document box after the rectangle.

So really the only important thing for me to figure out is if a list of intersecting boxes are really "together"

The requirement is that they all are nested the same and the deepest counter has the same head. So all of the parent counters are equal and the deepest counter
head is the same. And then we positioning given by the stem_count of the deepest counter.

# review gemini 3 flash output on arxiv13_ann.pdf
With the improved source marking, I don't need to worry about edits to footnotes, captions, etc.

However, there is still maybe one last step in connecting the complete metadata commands and float environments to the associated markboxes and marked captions
That would be an enhancement if solely markboxes works well enough. As of right now, I'm not doing anything with the dedicated metadata and environment extraction (which is different from the newly added marking of footnotes, captions, and metadata commands).

# make changes to source based on LLM changes
This is the last step before we get a completely closed loop program. Exciting!

# main next enhancements
- label standardization
- determining if no rectangle intersects/specified whether to give snippet of preamble to insert a missing metadata like `\datereceived`, `\subjclass`, etc.
- screening multi-line annotations (maybe can be done without opencv)
- correctly extracting multi-line annotations with opencv
- extracting line and polygon annotations (may or may not require opencv)



