# Build the docs using Zensical

You can build the [Zensical](https://github.com/zenseact/zensical) / MkDocs based docs from the project directory by running:

```bash
$ task docs
```

This will build the static docs in the `site` directory, which includes API docs that pull in docstrings from the code.

See also: [Standards](../reference/standards.md).

```bash
$ firefox site/index.html
```

## Autobuild / Local Server

You can also run a local preview server, which will watch your `docs` directory for changes and rebuild automatically:

```bash
$ task docs-serve
```

You can view the pages at localhost (usually `http://127.0.0.1:8000`).

## Translated docs

English under `docs/` is the source of truth. A translation mirrors it path
for path under `docs-i18n/<lang>/`: `docs-i18n/ja/how-to/adopt.md` translates
`docs/how-to/adopt.md`. Translations come from
[orimono](https://github.com/kasi-x/orimono)'s Lattice Docs (run locally for
now) or are written by hand. Either way, a page that is not translated yet is
simply absent.

```bash
$ task docs-i18n                 # DOCS_LANG=ja by default
$ task docs-i18n-serve           # local preview of the translated site
```

`tools/docs_i18n.py` stages `build/docs-i18n/<lang>/` and builds it as its
own Zensical site, because Zensical renders one language per site:

- the translated pages, plus every non-Markdown file of `docs/` so that
  relative image links resolve;
- a `zensical.toml` generated from the root one, with the language, the
  directories and the edit link replaced, and the nav reduced to the
  translated pages. Each nav label is the page's own `#` heading, so there is
  no separate nav translation to keep in sync.

A translated page that links to an untranslated one gets a "page does not
exist" warning from the build. Translate the target, or link to the English
page with an absolute URL.

## Building docs in CI

After a successful run of CI:

Settings > Pages

![Setup GitHub Pages](../images/gh-pages-setup.png)
