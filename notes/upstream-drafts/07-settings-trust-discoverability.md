Title: Make the settings trust list discoverable (docs and/or a CLI command)

## Summary

Copier supports permanently trusting templates via a settings file (`trust` list), which avoids repeating `--trust` on every invocation. The feature exists in code but has no CLI surface and is easy to miss in the docs — most users only ever learn about `--trust` from the unsafe-template error, which does not mention the settings alternative.

## Current behavior

- Settings are read from the platform config dir, e.g. `~/.config/copier/settings.yml` (v9.18.1: `copier/_settings.py:106,134`):
  ```yaml
  trust:
    - https://github.com/my-org/
  ```
- The unsafe-feature check consults it (`copier/_main.py:311`, `is_trusted_repository`).
- There is no `copier settings ...` CLI subcommand to view/edit it, and the "consider adding the `--trust` option" hint in the unsafe-template error does not mention that persistent trust exists.

## Expected behavior

- Docs: a clearly findable section showing the `settings.yml` `trust:` format and its prefix-matching semantics.
- Error message: the unsafe-template hint could add "…or list it in your Copier settings".
- (Larger, optional) a small CLI such as `copier settings trust add <url>` so users don't hand-edit YAML.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
