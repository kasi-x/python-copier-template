# Get a project without copier (`dist` branch + `bootstrap.sh`)

Every preset's *output* is static: the same answers always render the same
bytes. CI renders all of `presets/*.yml` on every `main` push and publishes
the result on the **`dist` branch** — flat trees, no Jinja, no copier
involved. This page is the no-copier path; the questionnaire path is
[tutorial](../tutorials/create-new.md).

## Just want the files

```shell
git clone -b dist https://github.com/politeuma/architekton-py.git
cp -r architekton-py/library my-project
```

Each top-level directory is a complete project (`library`, `cli`,
`web-api`, `ros2`, `micropython`, `data-science`, …). `index.json` lists
every file per preset, so you can also browse it on GitHub's branch
switcher before downloading.

## Ask first, then fetch: `bootstrap.sh`

For the knobs that genuinely vary per user — the project name, the package
name, the logging library — the branch ships `bootstrap.sh`:

```shell
curl -fsSL https://raw.githubusercontent.com/politeuma/architekton-py/dist/bootstrap.sh | bash
```

It asks four questions (preset / project name / package name / log
library), downloads the preset tree, renames the `smoke_example`
placeholders, and drops in `variants/logging_setup/<preset>/<lib>.py`
(rendered per library — loguru, picologging, or stdlib logging — so a
switch changes the file's *body*, not just a name). Environment variables
`PRESET`, `PROJECT`, `PACKAGE`, `LOG_LIB` answer non-interactively;
`DIST_DIR=/path/to/dist` fetches from a local checkout instead of GitHub.

## When you still need copier

`bootstrap.sh` covers the four questions above — nothing else. A different
strictness tier, a GitLab remote, an adoption into an existing project:
those are still the questionnaire's job, rendered locally:

```shell
uvx copier copy --trust https://github.com/politeuma/architekton-py.git my-project
```

Same render path either way — `bootstrap.sh` fetches exactly the bytes the
copier render produces, so the two cannot drift apart.

## Where it comes from

`architekton/gen_static.py` renders `dist/` (`task static` locally,
`--preset` to scope, `--check` for drift). `.github/workflows/_dist_branch.yml`
pushes `dist/` to the `dist` branch on every `main` push, and tag releases
upload the same trees as release assets via `_static.yml`.
