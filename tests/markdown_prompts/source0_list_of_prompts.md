#0

### Type
Remove

### Comment
```text
delete
```

### Replies 

#### Reply 1
```text
reply
```

#### Reply 2
```text
another reply
```

### PDF selected text
```text
curvature regimes1<Remove>.</Remove>
```
  
### LaTeX snippet
```latex
understand the failure of the ``Flat Orbit Conjecture'' in higher curvature regimes\footnote{
Originally conjectured by P.\ Alexandrov, the Flat Orbit Conjecture proposed that all $\lambda$-periodic orbits of a $\mathrm{CAT}(0)$ space are isometric to Euclidean circles. 
This is now known to be false in dimensions $\geq 3$ due to \cite{hubard23}.}.

\section{Background and Preliminaries}



Let
```

---

#1

### Type
Caret

### Comment
```text
. <period: put foootnote after period>
```

### PDF selected text
```text
curvature regimes<Caret></Caret>1
```
  
### LaTeX snippet
```latex
curvature regimes\footnote{
Originally conjectured by P.\ Alexandrov, the Flat Orbit Conjecture proposed that all $\lambda$-periodic orbits of a $\mathrm{CAT}(0)$ space are isometric to Euclidean circles. 
This is now known to be false in dimensions $\geq 3$ due to \cite{hubard23}.}.

\section{Background and Preliminaries}



Let
```

---

#2

### Type
Replace

### Comment
```text
Flat orbit conjecture
```

### PDF selected text
```text
the <Replace>“Flat Orbit Conjecture”</Replace> in
```
  
### LaTeX snippet
```latex
the ``Flat Orbit Conjecture'' in
```

---

#3

### Type
Remove

### Comment
```text
<close up space>
```

### PDF selected text
```text
in non<Remove>-</Remove> flat
```
  
### LaTeX snippet
```latex
in non-flat $\mathrm{CAT}(0)$
```

---

#4

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
= x}<Remove>,</Remove>
```
  
### LaTeX snippet
```latex
group
\[
    \mathrm{Stab}_{\mathcal{G}}(x) = \{ g \in \mathcal{G} \mid g \cdot x = x \},
\]
whose
```

---

#5

### Type
Replace

### Comment
```text
765489
```

### PDF selected text
```text
No. <Replace>314159357</Replace>. F.
```
  
### LaTeX snippet
```latex
No.\ 314159357. F.
```

---

#6

### Type
Replace

### Comment
```text
The first author
```

### PDF selected text
```text
<Replace>L. H.</Replace> was
```
  
### LaTeX snippet
```latex
L.\ H.\ was
```

---

#7

### Type
Highlight

### Comment
```text
please move to Acknowledgments section.
```

### PDF selected text
```text
L. H. was supported by NSF grant No. 314159357. F. E. thanks the Department of Linguistics</Highlight> <Highlight>for the valuable conversations. 1Originally
```
  
### LaTeX snippet
```latex
L.\ H.\ was supported by NSF grant No.\ 314159357. F.\ E.\ thanks the Department of Linguistics for the valuable conversations.
```

---

#8

### Type
Replace

### Comment
```text
p <small cap>
```

### PDF selected text
```text
and <Replace>P</Replace>reliminaries
```
  
### LaTeX snippet
```latex
regimes\footnote{
Originally conjectured by P.\ Alexandrov, the Flat Orbit Conjecture proposed that all $\lambda$-periodic orbits of a $\mathrm{CAT}(0)$ space are isometric to Euclidean circles. 
This is now known to be false in dimensions $\geq 3$ due to \cite{hubard23}.}.

\section{Background and Preliminaries}



Let
```

---

#9

### Type
Replace

### Comment
```text
; e
```

### Replies 

#### Reply 1
```text
a reply to a replace annotation
```

### PDF selected text
```text
at x0<Replace>. E</Replace>ach ellipse
```
  
### LaTeX snippet
```latex
at $x_0$. Each ellipse
```

---

#10

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
∆(x, λ)<Remove>.</Remove>
```
  
### LaTeX snippet
```latex
constant $\Delta(x,\lambda)$.
```

---

#11

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
under λ-perturbation<Remove>.</Remove>
```
  
### LaTeX snippet
```latex
$\lambda$-perturbation.
```

---

#12

### Type
Replace

### Comment
```text
if and only if
```

### PDF selected text
```text
quasi-uniform <Replace>if</Replace>
```
  
### LaTeX snippet
```latex
quasi-uniform iff
\begin{equation}
    \int_X \rho(x)\, d\mu(x) = \frac{\lambda^2}{1+\lambda\varphi}.
