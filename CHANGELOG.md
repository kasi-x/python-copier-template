# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Bug Fixes

- rename the codex secret CODEX_TOKEN -> GFCODEX_TOKEN (81b6e29)

- drop the secret entirely -- the codex is public (1ae8f82)

- give the reusable _tasks workflow a timeout (7af8679)


### Documentation

- ethics-as-external-source design note (f6d2981)

- branching model -- code / vendored content / release (98dd692)

- name the ethics repo good-future-codex (2a27be2)

- contract-only registry QA, codex drafts, CONTRIBUTING note (5822d59)


### Features

- scraping mode, OJ task recipes, and ethics/legal coverage (5b036d4)

- vendor _shared/ethics/ from good-future-codex with drift check (c66a2a8)

- export the flag vocabulary + wire the placement contract (ab2b5fd)

- vendor MANIFEST.yml + add the manifest/flags/registry contract check (35339e4)

- ship the regions table to web_api renders (8076135)

- add list_presets tool (ed249be)


### Miscellaneous Tasks

- archive resolved bug notes and re-record the test ledger (48029b1)


### Refactor

- generate the appendix include chain from the registry (4ada3f9)


### Testing

- render every shipped preset end to end (857af60)


### Style

- reword mis-paired to clear the spellchecker (91c6d1d)


## [6.1.0]

### Bug Fixes

- keep the 2-minute witness batch runner out of the edit loop (25bbb80)

- refuse a taskfile append that leaves invalid YAML (06d88ab)

- stop the logging_setup wrappers from emitting a leading blank line (b9aaf65)

- attribute conventional-commit enforcement to CI, not a hook (fd6bcc8)

- diagnose a malformed target instead of raising or blaming (cfc4f41)

- mirror the models/ un-ignores into the rendered gitignore (7d7b6e8)

- read the derived names from the render's own answers (e62d0e8)

- TypeError, not RuntimeError, for a non-mapping answers file (35f8e5a)

- let the fixture registry take the fixtures' own types (63fa251)

- keep the generated qa module formatted at every name length (0673309)

- keep the leaf dest out of the secret scanner's grammar (7439a33)

- read the python-floor pin from the macros source (de06ece)

- gitlab renders get gitlab urls, not hardcoded github ones (4a018b2)

- a throttled PyPI lookup is an unresolved check, not removed drift (ca67b80)

- the rehearsal records the described revision, not a raw sha (cbbf902)

- pin the version comments to the tags that point at them (b8d2e9c)

- pass the audit flag as the keyword-only argument it became (fadecdb)

- resolve include targets against the watched files, and sync the doc counts (3945fa9)

- gitleaks-action v2.3.9 -> v3.0.0; retarget the just pin probe (000a2d6)

- Japanese pydocstyle ignores, torch index on the GPU axis, deptry web_api gating + the sphinx regressions they exposed (7d6c2e2)

- the license gate is armed for every offered license, not 13 of 49 (4ae54b8)

- the update rehearsal checks out its release tags (2e410d3)

- the composite cannot check out the repo it lives in, and the zizmor pins must be a released pair (9b13f95)

- the domain variant list keeps list[str] without tripping RUF025 (3da5f17)

- the cpp flavour stops shipping pyproject orphans -- and the untested paths get their first exercise (7b294b2)

- the slides theme and the CSL actually render -- first real quarto run caught both (2a1b544)

- the example identifiers pass typos on both sides of the render -- found by act (ca5f8aa)

- the vendored clean.scss ends with exactly one newline -- the hygiene EOF check caught it on the first real CI run (8465713)

- the fairness acronyms are whitelisted, and the identifier-rewrite hazard is written down (6013e39)

- the spellchecker goes report-only -- fix never runs typos -w (8bd6338)

- the hazard's own example tripped the checker -- reworded, typos clean (e60b45f)

- generated .gitignore ends with exactly one newline on every include branch (7a13884)

- scheduled-check grants contents:write to the docs reusable call (bd8db87)

- strip trailing whitespace from vendored clean.scss (5dd6fce)

- skip leaves whose answers are invalid at the base ref (cac4260)

- strip trailing whitespace from generated text files (6ca255a)

