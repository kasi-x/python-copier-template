# Patches

PR-ready diffs authored against `copier-org/copier`. The two frozen,
ready-to-file patches live in `notes/upstream-drafts/patches/` (see
"準備済みのもの" in `notes/COPIER_UPSTREAM.md`); new work lands here.

## Status

| Patch                                                        | Upstream target                              | Status        |
| ------------------------------------------------------------ | -------------------------------------------- | ------------- |
| `notes/.../unsafe-refusal-message-and-exit-codes.patch`      | `errors.py`, `docs/faq.md`, `tests/test_unsafe.py` | Ready (frozen) |
| `notes/.../answers-file-error-hint.patch`                    | `errors.py`, `tests/test_cli.py`             | Ready (frozen) |
| `<area>-<slug>.patch` (this directory)                       | Per `FEATURES.md` item                       | Proposed next |

## Naming

`patches/<area>-<slug>.patch`, e.g. `cli-missing-answers-batch.patch`.
`<area>` is the upstream path area (`cli`, `config`, `docs`, `vcs`, ...),
`<slug>` the change in a few words.

## Creating

From the fork checkout, on a topic branch branched off `master`:

```sh
git format-patch -1 --stdout HEAD > patches/<area>-<slug>.patch
```

## Verifying

```sh
./scripts/verify-patch.sh patches/<area>-<slug>.patch /path/to/copier-checkout
```

It runs `git apply --check`, lists touched files, and suggests the upstream
tests covering them. Run those tests per upstream `CONTRIBUTING.md` before
filing — and file it yourself, in your own words (`AI_POLICY.md`).
