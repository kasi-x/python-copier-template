# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Bug Fixes

- copier should not be a dev dependency (#364) (718a485)


### Dependencies

- update astral-sh/setup-uv action to v9 (#363) (a0cac98)

- lock file maintenance (#366) (b8caef5)

- lock file maintenance (#367) (4ee6984)

- lock file maintenance (#368) (f39321a)


## [5.3.0]

### Dependencies

- update github actions (#351) (f458740)

- update pre-commit hook gitleaks/gitleaks to v8.30.1 (#352) (dfb14a4)

- update softprops/action-gh-release action to v3 (#362) (f889d83)

- update pre-commit hook pre-commit/pre-commit-hooks to v6 (#361) (d53e98a)

- update astral-sh/setup-uv action to v8 (#354) (2ea9db6)

- update github artifact actions (major) (#360) (cfcde41)

- update docker/setup-buildx-action action to v4 (#359) (5a3129c)

- update docker/metadata-action action to v6 (#358) (c97e1fc)

- update docker/login-action action to v4 (#357) (38d5b02)

- update docker/build-push-action action to v7 (#356) (89ce177)

- update actions/checkout action to v7 (#353) (03ac4ca)

- update codecov/codecov-action action to v7 (#355) (37b5344)


### Refactor

- remove dead code of debug container (a589896)

- remove dead code of debug container (#347) (18a7ecf)


## [5.2.0]

### Miscellaneous Tasks

- Use Ubuntu 26.04 (resolute) for devcontainer (#345) (7fa903a)


## [5.1.0]

### Features

- Add support for python 3.14 to copier template (#341) (aed03d7)


## [5.0.3]

### Bug Fixes

- Force uv to manage python itself (#335) (1dfadc8)


### Miscellaneous Tasks

- Remove reference to transferring into DiamondLightSource (#330) (47dcc42)


### Refactor

- Reformat link table template in README (#322) (dc6564e)


## [5.0.2]

### Bug Fixes

- tox / pyright python environment (#320) (d220299)


## [5.0.1]

### Bug Fixes

- Better handling of large files (#317) (c52b391)


## [5.0.0]

### Bug Fixes

- Remove codecov token (#312) (39120c6)

- Add application to component_type choices (#314) (294dc13)


### Miscellaneous Tasks

- Add cron to make issue for supporting new version of Python (#313) (70860ef)


## [5.0.0a5]

### Features

- Add renovate (#311) (b4da80f)


## [5.0.0a4]

### Features

- Add a global cache for uv, pre-commit and global venv (#307) (17daee5)


### Miscellaneous Tasks

- Bump the actions group with 5 updates (#293) (ae18808)


## [5.0.0a3]

### Bug Fixes

- VSCode garbled REPL (#298) (23f280c)


## [5.0.0a2]

### Bug Fixes

- run uv lock before pushing example code (#292) (c8fc7b7)

- make sure pyright is happy with external deps (#296) (73c31e3)

- container now copies managed python into runtime (#297) (7659ef5)


### Miscellaneous Tasks

- add pre-commit hook, config with sealed-secrets allowlist, and tests (#287) (32c6c7b)


## [5.0.0a1]

### Bug Fixes

- Remove requirement for buildkit (#290) (2aa1177)


### Refactor

- Convert to use `uv` (#248) (ed290c8)


## [4.3.0]

### Bug Fixes

- Enable subprocess coverage (#289) (ace29b9)


## [4.2.0]

### Features

- Enable pep8-naming ruff rules (#283) (9d544a5)


## [4.1.0]

### Documentation

- Document repo creation method (#275) (5294bde)


### Features

- Publish debug container image and account-sync sidecar (#251) (76c187c)


### Miscellaneous Tasks

- remove `trust` now that HEAD does not require trust. (#276) (07b2169)


## [4.0.1]

### Bug Fixes

- Deduplicate jobs from generated workflows (#272) (92dc82c)


## [4.0.0]

### Bug Fixes

- Remove need for --trust (#271) (d48d075)


## [3.1.0]

### Bug Fixes

- Move to long-form Github URLs (#260) (1c71289)

- Remove docs references to test outputs (#267) (2000007)

- Handle pinned sha versions of Python in the install_requirements action (#268) (dfe17b1)


### Miscellaneous Tasks

- Remove check workflow and filter on branch name (#253) (e07bbe8)

- Enforce Conventional Commit PR titles (#255) (71c6bb0)

- Update pre-commit-hooks to v5.0.0 (#242) (242d289)

- Bump softprops/action-gh-release from 2.2.0 to 2.2.2 in the actions group (#228) (99dc4b6)

- 241 release pipeline does not depend on tests (#257) (a7b863a)


## [0.1.0]