- retry the transient copier tempdir race; re-record tier ledger (a8c876f)

- mcp floor 2.0 -> 2.0.1 (2.0.0 final was never released) (958d0d7)

- upstream-fork check compares against a reviewed marker, not HEAD (594a988)


### Documentation

- pin the verification architecture and its growth rules (6ce577d)

- make the README a 120-line entry point (1981f36)

- record section 25/26 and check off the items the day's commits landed (c28fefb)

- spell unparsable the way the typos dictionary prefers (f9c637a)

- record the section 26.4 outcomes, spike verdicts and remaining items (d1aaab5)

- record the §27.7 batch — five branches, five outcomes (10747dc)

- V5 landed -- the merge contracts are an artifact (f9b1b31)

- settle §27.7-7 — pixi venv sharing rejected, randomly nightly adopted (d29e05b)

- the discord bot how-to, the layer's second implementation (b275e98)

- record the bot layer's first slice in section 4 (dabc7ac)

- follow the split in the prose that named test_example.py (95e62fe)

- audit the section 1-26 checkboxes against the tree (dcf546c)

- close section 27.7 item 4 with what landed (640427a)

- close the two MCP items the run_tests and support slices finished (11fe52a)

- the silent-override visibility item is done (f1218e9)

- the macros extraction is done (2ef2aab)

- the section-18 structural batch is done (bfd3ce1)

- the raw-vs-effective rule, and the README gate it was hiding (212cd59)

- section 18 is complete -- predicates named, rule written down, gitlab urls fixed (3bcbede)

- wire the predicate classifier into the workflow and the cost ledger (b2bc53e)

- section 18.5 -- the predicate classifier makes the unification permanent (c60bc52)

- the extension runbook -- platforms, layers, gates (398c779)

- section 18.6 -- growth-resilience contracts (068e5e3)

- section 18.7 -- the render twin turns byte-identity proofs into a command (8453f37)

- tell the template what you want -- the inverse template's page (21947bb)

- section 18.8 -- the update rehearsal, every configuration every night (7d5d6af)

- the drift matrix goes public -- and the leaf-count references stop lying (59ee48b)

- the paper scaffold gets its documentation -- and the generated README admits it exists (ed2392e)

- the biggest layer gets its how-to -- and every index page stops hiding pages (104726b)

- the feature list admits the bots, the ethics appendix and the drift page (701bec7)

- the first real CI run is green -- the EOF check caught the vendored scss, as designed (1a32efd)

- §31 -- scheduled-check startup_failure fixed, upstream drift reviewed (16e515f)

- record the two drift fixes the revived weekly check surfaced (66f45e4)

- §31.5 -- weekly check fully green after drift fixes (e31ff44)

- fix six dead links the weekly linkcheck flagged (69a551b)

- §31.6 -- periodic linkcheck green, all scheduled workflows healthy (fb16b3d)

- record the upstream-fork marker fix and mcp floor bump (e1cd3fb)


### Features

- --jobs N for the witness runs (113.8s -> 10.2s) (650b78e)

- make the template's own server usable while editing it (36b7fc7)

- journal the transaction so a crash is recoverable (85af34d)

- derive the generated CONTRIBUTING's commands from the task model (031be19)

- offer the license set as bare SPDX identifiers (75f5595)

- account for the excluded leaves and detect a stale jsonl (bb6a9e5)

- crash hooks for the rollback and recover paths (23a8434)

- the include_bot opt-in layer with its own gate (734844a)

- the discord platform as the second long-running layer (bbaa98e)

- add the Slack platform (Socket Mode) to the bot layer (814985a)

- serve the declared support contract as template://support (da4ef14)

- add run_tests, the suite tiers in run_batch's verdict shape (b645829)

- add the line platform to the bot layer (2c6425a)

- say the two silent answer overrides out loud at generation (f3c9293)

- the predicate classifier -- condition-site inventory, 225-leaf evaluation and the Z3 free-space oracle (e84772c)

- UPDATE_TIERS rewrites the doc's tier counts with the ledger (9e5bdeb)

- the witness leaf space gets a declared budget (LEAF_BUDGET) (16a1c61)

