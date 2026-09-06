# Pixi Projects

How to work with a project generated with `package_manager: pixi`, and how
to migrate an existing `pixi.toml`-based project onto the template's layout.

## Where the pixi configuration lives

The template stores pixi configuration in `pyproject.toml` under
`[tool.pixi.*]` — **no standalone `pixi.toml` is generated**. pixi reads
`[tool.pixi.*]` from `pyproject.toml` natively, and keeping everything in
one file means the project metadata (`[project]`) stays identical across
the uv / pixi / poetry choices. If you prefer a standalone `pixi.toml` you
can move the sections over (see below), but the generated tooling
(`pixi.lock`, CI, tasks) works with the `pyproject.toml` layout as-is.

The generated file contains:

```toml
[tool.pixi.workspace]
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

[tool.pixi.pypi-dependencies]
my_package = { path = ".", editable = true }

[tool.pixi.environments]
default = { solve-group = "default" }
dev = { features = ["dev"], solve-group = "default" }
```

Runtime dependencies go into the standard `[project] dependencies` list and
dev dependencies into the standard `[dependency-groups]` dev group — pixi
picks both up as PyPI dependencies of the matching feature. (data_science /
kaggle projects additionally get an `experiment` feature under
`[tool.pixi.feature.experiment.pypi-dependencies]`.)

## Dependency format: flat tables

pixi dependencies are declared as a **flat table** — one `name = "version"`
entry per package:

```toml
[tool.pixi.dependencies]
python = ">=3.11"
numpy = ">=2"
```

Writing one sub-table per package is invalid TOML here and fails with
cryptic errors such as `invalid character in string`:

```toml
# WRONG — do not do this
[tool.pixi.dependencies.numpy]
version = ">=2"
```

## conda vs PyPI packages

| Table | Source | Use for |
|-------|--------|---------|
| `[tool.pixi.dependencies]` | conda-forge | native/non-Python libraries (`ffmpeg`, `gdal`, `cmake`, ...), and `python` itself |
| `[tool.pixi.pypi-dependencies]` | PyPI (pip) | everything pip-installable, including your project (editable) |
| `[project] dependencies` / `[dependency-groups]` | PyPI (pip) | same as above, in the standard PEP 621/735 places pixi also reads |

**PyTorch and friends:** conda-forge's `pytorch` builds lag the CUDA
releases and can be unsatisfiable on some platforms
(`only pytorch<=1.0.2 is available`-style solver failures). The reliable
pattern is to keep heavy ML packages on the **PyPI side** and, when you need
CUDA wheels, add the PyPI index explicitly (this is what generated kaggle
projects do for uv):

```toml
[tool.pixi.pypi-dependencies]
torch = { version = ">=2.6", index = "https://download.pytorch.org/whl/cu126" }
```

Check <https://prefix.dev/channels/conda-forge> for what a conda package
actually provides before putting it in `[tool.pixi.dependencies]`.

## Migrating an existing `pixi.toml` project

1. Copy `[tool.pixi.*]` sections from your `pixi.toml` into
   `pyproject.toml` — the table names are identical.
2. Move pure-Python runtime deps from `[dependencies]` into
   `[project] dependencies`, and dev deps from `[tool.dev-dependencies]` /
   features into `[dependency-groups]` (or keep them under the matching
   `[tool.pixi.feature.<name>.pypi-dependencies]`).
3. Tasks survive verbatim: `[tasks]` and
   `[tool.pixi.feature.dev.tasks]` work in `pyproject.toml` exactly as in
   `pixi.toml`.
4. Delete `pixi.toml` (if both files exist pixi prefers `pixi.toml` and
   ignores your `pyproject.toml` sections), then run `pixi install` to
   regenerate `pixi.lock`.

## Everyday commands

```sh
pixi run -e dev shell        # dev environment (ruff/pytest/... installed)
pixi run test                # tasks defined by the chosen task runner
pixi run -e dev --locked test  # what CI runs (fails if pixi.lock is stale)
pixi update                  # refresh pixi.lock
```

CI picks the right tool automatically: the generated workflows install
`setup-pixi` when a `pixi.lock` is present (and setup-uv / poetry
otherwise), so no workflow edits are needed when switching package
managers.
