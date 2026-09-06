# Choose your strictness level

The template offers a single axis — `strictness` — that controls both how
strictly type annotations are required and how thorough the static-analysis
toolchain is. Pick one level when prompted; it drives the generated
`pyproject.toml`, task-runner tasks and CI configuration together.

## The 4 levels

| Level | Type annotations | Type checkers | Static analysis | Ruff |
|---|---|---|---|---|
| `none` | Not required | None | None | Minimal set (pycodestyle, pyflakes, isort) |
| `basic` | Not required | None | None | Basic set (bugbear, pycodestyle, isort, pyupgrade, ...) |
| `recommended` | Partial (fully-untyped functions pass) | basedpyright + secondary (pyrefly by default) | typos, vulture, deptry (+ `audit` on demand: pip-audit) | `ALL` rules with pragmatic ignores |
| `full` | All functions annotated | basedpyright (strict, `Any` forbidden) + secondary (pyrefly/ty) | Same as recommended | `ALL` rules with minimal ignores |

- **`none`**: pytest + ruff with a minimal rule set. No type checking, no
  static analysis. For throwaway scripts and experiments.
- **`basic`**: pytest + ruff with a curated basic rule set. No type checking.
  Good for small prototypes that still want consistent style.
- **`recommended`** (default): the full toolchain — ruff with `ALL` rules
  (preview enabled, pragmatic `WHYNOT` ignores), basedpyright (always) plus
  your chosen secondary checker (`type_checker`: pyrefly by default, or ty),
  typos / vulture / deptry, driven by your task runner.
  Partially-annotated functions are allowed. Dependency auditing is a
  separate on-demand `audit` task (`pip-audit`, needs network) so offline
  `type-check`/`check`/CI stays green.
- **`full`**: everything in recommended plus strict type checking. `Any` is
  forbidden (`reportAny` etc.), every function must be annotated, and ruff's
  ignores are minimized. When ty is the secondary checker, it additionally
  treats unresolved references as errors. Best for a brand-new project you
  intend to maintain long-term.

## How to Choose

When creating a project, select your `strictness` level when prompted.

- **`none`**: you want fast iteration without thinking about types or style.
  Good for throwaway scripts and experiments.
- **`basic`**: you want consistent style but no type checking.
- **`recommended`** (default): a balanced default. Fits both new code and
  applying the template to existing code.
- **`full`**: you treat `Any` as a code smell and want strict typing from day
  one. Best for a brand-new project you intend to maintain long-term.

## Lessons from practice

- **`full` is for new projects.** Applying strict mode to legacy code can
  produce thousands of errors. Use `recommended` for retrofits.
- **`recommended` survives retrofits.** `analyzeUnannotatedFunctions = false`
  skips fully-untyped functions, so an existing codebase stays green while new
  code gets stricter.
- **`Any` is sometimes necessary.** Libraries like `boto3` without full stubs
  need `Any` (or `types-boto3`). `full` requires the latter.
- **Type checkers are not interchangeable.** `# pyright: ignore[Rule]` is the
  correct comment for pyright-based checkers; mypy's `# type: ignore[code]`
  codes are not recognized.