- the question dependency graph -- where new internals may live (0b11e5a)

- the render twin -- prove which leaves a template change can affect (aa11c5b)

- answers_for -- the inverse template, features in answers out (a57ba7d)

- recommend_answers -- the inverse template on the MCP surface (fd5e246)

- the update rehearsal -- every configuration, every night (667c552)

- vary the integrations details -- docker + mcp joins the leaf space (a515149)

- invalidate renders per leaf -- the consumed bytes, not the whole tree (e750668)

- land the §28 audit closes and the Gmail bot platform (7dfc56d)

- the bot platforms join the leaf space -- 228 to 234 leaves (395516d)

- the L1/L2 rungs land, and the questionnaire guard stops crying wolf (7702ca5)

- the dependency and src/ lists become editable structured answers (048d2de)

- the domain traits land, and multi-select stops being untested (87e5b5c)

- personal data is asked, not guessed, and absorbs the special categories (e996a35)

- how the project ships decides whose rules apply, and the EU CRA lands (b299af2)

- the protection-term jurisdiction table lands -- lang/ gets its first dictionary (55f4b2c)

- the guide ships everywhere -- AGENTS.md goes constant, and PKI-chain boards its channel (0258626)

- the shared-authorship groundwork -- overdue reviews redden, the governance split is written down, and the section runbook exists (edd6f9c)

- every active section carries a concrete example -- and the examples are format-guarded (0c0bd3b)

- add Codeforces / Kattis / other judges with per-site CI and guide (67a3964)

- generated ci.yml subscribes to merge_group (upstream 72da24d) (928d681)


### Miscellaneous Tasks

- write the coverage xml under .cache (121b221)

- skip the render matrix for docs-only changes (f4838b7)

- verify the adopt crash-atomicity model with quint (7901cbc)

- grant the release job the contents write it needs (c8d8813)

- drop the dead apt cache key from the docs job (dde3dcd)

- act — run the workflows locally before pushing (c671b5b)

- drop the reverse closure the leaf-scoped lookup no longer uses (6d105ad)

- ignore .zcode tool-cache directory (root + template parity) (936b4bf)


### Refactor

- extract the when model and prove it against copier (a688a64)

- one file for what a leaf must satisfy (e89e410)

- move run_pipe and make_venv to a support module (a30747e)

- drop the pre-bot .env.example filename (8745f12)

- one source for the suite's Project Details (75e3254)

- drop the answers example-answers.yml inherits from the questionnaire (692e426)

- one source for the run prefix and the python-version triple (c586ed9)

- one pkg_dir path per package module instead of two trees (bd93786)

- base+append the dev dependencies instead of two duplicated branches (b414588)

- extract the dependencies one-liner and the deptry table into _shared partials (beecc95)

- name the two OJ predicate forms the template kept re-deriving (1dbd8ec)

- name the autodoc-sites predicate -- api_docs_zensical (19e5530)

- the naming report keeps classes that already have a name (dffb061)


### Testing

- guard the marker contract and record what each tier runs (641f830)

- content predicates for a 27-leaf sample (bc2b644)

- budget the edit loop and age the cost ledger (40de063)

- prove --jobs overlap by handshake, not by stopwatch (ec64787)

- re-record the ledger after the merge regression test (6ba9777)

- a Hypothesis state machine over the adoption driver (V4) (a4275e3)

- prove --jobs overlap against the clock, not against another line (7291c3f)

- finish the stateful machine (V4) (850cb12)

- re-record after the two merge fixes (ca394ef)

- record the merged tree's collected sets (2144a6f)

- declare the adopt-time merge contracts as an artifact (V5) (2a90708)

- run a nightly randomized-order seed job (pytest-randomly) (a712fc6)

- record the merged tree's collected sets (771/827/8) (f4a9352)

- the leaf space 205 -> 225 and the layer's verification (17d2a8f)

- split test_example.py by questionnaire axis (29344b3)

- re-record the ledger after the split, the slack platform and the format fix (acb9af3)

- follow the dest fix in the ledger and record the -n auto flake (19345d3)

- name what the full tier's docs build said and left behind (9dbf7f9)

