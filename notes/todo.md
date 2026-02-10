However, there is still maybe one last step in connecting the complete metadata commands and float environments to the associated markboxes and marked captions
That would be an enhancement if solely markboxes works well enough. As of right now, I'm not doing anything with the dedicated metadata and environment extraction (which is different from the newly added marking of footnotes, captions, and metadata commands).

# main next enhancements
- label standardization
- determining if no rectangle intersects/specified whether to give snippet of preamble to insert a missing metadata like `\datereceived`, `\subjclass`, etc.

## low priority
- screening multi-line annotations (maybe can be done without opencv)
- correctly extracting multi-line annotations with opencv
- extracting line and polygon annotations (may or may not require opencv)



