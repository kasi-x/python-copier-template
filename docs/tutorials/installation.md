# Install template pre-requisites

This tutorial will take you through installing copier, the templating engine that will allow you
to create new projects from the template, update existing projects in line with it, and keep projects in sync with changes to it.

`git` is required too: copier expands a revision of the template repository, and the projects it
generates are git repositories.

## Install uv

We recommend that you invoke copier via `uvx`, which will download, install, and run it in its own isolated `venv`. 

Please follow the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation).


## Try it out

If you run `uvx copier --version` then `copier` will be downloaded, installed, and run, and will print its version.

## Get the template's CLI

The repository also ships a one-command wrapper, `architekton-py new`, which picks the
release tag to expand, decides between creating a project and adopting an existing one, and warns
about — or protects — the files the target already has. No `--vcs-ref` or other copier flag is
needed:

```shell
uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py --help
```

The installed CLI clones and caches the template repo on first use. Inside a
checkout the equivalent forms are `uv run architekton-py …` and
`uv run python -m architekton.cli …`; add `--preset <name>` for a fully non-interactive run (see
[Create a New Project](./create-new.md)).

!!! note "Public interface"

    `architekton-py new`, the adopt path it auto-selects inside an existing
    project, and the `copier update` contract on generated projects are the
    public interface and follow semver. The questionnaire itself — question
    names, order, `when:` gates — is *not* part of that interface and may
    change between minor versions; stable entry points and answer-file
    compatibility are what a release commits to.

## Troubleshooting

Every message below is printed by `architekton-py new` itself (`architekton/cli.py`
writes all of them to stderr). Fix the cause, rerun the same command.

| Message | Cause | Fix |
| --- | --- | --- |
| `cannot clone the template repo … (the template is fetched on first use; is this machine offline?)` | first `uvx` use with no network, or the remote unreachable | go online, then rerun; for a mirror set `ARCHITEKTON_PY_TEMPLATE_URL` |
| `warning: could not refresh the cached template …; using the stale clone` | offline or fetch failure on a warm `~/.cache/architekton-py/repo` | go online and rerun; the stale clone still renders |
| `the delegated clone at … is not a template checkout (no copier.yml); delete it and rerun` | corrupt cache (double delegation guard) | `rm -rf ~/.cache/architekton-py/repo`, then rerun |
| `cannot prepare the cached template clone at …` | cache dir not writable | fix permissions on `~/.cache/architekton-py`, then rerun |
| `…/architekton/cli.py is missing; delete … and rerun` | partial clone missing the CLI | `rm -rf ~/.cache/architekton-py/repo`, then rerun |
| `unknown preset '…': no presets/….yml. Available presets: …` | `--preset` typo | pick a name from `architekton-py new <dir> --list-presets` |
| `… was generated from this template: update it with `copier update`` | `new` run inside an already-generated project | run `copier update` (or the adopt path) instead of a second copy |
| `cannot inspect …` | target unreadable (permissions / broken symlink) | fix the path's permissions, then rerun |
| `render failed: …` | copier raised mid-render (message carries the type and detail) | read the named error; rerun with `--dry-run` to see the plan first |
| `…; pass --preset <name> for a non-interactive run` | copier asked a question with no terminal attached | add `--preset <name>` (or `--list-presets` to choose one) |


You now have the pre-requisites to allow you to [create a new project](./create-new.md) and [adopt an existing one](./adopt-existing.md).
