# First 10 minutes

From nothing installed to a green project: three commands, then read one
file. If any step fails, the <lt-m v="["/>installation tutorial<lt-m v="](installation.md)"/> has
the troubleshooting table.

## 0–2 min: prerequisites

<lt-m v="["/>uv<lt-m v="](https://docs.astral.sh/uv)"/> and <lt-m v="["/>git<lt-m v="](https://git-scm.com)"/>. Check:

```shell
uvx copier --version && git --version
```

## 2–5 min: generate

No clone needed — this expands the newest release tag:

```shell
uvx --from git+https://github.com/politeuma/architekton-py.git \
    architekton-py new my-project --preset library
cd my-project
```

For an existing repo instead, run the same command inside it — it switches
to adopt mode and leaves your files alone
(<lt-m v="["/>adopt tutorial<lt-m v="](adopt-existing.md)"/>).

## 5–10 min: run the checks

The recommended path renders `just` as the runner:

```shell
just check   # lint + type-check + test, the same tasks CI runs
```

Green means the toolchain works on your machine. The first week stays quiet
on purpose: the `legal-check` task only reports findings (pass `--strict`
to fail on them), and hygiene CI checks the PR title only — land with
squash-merge and individual commit messages stay free-form. If even the
recommended gates feel like too much at once, `--preset bare` renders the
same library without the optional infrastructure extras. From here:

- read `AGENTS.md` — it is the agent guide <lt-m v="*"/>and<lt-m v="*"/> the human command list;
- <lt-m v="["/>create a new project<lt-m v="](create-new.md)"/> for presets, answers files, and
  pinning a release;
- <lt-m v="["/>why rules sit next to code<lt-m v="](../explanations/why-rules-next-to-code.md)"/>
  for what the `Field rules` section of that `AGENTS.md` is doing there.
