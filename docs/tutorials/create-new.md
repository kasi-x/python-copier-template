# Create a new repo from the template

## The one-command way

The template ships a small CLI that wraps copier: it decides whether the target
is a new project or an existing one, picks the release to expand, warns about
the files both the target and the template have, and then renders.

```shell
git clone https://github.com/kasi-x/python-copier-template.git   # once
uv run --project python-copier-template python-copier-template new my-project --preset library
```

`--preset library` answers the one question that defines the project family;
every other question keeps copier's default. Drop `--preset` and copier asks
the [whole questionnaire](../reference/questionnaire.md) instead, which needs a
terminal. From inside the checkout the same two forms are
`uv run python-copier-template …` (the console script the package declares) and
`uv run python -m tools.cli …`.

| preset | `project_type` | what you get |
| --- | --- | --- |
| `library` | `library` | a reusable Python package (src/ layout) |
| `cli` | `cli` | a command-line application |
| `web-api` | `web_api` | a FastAPI service (Postgres, Alembic, Prometheus, rate limiting, CORS) |
| `data-science` | `data_science` | notebooks, `data/`, `models/`, `reports/` and the Quarto paper |
| `ros2` | `ros2` | a ROS 2 package (ament_python + rclpy, Humble, apt toolchain) |
| `micropython` | `micropython` | firmware (esp32 by default) beside the CPython dev toolchain |
| `online-judge-atcoder` | `online_judge` | an AtCoder workspace driven with `oj` + `acc` |

Each preset is a file under `presets/`: it names only the answers that define
the family, so adding a preset of your own is a two-line YAML file. For a
fixture that sets every option instead, copy `example-answers.yml` from the
template root — it is what the template's own CI renders, and it works as a
`copier copy --data-file` answers file.

Other options:

- `--ref <ref>` expands another revision (`--ref HEAD` is the working tree of
  the checkout). **No `--vcs-ref` is needed**: without it the CLI expands this
  fork's newest release tag, and only falls back to the default branch — saying
  so — when that tag carries a different questionnaire.
- `--dry-run` renders the plan into a temporary directory and reports what the
  target would receive; nothing is written.
- A target that already has files is not copied into but
  [adopted](./adopt-existing.md): the files you already have are left alone
  (collisions are skipped and reported), the infrastructure you are missing is
  added, and the run rolls back if any of your files changed anyway.

Exit codes follow the other tools in the repository: `0` success, `1` a failed
render, `2` an invalid request (unknown preset, `copier update` needed, no
terminal for an interactive run), `3` the target belongs to another copier
template.

## The raw copier command (advanced)

Once you have followed the [installation](./installation.md) tutorial, you can
also drive copier directly:

```
git init --initial-branch=main /path/to/my-project
# $_ resolves to /path/to/my-project
uvx copier copy --trust \
    https://github.com/kasi-x/python-copier-template.git $_
```

No `--vcs-ref` is needed here either: copier then expands this fork's **newest
release tag**, and since the 6.0.0 fork detach that tag is the fork's own
release. Pass `--vcs-ref=6.0.0` (or another release tag) only to pin an exact
release and make the generation reproducible. Add `--defaults` to accept every
default, and `--data-file example-answers.yml` for a fully specified run.

This will:

- Ask some questions about the project to be created (each area first asks
  whether to use its [recommended settings](../reference/questionnaire.md))
- Expand the template with the answers give
- Record the answers in the project so they can be used in later updates
- Create a git repository if the directory is not already one

## Committing the results

You can now check what the template has created, tweak the results if desired, [lock the requirements](../how-to/lock-requirements.md), and commit the results:
```shell
$ cd /path/to/my-project
$ uv sync
$ git add .
$ git commit -m "Expand from python-copier-template x.x.x"
```

## Uploading to GitHub

You can now [create a new blank project on GitHub](https://github.com/new). Choose the same GitHub owner, repo name and description that you answered in the questions earlier. GitHub will now give you the commands needed to upload your repo from GitHub.


## Getting started with your new repo

You can now [set up the repo](../how-to/setup-repo.md), [set up a dev environment](../how-to/dev-install.md), and then follow some of the other [how-to guides](../how-to.md).
