# Why rules sit next to code

Coding agents write much of our code now, but they do not know which laws
apply to it — and neither do most developers. Statutes are long, scattered
across countries, and keep changing; no one re-reads them per pull request.

So this project turns legal requirements into short, sourced rules that sit
where the work happens: in `AGENTS.md`, which people and agents both read,
and as checks in CI. One example carries the whole idea: GDPR Art. 5(1)(f),
Japan's APPI Art. 23, and the FTC's Wyndham case all support the same
engineering rule — *don't put raw personal identifiers in logs*. The rule is
written once, with all three sources attached, and shown to whoever is about
to add a log line.

That is why every project this template generates ships an `AGENTS.md` with
a `Field rules` block plus a `.daimonion.yml` declaring which rules match
the project kind: the `daimonion` linter renders the matching sections from
the reviewed [law-map guidance](https://github.com/politeuma/law-map/tree/main/guidance/sections)
corpus into the guide, and `daimonion scan` matches changed lines against
their triggers before committing. The canonical picture — law-map as the
rulebook, its guidance tree as the prose, daimonion as the delivery, this
template as one entry point —
is the [politeuma architecture diagram](https://github.com/politeuma/.github/blob/main/profile/diagram.md).

These are engineering guardrails with citations, not legal advice. Ask a
qualified professional for compliance decisions.
