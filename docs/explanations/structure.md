# Template Project Structure

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
