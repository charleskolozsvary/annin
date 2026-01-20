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