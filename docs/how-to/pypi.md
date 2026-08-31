# Setting up PyPI publishing

To publish your package on PyPI requires a PyPI account and for PyPI to be setup for [Trusted Publisher](https://docs.pypi.org/trusted-publishers/).

## Gather the information

You will need the following information:

- Owner: The GitHub org that the repo is contained in, e.g. `kasi-x`
- Repository name: The GitHub repository name, e.g. `python-copier-template-example`
- PyPI Project Name: The distribution name on PyPI, e.g. `kasi-x-python-copier-template-example`
- Workflow name: The workflow that does publishing, `_pypi.yml` for `python-copier-template` projects
- Environment name: The GitHub environment that publishing is done with, `release` for `python-copier-template` projects

## Publishing to PyPI

Use the above information in one of the following guides:

- [Creating a PyPI project with a trusted publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Adding a trusted publisher to an existing PyPI project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
