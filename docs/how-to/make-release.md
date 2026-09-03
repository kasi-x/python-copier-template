# Make a release

To make a new release, please follow this checklist:

- Ensure that you have previously followed [PyPI uploading](./pypi.md)
- Regenerate `CHANGELOG.md` from [Conventional Commits](https://www.conventionalcommits.org)
  with [git-cliff](https://git-cliff.org): `uvx --from git-cliff git-cliff -o CHANGELOG.md`,
  then commit it
- Choose a new PEP440 compliant release number (see <https://peps.python.org/pep-0440/>)
- Go to the GitHub [release] page
- Choose `Draft New Release`
- Click `Choose Tag` and supply the new tag you chose (click create new tag)
- Publish the release; the release notes are filled in automatically from
  git-cliff (categorised by Conventional Commit type, for this tag only) —
  review and edit them if needed, then click `Publish Release`

Note that tagging and pushing to the main branch has the same effect except that
you will not get the option to edit the release notes.

A new release will be made and the wheel and sdist uploaded to PyPI.

[release]: https://github.com/kasi-x/python-copier-template/releases
