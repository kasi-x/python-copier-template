# Security & compliance posture

Both this template repository and the projects it generates follow the
[OpenSSF Scorecard](https://securityscorecards.dev) checks. This page maps
each Scorecard check to the mechanism that satisfies it.

## Scorecard checks → implementation

| Scorecard check | Risk | Mechanism |
|---|---|---|
| Token-Permissions | Critical | Every workflow declares `permissions: contents: read` (or a narrower job-level scope); checkout steps set `persist-credentials: false` except the workflow that pushes the example repo |
| Pinned-Dependencies | High | renovate's `helpers:pinGitHubActionDigests` converts every third-party `uses:` to a 40-char commit SHA (with the version tag as a comment); `unpinned-uses` is re-enabled in zizmor once the pinning PR lands |
| Dangerous-Workflow | Critical | No `pull_request_target`; `github.event` contexts are never interpolated into `run:` shells (zizmor's `template-injection` audit is enabled) |
| SAST | Medium | zizmor (`.github/workflows/security.yml`) audits the workflow files on every push/PR; pip-audit scans dependencies via the on-demand `audit` task |
| Security-Policy | Low | Root `SECURITY.md`; generated projects get one under the `use_recommended_security` gate |
| Branch-Protection | High | Not enforceable from the repo: enable signed commits, linear history and required reviews in GitHub settings / rulesets |
| Binary-Artifacts | High | `.gitignore` excludes build outputs; no compiled artifacts are committed |

## Repository hygiene files

The "repo layout" items from the OSPS baseline live at these paths:

- `.github/workflows/` — hardened CI/CD (SHA pins, least-privilege, SAST,
  scorecard on `main` + weekly)
- `.github/ISSUE_TEMPLATE/` — structured issue forms with validation
- `.github/CODEOWNERS` — change approval for CI/security-sensitive paths
- `LICENSES/` + `REUSE.toml` — [REUSE](https://reuse.software) license
  compliance (aggregate SPDX annotation; the project license is Apache-2.0)
- `CITATION.cff` — machine-readable citation metadata
- `codemeta.json` — CodeMeta software metadata (JSON-LD)
- `SECURITY.md` — coordinated vulnerability disclosure

## Generated projects

When you generate a project, the `use_recommended_security` gate (default
**yes**) ships:

- the same hardened CI: minimal permissions, SHA-pinned actions (renovate
  keeps the digests current), a zizmor CI job, `SECURITY.md`;
- a generated `tests/test_qa.py` that verifies every module imports, the
  `__all__` public API resolves, and no module imports a missing internal
  sibling (dependency completeness against `pyproject.toml` is deptry's
  static job, run in `task type-check`).

The gate applies to GitHub projects. GitLab projects skip `SECURITY.md` and
the Scorecard workflow (GitHub private advisories and the Scorecard badge
both require github.com); they keep the hardened `.gitlab-ci.yml` instead.

Answer **No** to the gate (on GitHub) to also choose:

- `security_policy` (default yes): include `SECURITY.md`;
- `scorecard` (default no): add the OpenSSF Scorecard workflow + README
  badge. Only meaningful for public repositories — the badge and published
  results require one.
