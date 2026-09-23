# The Quarto Paper and Slides

Projects generated with the data-science layer ship a research-writing
scaffold alongside the analysis tree: a Quarto paper targeting arXiv, a
reveal.js slide deck, a bibliography, and a quartodoc API reference that
reads the package's own docstrings. The scaffold answers a specific
question — *how do I go from a `src/` analysis to a submittable paper
without copy-pasting numbers?* — by making the paper **execute** the same
package the analysis uses.

## What ships

| Path | Purpose |
| --- | --- |
| `paper/paper.qmd` | the manuscript, rendered to `arxiv-pdf` and `arxiv-html` |
| `slides/slides.qmd` | a reveal.js deck (`clean-revealjs` format) |
| `_quarto.yml` | project config: bibliography, CSL, and the `quartodoc` section |
| `references/references.bib` + `references/chicago-author-date.csl` | starter bibliography and citation style |
| `outputs/` | tables and figures the paper reads in (git-ignored like `data/`) |
| `paper/_extensions/arxiv/` | the [arxiv Quarto extension](https://github.com/mikemahoney218/quarto-arxiv) by Mike Mahoney (vendored, MIT) |
| `slides/_extensions/clean/` | the [clean revealjs theme](https://github.com/grantmcdermott/quarto-revealjs-clean) by Grant McDermott (vendored, MIT) |

The `paper`, `slides` and `paper-api` tasks exist only where the scaffold
ships — check `task paper --list`
(or your runner's equivalent) if in doubt.

## Prerequisites

1. **Quarto itself** — <https://quarto.org/docs/get-started> (1.6+).
2. **A LaTeX toolchain for the PDF** — easiest is Quarto's own TinyTeX:
   `quarto install tinytex`. The HTML output needs no LaTeX.
3. **The project environment** — the `.qmd` files run with `jupyter:
   python3`, i.e. the kernel of the environment you render from. Render
   from an activated project environment (`uv run` / `pixi run -e dev` /
   `poetry run`) so the cells see the package and its dependencies;
   `ipykernel` is already among the dev dependencies.

## Rendering

```sh
task paper        # paper/paper.qmd → paper/paper.pdf + .html
task slides       # slides/slides.qmd → the reveal.js html
task paper-api    # quartodoc build --config _quarto.yml
```

(`task` throughout; the tasks exist on every runner the template offers —
`just paper`, `make paper`, `poe paper`, `pixi run -e dev paper`.)

The tasks are thin wrappers (`quarto render paper/paper.qmd`, `quarto
render slides/slides.qmd`, `quartodoc build --config _quarto.yml`) — call
Quarto directly when you need its flags (`--to pdf`, `--execute-daemon`).

On first use, quartodoc needs a one-time install into the project:
`quarto add machow/quartodoc`. It then generates API reference pages from
the package docstrings into `docs/reference/`, so the paper's appendix and
the package documentation read from the same source of truth. Re-run
`task paper-api` after docstring changes; the paper's
*Software* appendix table is generated at render time from
`pyproject.toml`'s dependencies, never by hand.

## The paper ↔ analysis contract

The scaffold's central convention is that **the paper never hard-codes a
number**. Analysis code in `src/` writes tables and figures into
`outputs/`; the paper reads them at render time:

````markdown
```{python}
#| label: tbl-one
#| tbl-cap: Summary statistics
#| output: asis
#| echo: false

with open(Path("outputs/table_one.tex"), "r") as f:
    print(f.read())
```
````

...and cross-references it as `@tbl-one` (figures: `@fig-...`; sections:
`@sec-...` — the labels live in the code-cell options and the `{#sec-...}`
headers). Citations come from `references/references.bib` in the usual
pandoc syntax (`@example2020key`, `[@a; @b]`), styled by the CSL file.
Keep the `outputs/` direction one-way: `src/` writes it, the paper reads
it, nothing else edits it — that is what makes a re-render reproducible.

The template's own `paper.qmd` doubles as a tutorial: commented-out
blocks show the figure include and the LaTeX table pattern, and the
*Software* appendix shows the generated package table.

## Slides

`slides/slides.qmd` targets `clean-revealjs` — the minimalist reveal.js
theme, vendored under `slides/_extensions/clean/` so the deck renders
with no `quarto add` step. It embeds its resources into a single file
(`embed-resources: true`, MathJax from CDN) and writes
`<repo>_slides.html` at the repo root. Slide content follows the same
execute-as-you-go model — a `{python}` cell renders its output into the
slide.

## What does not ship

There is **no CI job** for the paper: LaTeX renders are too heavy and too
font-sensitive for the generated project's default pipeline, and a paper
is rendered when *you* need it, not on every push. Rendering locally (or
in a release workflow you add yourself) is the intended loop. The
scaffold also stays out of the agent guide's command table on purpose —
`AGENTS.md` documents the checks that must stay green; the paper is a
product, not a check.
