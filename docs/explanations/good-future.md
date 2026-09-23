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

## The legal surface

Two field rules name the law that the mechanical defaults sit inside. The
**scraping-law** section (`domain-scraping-law`, on the `scraping_effective`
gate) maps copyright and the EU database right (Directive 96/9/EC art. 7)
against the contract question (ToS) and the unauthorized-access line
(CFAA / 不正アクセス禁止法), with robots.txt as evidence of the operator's
intent rather than an authorization — hiQ Labs v. LinkedIn (9th Cir. 2022)
kept the contract claim alive while the CFAA reading narrowed. Its generated
counterpart is **`LEGAL.md`**, the per-source pre-crawl checklist a scraping
project ships. The **contest-rules** section (`domain-contest-rules`, on the
`oj_code` judges) records that AI-use rules differ per judge and change
(AtCoder bans generative AI during ABC/ARC/AGC except a whitelisted
translation prompt), that the submission is the entrant's own responsibility,
and that rating manipulation and multi-accounting are banned. Both are
enforcement L0: they reach the reader through the generated `AGENTS.md`
appendix, and the ethics-appendix predicate in
`tests/test_render_invariants.py` holds them to the leaf classes that select
them.

## How it is enforced

| Charter rule | Mechanism | Runs in |
|---|---|---|
| feed-first / API-second judgement | `preflight()` (`Preflight.should_use_feed` / `.should_use_api`) | pytest (offline) |
| robots.txt + access + budget refusals | `RobotDeniedError` / `AccessDeniedError` / `BudgetExceededError` | pytest (offline) |
| no direct HTTP calls | ruff `banned-api` | `task lint` + CI lint job |
| dependency license compliance | `task license-check` (pip-licenses) | CI lint job (with `type-check`); never inside offline `check` |
| vulnerability audit | `task audit` (pip-audit) | on demand |
| citation / SPDX metadata | `validate-cff` / `reuse` checks | CI hygiene workflow |
| data governance (DUO/CARE) | `data/DUO.md` / `data/CARE.md` sheets + `test_qa.py` presence asserts + gitleaks `deidentification-salt` | pytest + CI hygiene workflow |
See [the scraping how-to](../how-to/scraping.md) for the engine choices
and [Security & Compliance](security.md) for the Scorecard mapping.