\end{equation}
(The
```

---

#13

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
<Remove>(</Remove>The proof
```
  
### LaTeX snippet
```latex
iff
\begin{equation}
    \int_X \rho(x)\, d\mu(x) = \frac{\lambda^2}{1+\lambda\varphi}.
\end{equation}
(The proof
```

---

#14

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
Appendix B.<Remove>)</Remove>
```
  
### LaTeX snippet
```latex
Appendix~B.)

\subsection{Curvature sensitivity}
A
```

---

#15

### Type
Highlight

### Comment
```text
COMP: set typewriter font <\texttt{}>
```

### PDF selected text
```text
in <Highlight>Julia 1.10</Highlight> to
```
  
### LaTeX snippet
```latex
divergence.

\begin{figure}[htbp]
\centering
\begin{tikzpicture}[scale=1.0]
  \draw[->] (-2,0)--(2,0) node[right] {$\lambda$};
  \draw[->] (0,-0.2)--(0,2.5) node[above] {$\mathrm{Var}(\rho)$};
  \draw[domain=0.5:1.8, smooth, variable=\x, blue, thick]
     plot ({\x},{(\x*\x*\x-1)/(2+\x*\x)});
  \draw[dashed, red] (1,0)--(1,0.0);
  \node at (1.3,1.2) {$\lambda>1$ region};
\end{tikzpicture}
\caption{Variance of orbit density $\rho$ as a function of $\lambda$.}
\end{figure}

\section{Numerical Experiments}

We implemented a simple prototype in \textsf{Julia 1.10} to visualize $\mathcal{F}_\lambda(X)$ for synthetic $\mathrm{CAT}(0)$
```

---

#16

### Type
Highlight

### Comment
```text
small cap
```

### PDF selected text
```text
Numerical <Highlight>E</Highlight>xperiments
```
  
### LaTeX snippet
```latex
divergence.

\begin{figure}[htbp]
\centering
\begin{tikzpicture}[scale=1.0]
  \draw[->] (-2,0)--(2,0) node[right] {$\lambda$};
  \draw[->] (0,-0.2)--(0,2.5) node[above] {$\mathrm{Var}(\rho)$};
  \draw[domain=0.5:1.8, smooth, variable=\x, blue, thick]
     plot ({\x},{(\x*\x*\x-1)/(2+\x*\x)});
  \draw[dashed, red] (1,0)--(1,0.0);
  \node at (1.3,1.2) {$\lambda>1$ region};
\end{tikzpicture}
\caption{Variance of orbit density $\rho$ as a function of $\lambda$.}
\end{figure}

\section{Numerical Experiments}

We
```

---

#17

### Type
Highlight

### Comment
```text
lowercase
```

### PDF selected text
```text
Numerical <Highlight>S</Highlight>imulation. Following
```
  
### LaTeX snippet
```latex
boundaries.

\subsection{Numerical Simulation}
Following \cite{euler24}, we can simulate the orbit structure numerically.
```

---

#18

### Type
Highlight

### Comment
```text
lowercase
```

### PDF selected text
```text
and <Highlight>E</Highlight>xamples
```
  
### LaTeX snippet
```latex
.
\end{corollary}

\begin{figure}[htbp]
\centering
\begin{tikzpicture}[scale=1.1]
  \foreach \a in {0,30,...,330}{
    \draw[thick, blue!60] (0,0) ellipse ({2+0.3*sin(\a)} and {1+0.2*cos(\a)});
  }
  \filldraw[black] (0,0) circle (2pt) node[below left] {$x_0$};
  \node at (1.5,1.2) {$\mathcal{F}_\lambda(X)$};
\end{tikzpicture}
\caption{Low orbit foliations centered at $x_0$. Each ellipse represents an orbit of constant $\Delta(x,\lambda)$.}
\end{figure}

\section{Applications and Examples}

Consider
```

---

#19

### Type
Highlight

### Comment
```text
Move caption to top of table
```

### PDF selected text
```text
-0.403 <Highlight>Table 1. Empirical orbit metrics under λ-iteration.</Highlight>
```
  
### LaTeX snippet
```latex
Empirical orbit metrics under $\lambda$-iteration.
```

---

#20

### Type
Replace

### Comment
```text
Figure
```

### PDF selected text
```text
observation (<Replace>Fig.</Replace> 5)
```
  
### LaTeX snippet
```latex
observation (Fig.~\ref{fig:scatter}) was
```

---

#21

### Type
Highlight

### Comment
```text
put footnote after period
```

### PDF selected text
```text
Hamiltonian systems<Highlight>2.</Highlight>
```
  
### LaTeX snippet
```latex
a double-lobed structure reminiscent of quasi-periodic tori in Hamiltonian systems\footnote{A referee pointed out that this might be a discretization artifact, but we were unable to reproduce it analytically.}. 

