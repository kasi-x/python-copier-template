# Template Project Structure

This page covers two trees: the folders a **generated project** gets (below),
and the **template repository's** own layout -- in particular the symlink
convention that keeps the two in sync.

## The template repository: root files are shared by symlinking

Several files must exist both in this repository (where the template's own CI,
editor configuration and secret scanning use them) and in every generated
project (where they do the same job). The convention is to keep **one real
file at the repository root** and make `template/` **link to it**, so the
repository dogfoods exactly what it ships: the workflows that test this repo
are byte-for-byte the workflows a generated project receives, and editing one
side edits both.

The 14 links under `template/`:

| link (under `template/`) | real file (repository root) |
| --- | --- |
| `.devcontainer` | `.devcontainer/` |
| `.vscode` | `.vscode/` |
| `.gitleaks.toml` | `.gitleaks.toml` |
| `.github/pages` | `.github/pages/` |
| `.github/{...}/actions/setup-runner/action.yml` | `.github/actions/setup-runner/action.yml` |
| `.github/{...}/workflows/_tasks.yml` | `.github/workflows/_tasks.yml` |
| `.github/{...}/workflows/_test.yml` | `.github/workflows/_test.yml` |
| `.github/{...}/workflows/_docs.yml` | `.github/workflows/_docs.yml` |
| `.github/{...}/workflows/_hygiene.yml` | `.github/workflows/_hygiene.yml` |
| `.github/{...}/workflows/_dist.yml` | `.github/workflows/_dist.yml` |
| `.github/{...}/workflows/_release.yml` | `.github/workflows/_release.yml` |
| `.github/{...}/workflows/_container.yml` | `.github/workflows/_container.yml` |
| `.github/{...}/workflows/_pypi.yml` | `.github/workflows/_pypi.yml` |
| `{...}tests/conftest.py` | `tests/conftest.py` |

(The `{...}` stands for the Jinja filename conditions that gate each path.)

Two consequences follow from the convention:

- **Editing a root file silently edits every generated project.** The
  `.github/workflows/_*.yml` reusable workflows, `.gitleaks.toml` and
  `tests/conftest.py` are render inputs: copier follows the links and writes
  the linked bytes into each render. This is the point of the convention, but
  it means a "repo-only" change to those files is a template change and should
  be verified like one (the render-twin tooling and the suite both treat them
  as template bytes; `tools/render_inputs.py` hashes through the links).
- **Only content-identical files may be linked.** A file the template must
  render differently per answer cannot be a symlink. The cautionary example is
  `.python-version`: it was linked once, which broke the ros2 distro pins
  (the repository needs a fixed interpreter while the template renders a
  per-answer value), so it is now a real `.jinja` file in `template/` and a
  separate fixed file at the root.

## Generated project layout

The template generates projects with the following folders at the root level.

## src

This folder contains the source code for the project. Typically this contains a single folder with the package name for the project and the folder contains python modules files. A `src/` layout is the default because it prevents accidental imports of an uninstalled package.

## tests

This folder holds all of the tests that will be run by pytest, both locally and in CI. See [how to run the tests](../how-to/run-tests.md).

## docs

This folder contains the source for the zensical / MkDocs documentation.

## .github

Configuration for the Continuous Integration Workflow on github

## VSCode specific folders

### .devcontainer

Configuration for running the developer container for this project in VSCode.

### .vscode

VSCode settings for this project:

- enable static analysis in the editor
- enables python debugging.
