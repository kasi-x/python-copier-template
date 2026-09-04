# Good-future-python charter

The template's founding idea — **Good-future-python**: generated projects
ship with lawful, network-kind defaults enforced by code, not by
documentation alone. Copyright, scraping politeness, and research ethics
are constraints the toolchain checks (ruff / pytest / CI), so breaking
them fails the build before it reaches review.

## The three respects

**Respect the source.** Every web fetch goes through the polite fetcher
layer (`fetcher.py` or the engine starter), which checks robots.txt before
the first byte, sleeps between per-host requests, caches GET responses on
disk, and identifies the project with a contactable User-Agent. Direct HTTP
calls are banned project-wide by ruff's `banned-api`.

**Respect the law.** The project license stays attached (`LICENSE` +
`license-files`); dependency licenses are audited by `task license-check`
(`pip-licenses --fail-on`) against a copyleft policy the project license
can absorb. AGPL dependencies (memorious) force the whole project AGPL.
CAPTCHA-solving helpers are never generated — bypassing bot protection
violates the site's terms. Personal data follows the same bar as
`DEIDENTIFICATION.md`.

**Respect the commons.** Research software ships citation metadata
(`CITATION.cff`) and SPDX annotations (`REUSE.toml`); datasets carry DUO
use-conditions and CARE governance notes where they apply. Caches,
harvests, and credentials are git-ignored — commit code, never data.

## How it is enforced

| Charter rule | Mechanism | Runs in |
|---|---|---|
| feed-first / API-second judgement | `preflight()` (`Preflight.should_use_feed` / `.should_use_api`) | pytest (offline) |
| robots.txt + access + budget refusals | `RobotDeniedError` / `AccessDeniedError` / `BudgetExceededError` | pytest (offline) |
| no direct HTTP calls | ruff `banned-api` | `task lint` (pre-commit) |
| dependency license compliance | `task license-check` (pip-licenses) | CI lint job (with `type-check`); never inside offline `check` |
| vulnerability audit | `task audit` (pip-audit) | on demand |
| citation / SPDX metadata | `validate-cff` / `reuse` hooks | `task lint` (pre-commit) |
| data governance (DUO/CARE) | `data/DUO.md` / `data/CARE.md` sheets + `test_qa.py` presence asserts + gitleaks `deidentification-salt` | pytest + `task lint` (pre-commit) |
See [the scraping how-to](../how-to/scraping.md) for the engine choices
and [Security & Compliance](security.md) for the Scorecard mapping.