- import z3 loudly instead of skipping when it is missing (aec9b0f)

- ledger and doc table after the line platform (5515dfd)

- refuse answers that merely restate the questionnaire's default (cd40b56)

- re-record the tier ledger for the two oj-predicate guards (18342b7)

- record the merged tree's collected sets (841/901) (1d6bd01)

- the fast-tier rot-guard -- every unconditional equivalence accounted for (5a23be8)

- contracts for the tools/ dependency layers (cc0d3fd)

- the automated UPDATE_TIERS sync after the layers merge (7a67637)

- retry the generated docs build without a file watcher; link the local-CI how-to (485f361)

- record the collected sets for the pushed tree (a884426)

- skip cases unrenderable at the released ref (51885d1)


### Style

- ruff format -- two blank lines before _rehearse_job (d6df840)


## [6.0.0]

### Bug Fixes

- Move to long-form Github URLs (#260) (1c71289)

- Remove docs references to test outputs (#267) (2000007)

- Handle pinned sha versions of Python in the install_requirements action (#268) (dfe17b1)

- Remove need for --trust (#271) (d48d075)

- Deduplicate jobs from generated workflows (#272) (92dc82c)

- Enable subprocess coverage (#289) (ace29b9)

- Remove requirement for buildkit (#290) (2aa1177)

- run uv lock before pushing example code (#292) (c8fc7b7)

- make sure pyright is happy with external deps (#296) (73c31e3)

- container now copies managed python into runtime (#297) (7659ef5)

- VSCode garbled REPL (#298) (23f280c)

- Remove codecov token (#312) (39120c6)

- Add application to component_type choices (#314) (294dc13)

- Better handling of large files (#317) (c52b391)

- tox / pyright python environment (#320) (d220299)

- Force uv to manage python itself (#335) (1dfadc8)

- copier should not be a dev dependency (#364) (718a485)

- disable Renovate Dockerfile base-image updates in downstream repos (#365) (909a4b5)

- repair test_example_repo_updates's copier-update invocation (3ed9dfe)

- resolve three CI-only failures found while verifying the push (639c24e)

- clear basedpyright warnings so type-check exits green (d213cde)

- address generation-session bug reports (bugs.md) (c4f725c)

- resolve reported generation bugs; replace pre-commit with CI hygiene workflow (0287df4)

- harden hygiene workflow checks against symlinked and template sources (987abac)

- pin setup-just to just 1.58.0 (zizmor unpinned-tools) (87058c2)

- first CI-run fallout — lint scope, hygiene uv, mcp floor false positive (7069b0b)

- run cffconvert via uvx — the cffconvert-github-action v1 tag is broken (df1669d)

- generated projects work outside git via setuptools-scm fallback (52f4aec)

- make/poe/invoke/duty lint tasks actually execute (runtime audit) (5737615)

- extend the render/lint matrix — agent help line, gitlab-ci EOF, runner variants (5131c53)

- transitional --with for updates crossing the extensions removal (dad04cc)

- adopt mode skips the REUSE scaffolding (protected LICENSE) (2fce244)

- poetry projects ship a static version and no placeholder lock (ad60af4)

- drop the unused adoption arg vulture flags in _confirm_merges; docs touch-ups (3ed4f0b)

- grant contents:read to the pypi reusable-call job (81a482e)

- create the apt archives partial directory before the cached graphviz install (8bbc42a)

- register actions/cache in the generated renovate hygiene rule (7bca190)

- drop the broken graphviz deb cache from the docs job (162e44d)

- register the imported encoder module and pin the projected gates (3b9f9d5)

- make the witness leaves' own checks pass (ce94f77)

- clear the repo's own type-check on the new tooling (335cde9)

- pin the mimxrt stubs series, wrap the flat agent help, correct the OJ docs page (4d9b25b)


### Dependencies

- update github actions (#351) (f458740)

- update pre-commit hook gitleaks/gitleaks to v8.30.1 (#352) (dfb14a4)

- update softprops/action-gh-release action to v3 (#362) (f889d83)

- update pre-commit hook pre-commit/pre-commit-hooks to v6 (#361) (d53e98a)

- update astral-sh/setup-uv action to v8 (#354) (2ea9db6)

- update github artifact actions (major) (#360) (cfcde41)

- update docker/setup-buildx-action action to v4 (#359) (5a3129c)

- update docker/metadata-action action to v6 (#358) (c97e1fc)

- update docker/login-action action to v4 (#357) (38d5b02)

- update docker/build-push-action action to v7 (#356) (89ce177)

- update actions/checkout action to v7 (#353) (03ac4ca)

- update codecov/codecov-action action to v7 (#355) (37b5344)

- update astral-sh/setup-uv action to v9 (#363) (a0cac98)

- lock file maintenance (#366) (b8caef5)

- lock file maintenance (#367) (4ee6984)

- lock file maintenance (#368) (f39321a)

- update astral-sh/setup-uv action to v10 (#369) (72fb4e1)

- update astral-sh/setup-uv action to v10.0.1 (#370) (db53298)

- lock file maintenance (#371) (7d4fecf)

- lock file maintenance (#375) (e3910cf)

- lock file maintenance (#377) (092aa5b)


### Documentation

- Document repo creation method (#275) (5294bde)

- explain LOG_FORMAT=json for cloud/log-aggregator deployments (80123c9)

- note Render/Railway/Vercel's level+message log convention (f6a6010)

- mark online_judge / kaggle TODO items done and record the oj-driven design change (8199e70)

- update TODO with the 2026-09 questionnaire/web_api restructuring (bd9c349)

- add Strategy.md for error-detection and upstream-tracking mechanisms (922bc3b)

- reformat an embedded code snippet in Strategy.md (ruff format style) (fea050a)

- record v1.0 fork-detach and clean-history publish plan (3cb6878)

- record remaining issues after Strategy.md implementation (816fc43)

- add 7 new template issues from kasi-x publish pipeline (0ddca97)

- pixi guide, upstream contribution drafts, governance, bug-ledger refresh (2696aea)

- record CI-run triage and the zizmor latest-float lesson in TODO (3ec74ad)

- record the gh-pages Pages-source fix and the verified docs URLs in TODO (cff6672)

- record the setuptools-scm fallback fix in the lint guide and bug ledger (950be3f)

- record the setuptools-scm fallback fix in notes/bugs.md (1013845)

- add ready-to-file copier contribution patches and filing procedure (bfc50a0)

- adoption-mode spec (P0 --skip flow documented) (3f1efe6)

- adopt-existing — document the infra-only --skip flow (adoption spec P0) (ff3713d)

- refresh the improvement plan (W9 rework, W10/W11) and TODO section 22 (6b73e3f)

- record the W-P remnant decision (native loader stays; questionnaire serves the JSON model) (e84922b)

- record the inherited tag snapshot and the W0 execution procedure (deletion pending user approval) (6fbb3fa)

- record the graphviz cache removal in TODO W7 (322254f)

- mark W2 done in TODO 22 (macro aggregation noted as remaining polish) (0441995)

- drop the --vcs-ref premise now that the fork tags its own releases (89b7cf5)

- generate the questionnaire-derived blocks from the question model (2d6a6c9)

- record W1/W3/W5/W6, the witness-driven fixes and the open findings in TODO 22 (fc2994b)

- record the 6.0.0 tag re-point and the CI-green release commit (336d7ce)

- declare the support matrix from the witness coverage (92c0066)

- record W3's audit, W4 and the residual fixes in TODO 22 (d5802e3)


### Features

- Publish debug container image and account-sync sidecar (#251) (76c187c)

- Enable pep8-naming ruff rules (#283) (9d544a5)

- Add a global cache for uv, pre-commit and global venv (#307) (17daee5)

- Add renovate (#311) (b4da80f)

- Add support for python 3.14 to copier template (#341) (aed03d7)

- replace tox with selectable task runner and simple license mode (d1ccdcb)

- add opt-in FAIR metadata with CITATION.cff, REUSE and DUO/CARE sheets (4127f5c)

- add Confidential license choice and harden Proprietary text (7cf70f9)

- ship data governance & restricted-data sharing kit for data_science (beff0cf)

- make the logging library selectable (structlog/loguru/picologging/logging) (f5beab0)

- use Cloud Logging's severity/message/time field names when cloud_provider=gcp (1ab3d80)

- add micropython project type (4d0a290)

- micropython freeze build, maintenance tooling, and ty/pyrefly secondary checker (bd4a304)

- add online_judge project type, move kaggle out of data_science (505a768)

- MCP layer integration, security/compliance baseline, and Dockerfile dedup (afc3594)

- turn web_api into a working FastAPI scaffold (TODO item 6) (11ec617)

- split copier.yml questionnaire into genre fragments (5e67369)

- make web_api a top-level app/ package (drop the <pkg> library) (619a91b)

- allow base + layer combos (data_science + web_api, web_api + MCP) (cdfeb31)

- add web scraping layer, AGENTS.md, upstream-check consolidation, CTF/pyproject cleanup (085b157)

- add drift detection and periodic full checks (a82f9a4)

- usability pass — update guidance, typos auto-fix, tidy repo root (ef15271)

- drop the copier-template-extensions dependency — plain uvx works (eba70ae)

- adopt mode (P1) — existing_project answer protects the adopter's files (16b2c4f)

- fresh-project next-steps report (U1 gap fill) (5e9984f)

- adopt mode P2 — adopt_protect multiselect and per-file protection (da984b2)

- adopt-mode P2 (adopt_protect multiselect) + adoption/batch/detect/questionnaire/MCP tooling (1685761)

- enumerate Z3 witness leaves for the questionnaire (9aba3b8)

- one command to start or adopt a project, plus presets (bf5d715)


### Miscellaneous Tasks

- Remove check workflow and filter on branch name (#253) (e07bbe8)

- Enforce Conventional Commit PR titles (#255) (71c6bb0)

- Update pre-commit-hooks to v5.0.0 (#242) (242d289)

- Bump softprops/action-gh-release from 2.2.0 to 2.2.2 in the actions group (#228) (99dc4b6)

- 241 release pipeline does not depend on tests (#257) (a7b863a)

- remove `trust` now that HEAD does not require trust. (#276) (07b2169)

- add pre-commit hook, config with sealed-secrets allowlist, and tests (#287) (32c6c7b)

- Bump the actions group with 5 updates (#293) (ae18808)

- Add cron to make issue for supporting new version of Python (#313) (70860ef)

- Remove reference to transferring into DiamondLightSource (#330) (47dcc42)

- Use Ubuntu 26.04 (resolute) for devcontainer (#345) (7fa903a)

- Update devcontainer to use resolute image (#374) (01c35b3)

- clean up deptry/typos findings surfaced by task check (bc3c8e7)

- make the example regeneration work non-interactively (3fcb330)

- ignore zizmor self-repository advisory for local reusable refs (87e3525)

- split the test tier by markers and run the heavy tier nightly (fdb724a)


### Performance

- render each answers/template pair once per session (d678957)


### Refactor

- Convert to use `uv` (#248) (ed290c8)

- Reformat link table template in README (#322) (dc6564e)

- remove dead code of debug container (a589896)

- remove dead code of debug container (#347) (18a7ecf)

- ground restricted-data sharing in CARE traceability (c809588)

- ask "use recommended settings?" per area instead of one detail_level toggle (b186ef8)

- migrate docs to Zensical and update devcontainer / tests (0065bcf)

- order copier.yml questions by dependency, DRY repeated conditionals (d1a5df4)

- rename template/ conditional paths to the new named variables (eca2c2f)

- single declarative model + per-runner macros, byte-identical renders (0c442ef)


### Testing

- enforce single trailing newline in rendered files; document .jinja rules (e0f1333)

- pin the pixi native task set (lint/fix/type-check/test/check + typos) (ae2b17f)

- structural bug prevention — task-runner conformance and lint-execution guards (6cc9f38)

- mark the venv-building runner tests heavy (5a3b4a1)

- update-path matrix and a questionnaire migration guard (49727f1)

- execute the witness leaves and record the coverage ledger (ce6b486)

- replace text-pinning asserts with behaviour checks (662cd24)


### Style

- format the transitional update test line (e2a210e)

- split the over-long pyproject template constant (58458b5)



