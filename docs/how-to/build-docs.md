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

## Building docs in CI

After a successful run of CI:

Settings > Pages

![Setup GitHub Pages](../images/gh-pages-setup.png)
