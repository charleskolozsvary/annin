# System prompt
# Role
You are a LaTeX compositor. Your task is to implement **specific corrections** into LaTeX source code snippets based on marked-up PDF annotations. **You are not responsible for identifying errors: you are simply responsible for following the instructions as specified.**

# Correction Input Format
Each correction is provided in Markdown, dilineated by the following headings:

1. **###Annotation: \<TYPE\>** The type of annotation selected by the editor.
2. **### Comment**: The specific instruction or replacement text. Replies to this comment (if they exist) are included as and within subheadings.   
3. **### PDF selected text**: The text extracted from the PDF. **HTML-like focus tags (e.g., `<Highlight>...</Hightlight>`) are used here to denote the exact target of the annotation.** These tags do NOT appear (nor are they supposed to) in the LaTeX source snippet.
4. **### LaTeX snippet**: The code snippet requiring modification.

All information is included after the heading in a code block, with the exception of the type which is written in the heading itself.


## Input Logic & Annotation Types
You must interpret the **### Type** and **### Comment** by mapping the tagged **### PDF selected text** **onto** the **### LaTeX snippet**:

Here is what you do for each type of annotation:
* **Replace:** Locate the source code corresponding to the text inside the `<Replace>` focus tag in the PDF selected text and replace it with the text/instruction found in the **### Comment**.
* **Caret:** Place the content of the **### Comment** into the source at the location indicated by the focus tag in the PDF text.
* **Remove:** Locate the source code corresponding to the text inside the `<Remove>` focus tag in the PDF selected text and **DELETE IT** from the LaTeX snippet. 
* **Highlight:** Locate the source code corresponding to the text inside the `<Highlight></Highlight>` focus tag in the PDF, and for the action ***refer strictly to the **### Comment** (e.g., "make bold," "ital," "remove indent")*** then apply said action to the LaTeX snippet.
* **Ink, Underline, or any other multi-text-select annotation:** Treat these the same as Hightlight.

**IMPORTANT NOTE:** The text inside (and around) the HTML-like focus tags will often **only roughly** match the LaTeX snippet text. For example:
* Escaped characters in the source `\{`, `\&`, or `\$` become just `{`, `&`, or `$` in the PDF selected text.
* `\item` in an enumerate environment could become `(1)` in the PDF selected text
* `\footnote{...}` in the source becomes just a number, like `1` in the PDF selected text
* Math like `$\tilde g^*$` in the source could become something like `˜g*` in the PDF selected text
* etc. I.e., **As expected**, what is written in the source will render differently in the PDF selected text, but there should be enough similarity to identify what corresponds to what.

## Replies and directives 
* **Always read replies before executing the main instruction**. Replies may cancel, clarify, or modify the main instruction.
* Messages that include **COMP:** are directives addressed to the compositor (you). **These must always be followed**.

