Title: Let templates declare the packages their Jinja extensions need (and document the uvx/pipx recipes)

## Summary

`_jinja_extensions` entries must be importable **by copier itself**, in copier's own environment. With isolated runners this fails immediately: a bare `uvx copier copy <template>` cannot import a third-party extension package, and there is no way for a template to declare what it needs. Today the only remedies are informal (`uvx --with <pkg> copier ...`, `pipx inject copier <pkg>`, or running copier from an environment that happens to have the package installed).

## Current behavior

```console
$ uvx copier copy https://example.com/template.git dest
Copier could not load some Jinja extensions:
No module named 'copier_template_extensions'
Make sure to install these extensions alongside Copier itself.
See the docs at https://copier.readthedocs.io/en/latest/configuring/#jinja_extensions
```

Source (v9.18.1): `copier/errors.py:125` (`ExtensionNotFoundError`) raised from `copier/_main.py:736-741`. There is no template-side key to declare the required distribution(s) (nothing like `_pre_requirements` exists in 9.18.1).

## Possible improvements (staged, smallest first)

1. **Docs** (small): in the `jinja_extensions` docs section, add the isolated-runner recipes:
   - `uvx --with <extension-package> copier copy ...`
   - `pipx inject copier <extension-package>`
2. **Error message** (small): include those recipes in the `ExtensionNotFoundError` text, since that is where affected users land.
3. **Feature** (needs design discussion — probably better suited for a Discussion first): a `copier.yml` key such as `_pre_requirements: [package-spec, ...]` so templates can declare what copier must have importable. Auto-installing into the user's environment is code execution, so this would need careful scoping (e.g. never auto-install; only validate and produce a precise, actionable error, or require `--trust` to act on it).

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