\begin{figure}[htbp]
\centering
\begin{tikzpicture}[scale=1.0]
  \filldraw[blue!50,opacity=0.6] (0.3,0.5) circle (0.15);
  \filldraw[blue!50,opacity=0.6] (-0.3,0.5) circle (0.15);
  \filldraw[red!60,opacity=0.5] (0,-0.6) circle (0.3);
  \node at (0,-1.1) {bifurcation lobes};
  \draw[->,thick] (-1,0)--(1,0);
  \draw[->,thick] (0,-1.5)--(0,1.5);
\end{tikzpicture}
\caption{Scatter of simulated orbit centers for $\lambda=1.6$.}
\label{fig:scatter}
\end{figure}

\section{Discussion and Further Work}

Our
```

---

#22

### Type
Replace

### Comment
```text
Equation
```

### PDF selected text
```text
However, <Replace>Eq.</Replace> (7)
```
  
### LaTeX snippet
```latex
However, Eq.~(7)
```

---

#23

### Type
Replace

### Comment
```text
(5) <pls link>
```

### PDF selected text
```text
Eq. <Replace>(7)</Replace> reveals
```
  
### LaTeX snippet
```latex
Eq.~(7) reveals
```

---

#24

### Type
Highlight

### Comment
```text
<link>
```

### PDF selected text
```text
(Hypothesis <Highlight>5.1</Highlight>) that
```
  
### LaTeX snippet
```latex
(Hypothesis 5.1) that
```

---

#25

### Type
Highlight

### Comment
```text
remove new paragraph: continue the last paragraph with this sentence.
```

### PDF selected text
```text
setting. <Highlight>We hypothesize</Highlight> (Hypothesis
```
  
### LaTeX snippet
```latex
setting.

We hypothesize (Hypothesis
```

---

#26

### Type
Replace

### Comment
```text
; at
```

### PDF selected text
```text
φ2 ≈2.618<Replace>. At</Replace> that
```
  
### LaTeX snippet
```latex
near $\lambda = \varphi^2 \approx 2.618$.  
At that
```

---

#27

### Type
Highlight

### Comment
```text
does this look right?
```

### PDF selected text
```text
resonance <Highlight>near λ = φ2 ≈</Highlight>2.618. At
```
  
### LaTeX snippet
```latex
resonance near $\lambda = \varphi^2 \approx 2.618$.
```

---

#28

### Type
Highlight

### Comment
```text
place footnote after period
```

### PDF selected text
```text
first author<Highlight>3.</Highlight>
```
  
### LaTeX snippet
```latex
first author\footnote{Submitted to the \emph{Journal of Approximate Topologies}, 2025.}.  

\subsection{Error analysis and convergence}

While
```

---

#29

### Type
Highlight

### Comment
```text
place footnote after comma
```

### PDF selected text
```text
is questionable<Highlight>4,</Highlight> the
```
  
### LaTeX snippet
```latex
is questionable\footnote{We observed divergence for $|\lambda| > 2.1$, which we did not persue.}, the
```

---

#30

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
+ λφ)<Remove>,</Remove>
```
  
### LaTeX snippet
```latex
condition,
\[
    \langle f_i, f_j \rangle_\varphi = \delta_{ij}(1+\lambda\varphi),
\]
we
```

---

#31

### Type
Highlight

### Comment
```text
<link>
```

### PDF selected text
```text
Theorem <Highlight>4.3.</Highlight>
```
  
### LaTeX snippet
```latex
Theorem~4.3.

\bigskip

\noindent
\textbf{Acknowledgements.}
```

---

#32

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
φ-orthogonality condition<Remove>,</Remove>
```
  
### LaTeX snippet
```latex
-orthogonality condition,
\[
    \langle f_i, f_j \rangle_\varphi = \delta_{ij}(1+\lambda\varphi),
\]
we
```

---

#33

### Type
Remove

### Comment
```text

```

### PDF selected text
```text
∥∆n −∆n−1∥<Remove>.</Remove>
```
  
### LaTeX snippet
```latex
difference $\|\Delta_n - \Delta_{n-1}\|$.
```

---

#34

### Type
Caret

### Comment
```text
,
```

### PDF selected text
```text
Way, Genevive<Caret></Caret> 06578,
```
  
### LaTeX snippet
```latex
Way, Genevive 06578,
```

---

#35

### Type
Caret

### Comment
```text
,
```

### PDF selected text
```text
Circle, Washington<Caret></Caret> 12765,
```
  
### LaTeX snippet
```latex
Circle, Washington 12765,
```

---

#36

### Type
Caret

### Comment
```text
; and Department of Mathematics, Princeton University, Nassau Street, Princeton New Jersey, 02854
```

### PDF selected text
```text
12765, USA<Caret></Caret> Email
```
  
### LaTeX snippet
```latex
12765, USA
```