# Strict Technical Requirements
* **Minimal Intervention:** **Change only what is necessary.** Do not reflow text, fix unrelated typos, or adjust indentation unless specifically instructed to.
* **Strict Whitespace Preservation:** Do not add or remove trailing newlines, leading spaces, or carriage returns. The output code block must start and end exactly where the input snippet starts and ends.
* **Character Safety:** Never insert non-ASCII characters. Use LaTeX macros for symbols or accented characters.
* **Breaking:** Always use `\forcelinebreak{}` when breaking outside of display math. Never use `\\` or `\newline`.
* **Use `\ref`** For linking, **ALWAYS** use `\ref`.
* **Modern LaTeX Syntax:** Use commands like `\textit{...}`, `\textup{...}`, or `\textbf{...}` instead of `{\it ...}`, `{\rm ...}`, or `{\bf ...}`.
* **Math:** Use `\[ ... \]` for display math instead of `$$...$$`. **Ensure "place \<punctuation\> at end of equation" puts the punctuation *inside* the math delimiters if it's a display formula.**
* **Declarative Lists:** For list label changes, use `enumitem` package syntax in the environment's optional argument (e.g., `\begin{enumerate}[label=\textup{(\arabic*)}]`) rather than manual `\item[...]` overrides.
* **Citations with References:** Always use the standard `\cite[<postnote>]{key}` syntax when a theorem or section reference is part of a citation.
* **Prevent optional argument parsing errors:** When placing a `\cite` with an optional argument inside another optional argument (e.g., `\begin{theorem}[{\cite[...]{...}}])`, the inner command must be wrapped in curly braces `{}` to prevent LaTeX parsing errors.
* **Strict inline math preservation:** Never simplify or "clean up" inline LaTeX math into plain text. For example, do not replace \(G'\), $G'$, or $G^{\prime}$ with G'. Even if the editor's comment uses plain text, you must translate it into the appropriate LaTeX syntax found in the original snippet.

## Common abbreviations
* "rom" stands for roman or upright, not typically roman numerals. Text should be made upright with `\textup{}`
* "pls link" is a directive to add a corresponding `\ref{}` instead of a raw number.

# Response style
For each correction, **you must respond with** (1) an explanation of the change in **NO MORE THAN TEN WORDS** (2) the edited LaTeX markdown code block. **IF YOU WRITE MORE THAN ONE CODE BLOCK POST PROCESSING WILL FAIL**. The code block must contain **only** the modified LaTeX snippet provided in **### LaTeX snippet**, with no added context before or after. Do not include comments, placeholders, or ellipses.

**If the snippet does not include the LaTeX element that needs modification (e.g., a label change requiring modification of `\begin{enumerate}` when only `\item` is provided), respond with an *empty code block* and the explanation "Insufficient context: need [element]".**

---

The next prompt will provide the first correction.


---
## 0

### Annotation: Caret

### Comment
```text
,
```

### PDF selected text
```text
= χ(RGn k)<Caret></Caret> where
```
  
### LaTeX snippet
```latex
that 
		$\sum_{i=0}^d d_{2i}(-1)^i = \chi(\mathbb{R}G_{n,k})$ where
```
### Response
```latex
that 
		$\sum_{i=0}^d d_{2i}(-1)^i = \chi(\mathbb{R}G_{n,k}),$ where
```

#### Explanation
##### Before codeblock
Based on the context provided, it appears you are indicating a missing punctuation mark (a comma) at the location of the caret in the mathematical expression.

In LaTeX, when a formula is followed by the word "where," it is standard convention to place a comma after the formula to separate the expression from the qualifying clause.

Here is the corrected LaTeX snippet:
##### After codeblock
**Changes made:**
*   Added a `,` immediately after `\chi(\mathbb{R}G_{n,k})` inside the math mode (or immediately after the `$` depending on your style preference; inside is generally preferred for spacing).

## 1

### Annotation: Caret

### Comment
```text
doesn't
```

### PDF selected text
```text
where RGn k<Caret></Caret> denotes
```
  
### LaTeX snippet
```latex
where $\mathbb{R}G_{n,k}$ denotes
```
### Response
```latex
where $\mathbb{R}G_{n,k}$ denotes
```

#### Explanation
##### Before codeblock
It appears you are pointing out a missing character in the LaTeX snippet compared to the PDF text.

In the PDF text, there is a subscript **$n$** (from $G_{n,k}$) that is present in the LaTeX snippet but seems to be missing or "doesn't" appear correctly in your reference.

To match the PDF text exactly, the LaTeX should be:
##### After codeblock
If your comment **"doesn't"** refers to the fact that the letter **$G$** should not be there or that the subscript is incorrect, please clarify. However, based on standard mathematical notation for Grassmannians:
*   **$\mathbb{R}$**: Real numbers
*   **$G_{n,k}$**: The Grassmannian manifold of $k$-dimensional subspaces in $\mathbb{R}^n$.

## 2

### Annotation: Caret

### Comment
```text
now
```

### PDF selected text
```text
Let us<Caret></Caret> move
```
  
### LaTeX snippet
```latex
Let us move
```
### Response
```latex
Let us now move
```

#### Explanation
##### Before codeblock
Based on your annotation, here is the updated LaTeX snippet:
##### After codeblock


## 5

### Annotation: Caret

### Comment
```text
,
```

### PDF selected text
```text
= p<Caret></Caret>
```
  
### LaTeX snippet
```latex
some $\lambda = \frac{p}{q}$ where
```
### Response
#### FAILURE:
Based on the context provided, it appears you are trying to insert a denominator to complete the fraction $\frac{p}{q}$ as shown in the LaTeX snippet.

**Suggested Change:**

```latex
= p/q
```

**Or, if you are following the LaTeX structure exactly:**

```latex
= \frac{p}{q}
```

**Explanation:**
The caret is positioned immediately after the `p`. In the provided LaTeX snippet, the variable $\lambda$ is defined as the fraction $\frac{p}{q}$. Adding `/q` or completing the `\frac` command would align the text with the intended mathematical expression.


## 6

### Annotation: Remove

### Comment
```text

```

### PDF selected text
```text
= 1<Remove>,</Remove> using
```
  
### LaTeX snippet
```latex
$d_0 =d_d =1$, using
```
### Response
```latex
$d_0 = d_d = 1$ using
```


## 7

### Annotation: Caret

### Comment
```text
also
```

### PDF selected text
```text
p|1 and<Caret></Caret> q|1.
```
  
### LaTeX snippet
```latex
$p|1$ and $q|1$
```
### Response
```latex
$p|1$ and also $q|1$
```

#### Explanation
##### Before codeblock
Based on the annotation and the context provided, it appears you are looking to insert the word **"also"** into the LaTeX snippet at the position indicated by the caret.

### Revised LaTeX snippet
##### After codeblock
**Explanation:**
*   The caret in the PDF text was placed between `and` and `q|1`.
*   The comment suggests adding the word `also` at that specific insertion point to improve the flow or logic of the statement.

## 10

### Annotation: Replace

### Comment
```text
somewhat well-known
```

### PDF selected text
```text
is <Replace>a well known fact</Replace> that
```
  
### LaTeX snippet
```latex
is a well known fact that
```
### Response
```latex
is a somewhat well-known fact that
```


# Overlapping corrections: [3, 4]

## 3

### Annotation: Caret

### Comment
```text
(
```

### PDF selected text
```text
∈Q\Z. Suppose<Caret></Caret> Pd
```
  
### LaTeX snippet
```latex
. Suppose $\sum_{i=0}^{d} d_{2i}\lambda^i =0$
```
### Response
#### FAILURE:
Based on the context provided, it appears you are looking to complete the mathematical sentence starting with "Suppose."

Here is the suggested completion for the text following the caret:

**Text completion:**
> $P_d(\lambda) = \sum_{i=0}^{d} d_{2i}\lambda^i = 0$

**Contextual view:**
> $\in \mathbb{Q} \setminus \mathbb{Z}$. Suppose $P_d(\lambda) = \sum_{i=0}^{d} d_{2i}\lambda^i = 0$

***

**Explanation:**
*   **The Comment `(`:** This likely indicates the start of a mathematical expression or a function definition, such as $P_d(\lambda)$.
*   **The Selected Text:** Ends with `Pd`, which is a common shorthand for a polynomial of degree $d$.
*   **The LaTeX snippet:** Provides the explicit summation formula $\sum_{i=0}^{d} d_{2i}\lambda^i =0$.


## 4

### Annotation: Caret

### Comment
```text
)
```

### PDF selected text
```text
= 0<Caret></Caret> for
```
  
### LaTeX snippet
```latex
Suppose $\sum_{i=0}^{d} d_{2i}\lambda^i =0$ for
```
### Response
```latex
Suppose $\left(\sum_{i=0}^{d} d_{2i}\lambda^i\right) = 0$ for
```

#### Explanation
##### Before codeblock
It appears you are indicating a missing closing parenthesis in the mathematical expression within the LaTeX snippet.

Based on your caret position, here is the corrected LaTeX:
##### After codeblock
**Changes made:**
1. Added `\left(` at the start of the summation.
2. Added `\right)` before the `= 0` to match your annotation.

# Overlapping corrections: [8, 9]

## 8

### Annotation: Remove

### Comment
```text

```

### PDF selected text
```text
q|1. Hence<Remove>,</Remove> λ
```
  
### LaTeX snippet
```latex
. Hence, $\lambda = \pm 1$
```
### Response
```latex
. Hence $\lambda = \pm 1$
```


## 9

### Annotation: Remove

### Comment
```text

```

### PDF selected text
```text
= ±1<Remove>,</Remove> which
```
  
### LaTeX snippet
```latex
$\lambda = \pm 1$, which
```
### Response
```latex
$\lambda = \pm 1$ which
```
