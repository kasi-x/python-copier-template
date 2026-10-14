# Setup the repository with recommended settings

When the repository has been created, it will require some settings to be changed for all the features of architekton-py to work. These are listed below.

## Discussions

The contributing guide for the template recommends that new users start a discussion for questions. You can enable this feature by navigating to your repository page and:

- Visiting `Settings` > `General`
- Scrolling down to `Features`
- Enabling it as shown

!<lt-m v="["/>Setup GitHub Features<lt-m v="](../images/gh-features-setup.png)"/>

## Branch protection

GitHub will prompt you that your `main` branch is not protected. It is recommended that a <lt-m v="["/>branch protection rule<lt-m v="](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)"/> is setup for `main` to require pull requests.

## Code Coverage

To ensure that code coverage is correctly uploaded to codecov.io follow <lt-m v="["/>Code Coverage<lt-m v="](./coverage.md)"/>.

## Renovate

To ensure that your dependencies are kept up to date follow <lt-m v="["/>Renovate<lt-m v="](./renovate.md)"/>.

## GitHub pages

If you configured the project to have docs then follow <lt-m v="["/>Building docs<lt-m v="](./build-docs.md)"/>.

## PyPI uploading

If you configured the project to upload built wheels to PyPI then follow <lt-m v="["/>PyPI uploading<lt-m v="](./pypi.md)"/>.
