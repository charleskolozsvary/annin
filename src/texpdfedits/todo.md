# segmentsource
A better name for this script might be linksource

## dedicated marked macro linking
If there's a word box which comes from a marked macro, find the entire corresponding instance of the control sequence whose contents contains the marked box.
E.g., if there's a marked box with ID DOCUMENT0;584,FOOTNOTE6;0 then we should be able to access the entire `\footnote{<contents>}` where the mark ID is in the contents. We need to return the start and end positions of said constrol sequence in the original source file (character positions).

# extract
A better name for this script might be extractanns

## low priority enhancements
- Use opencv to identify the selections for multi-line annotations
- Extract equations images to eventually pass to the LLM (need to research)

# prompt
A better name for this script might be compilecorrs

## Identify corrections which don't need AI help
There are actually a good handful of the simplest kind of corrections like this one, for example, from arxiv5 which gemini-3-flash-preview actually failed on.

## 67

### Annotation: Replace

### Comment
```text
.)
```

### PDF selected text
```text
0 TRR<Replace>)</Replace> Suppose
```
  
### LaTeX snippet
```latex
$g=0$ TRR) Suppose
```
### Response
```latex
$g=0$ TRR) Suppose
```

-----------



## rectangleToLatex
use dedicated marked macro linking from segment source