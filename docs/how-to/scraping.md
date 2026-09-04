# Polite web-fetching layer

The template can layer **polite web fetching** onto a `cli` project under
the [Good-future charter](../explanations/good-future.md): robots.txt first,
per-host rate limiting, on-disk caching, and a contactable User-Agent. The
charter's rules are enforced by the toolchain (ruff `banned-api`, pytest,
CI) — not left to discipline.

Answering **Yes** to `include_scraping` (asked for the `cli` base only)
generates a `CHARTER.md` plus a fetcher module. Answering **No** to
`use_recommended_scraping` reveals the engine question (`scraping_engine`):
`httpx` (recommended), `scrapy`, `memorious`, `playwright`, or `all`
(every engine at once).

## What gets generated

- `CHARTER.md` — the Good-future rules for this project (respect the
  source, respect the law, respect the commons). Read it before touching
  fetch code.
- `httpx` engine (recommended; also included for `memorious`,
  `playwright`, and `all` as the politeness core they reuse):
  `<pkg>/fetcher.py` — the preflight judge (`preflight()` /
  `PoliteFetcher`) plus offline `tests/test_scraping.py`. Adds the `httpx`
  runtime dependency. The judgement order is fixed in code:
  1. probe feed endpoints (`/feed`, `/rss.xml`, `/atom.xml`, ...) — when
     one answers, fetch the feed instead of the page;
  2. probe API hints (`/api`, `api.` subdomain, `openapi.json`) — when
     found, prefer the API over scraping;
  3. check robots.txt (deny → `RobotDeniedError` immediately, before any
     discovery — a denied page never detours through its feed), probe
     access (401/403 → `AccessDeniedError`: do not work around it), check
     the per-host session budget (`max_requests_per_host`, default 100 →
     over it is `BudgetExceededError`: stop, do not scale up). Probes count
     too, but discovery findings are cached per origin for
     `cache_ttl_seconds`, so the second page on a host costs one HEAD probe
     instead of re-probing 8 feed paths + API hints;
  4. rate-limit (1 req/s per host), serve from the on-disk cache when
     fresh, otherwise GET once and cache.
- `scrapy` engine: `<pkg>/spider.py` — spider starter with `ROBOTSTXT_OBEY`
  + `AUTOTHROTTLE` enforced in `custom_settings`, plus
  `tests/test_scrapy_spider.py` (settings + offline parse). Adds `scrapy`.
- `memorious` engine: `<pkg>/crawler.py` — memorious crawler config
  (rate-limited cached HTTP sessions), plus
  `tests/test_memorious_crawler.py`. Adds `memorious4` — which is
  **AGPL-3.0**, so choosing this engine rewrites the whole project license
  to AGPL-3.0 automatically (see below).
- `playwright` engine: `<pkg>/browser_fetch.py` — headless-Chromium fetch
  for JS-rendered pages (robots precheck reused from the fetcher), plus
  `tests/test_browser_fetch.py` (config defaults only — no browser launch
  in CI). Adds `playwright` (`playwright install chromium` once to run it).
- ruff `banned-api`: direct HTTP calls (`requests.get`, `httpx.get`,
  `urllib.request.urlopen`, ...) are banned outside the fetcher, so every
  fetch stays polite. `.cache/fetcher/` is git-ignored.

## License consequences

- `memorious4` is AGPL-3.0: linking it forces the whole project to
  AGPL-3.0. The template hard-forces `license_effective` to AGPL-3.0 when
  the memorious engine is selected — do not change it back to MIT.
- `task license-check` (`pip-licenses --fail-on`) audits installed
  dependency licenses in CI and fails on copyleft the project license
  cannot absorb. It runs standalone and from `type-check`; like
  `task audit` it needs network (PyPI metadata).

## What is never generated

CAPTCHA-solving helpers (2captcha-style solvers, token injectors) are
deliberately out of scope for every engine. If a site blocks bots, use its
API or ask permission — bypassing bot protection violates the site's terms
and likely the law.
