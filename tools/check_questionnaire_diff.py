#!/usr/bin/env python3
"""Guard the questionnaire against breaking the `copier update` path.

A generated project records its answers in `.copier-answers.yml`, and
`copier update` replays the questionnaire: the recorded answers are carried
over to the new template version by question *name*. When a question is
removed, renamed, or keeps its name but changes its `default`, that replay no
longer reproduces the project's answers -- the recorded answer is dropped (or
silently re-interpreted), so the update produces a project that no longer
matches the questionnaire it claims to follow. Copier's escape hatch is
`_migrations`: an entry that did not exist at the version the project was
generated from runs during the update and can rename or translate the recorded
answers.

This tool compares the newest release tag's `copier.yml` against the working
tree's and exits 1 for every removal / rename / default change that no new
`_migrations` entry covers, printing `[MISSING MIGRATION] <name>`. A `when`
change is reported for review but does not fail the run: it decides *whether* a
question is asked, and copier replays it rather than dropping an answer (a
`when` that turns `false` would hide an internal variable again, which is a
different, template-internal concern).

Both configurations are read with copier's own loader, so `!include`d
fragments are merged exactly the way copier merges them and the comparison is
over the real questionnaire, not over the YAML layout. The base side is
extracted from a git archive of the release tag, so the tool runs offline and
never touches the working tree.

Migrations are matched by set difference against the base release, not by
PEP 440 ordering: a change introduced after the release has to be covered by an
entry the release does not carry yet, and copier gates each entry by its own
`version` (`template.version >= entry.version > project.version`). Ordering is
deliberately left to copier instead of being re-implemented here -- the release
a change is recorded for is the *next* one, which does not exist yet for the
guard to compare a version against. An entry the base release already shipped
therefore cannot cover a change introduced after it, however new its version
looks; text and `--json` output name the covering versions so a reviewer sees
what the change was recorded for.

Usage:
    python tools/check_questionnaire_diff.py                 # newest tag vs working tree
    python tools/check_questionnaire_diff.py --base 5.4.0    # against another ref
    python tools/check_questionnaire_diff.py --json          # machine-readable
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copier._template import filter_config
from copier._template import load_template_config
from copier._vcs import get_latest_tag
from copier.errors import CopierError

TOP = Path(__file__).resolve().parent.parent
CONFIG_NAME = "copier.yml"

# The absolute path (readable failure when git is absent, and S607-clean).
GIT = shutil.which("git") or "git"

# Where copier's loader documents its include semantics: patterns are globs
# relative to the config file, so the whole tree has to be materialized, not
# just copier.yml and questions/.
NO_RELEASE_TAG = "HEAD"


@dataclass(frozen=True)
class Finding:
    """One questionnaire change copier cannot replay on its own."""

    name: str
    change: str  # "removed" | "renamed" | "default"
    detail: str

    def as_dict(self) -> dict[str, str]:
        """Serializable form used by --json."""
        return {"name": self.name, "change": self.change, "detail": self.detail}


def _git(repo: Path, *args: str) -> bytes:
    # args is a fixed literal argv built by this script, and the repository is
    # the one this file lives in; never shell, never user input.
    result = subprocess.run(  # noqa: S603
        [GIT, "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout


def release_tag(repo: Path) -> str | None:
    """The newest release tag, or None when the repository has none.

    This is copier's own resolution (PEP 440 order, prereleases skipped), i.e.
    the ref `copier copy`/`copier update` use when no `--vcs-ref` is passed --
    the same release this guard has to hold the update path to.
    """
    ref = get_latest_tag(str(repo))
    return None if ref == NO_RELEASE_TAG else ref


def load_ref_config(repo: Path, ref: str) -> dict[str, Any]:
    """The `copier.yml` of `ref`, with its `!include`s resolved by copier."""
    with tempfile.TemporaryDirectory(prefix="check-questionnaire-") as tmp:
        dest = Path(tmp)
        blob = _git(repo, "archive", ref)
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            # Only the tree's own regular files and directories: symlinks (the
            # generated project's conftest.py is one) carry no YAML.
            members = [member for member in archive.getmembers() if member.isfile() or member.isdir()]
            # The members come from this repository's own object store, and
            # filter="data" refuses to write outside `dest` regardless.
            archive.extractall(dest, members=members, filter="data")  # noqa: S202
        return load_template_config(dest / CONFIG_NAME)


def load_working_tree_config(repo: Path) -> dict[str, Any]:
    """The `copier.yml` as it is on disk right now."""
    return load_template_config(repo / CONFIG_NAME)


def questions(config: dict[str, Any]) -> dict[str, Any]:
    """The question entries, normalised the way copier normalises them."""
    return filter_config(config)[1]


def compare(base: dict[str, Any], head: dict[str, Any]) -> list[Finding]:
    """Removals, renames and default changes between two question sets.

    A rename is a removal whose body survived under a new name; it is reported
    as such because the recorded answer needs the same migration either way.
    """
    added = [name for name in head if name not in base]
    findings: list[Finding] = []
    for name, body in base.items():
        if name not in head:
            renamed = [candidate for candidate in added if head[candidate] == body]
            if len(renamed) == 1:
                added.remove(renamed[0])
                findings.append(Finding(name, "renamed", f"renamed to {renamed[0]}"))
            else:
                findings.append(Finding(name, "removed", "removed"))
        elif body.get("default") != head[name].get("default"):
            findings.append(
                Finding(name, "default", f"default: {body.get('default')!r} -> {head[name].get('default')!r}")
            )
    return findings


def when_changes(base: dict[str, Any], head: dict[str, Any]) -> list[dict[str, str]]:
    """Questions whose condition changed, for review only (see module doc)."""
    return [
        {"name": name, "from": repr(base[name].get("when")), "to": repr(head[name].get("when"))}
        for name in base
        if name in head and base[name].get("when") != head[name].get("when")
    ]


def new_migrations(base_config: dict[str, Any], head_config: dict[str, Any]) -> list[Any]:
    """`_migrations` entries the release under comparison does not carry yet."""
    before = base_config.get("_migrations", [])
    return [entry for entry in head_config.get("_migrations", []) if entry not in before]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail on questionnaire changes a copier update cannot replay.")
    parser.add_argument(
        "--base",
        metavar="REF",
        help="compare against this git ref (default: the newest release tag)",
    )
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    return parser.parse_args(argv)


def _migration_labels(entries: list[Any]) -> str:
    """How a covering migration is named in text output: by its version."""
    return ", ".join(
        str(entry["version"]) if isinstance(entry, dict) and "version" in entry else "<unversioned>"
        for entry in entries
    )


def _report_text(ref: str, findings: list[Finding], when: list[dict[str, str]], covered: list[Any]) -> None:
    print(f"questionnaire diff: {ref} -> working tree ({CONFIG_NAME})")
    if findings and not covered:
        # `[MISSING MIGRATION]` is the failure marker (same convention as
        # tools/check_upstream.py's `[DRIFT]`): a green run never prints it.
        for finding in findings:
            print(f"[MISSING MIGRATION] {finding.name} ({finding.detail})")
        print("Add a _migrations entry newer than this release for each [MISSING MIGRATION] line, e.g.:")
        print("    _migrations:")
        print("        - version: <next release>")
        print("          command: ...")
    elif findings:
        print(f"covered by new _migrations entries: {_migration_labels(covered)}")
        for finding in findings:
            print(f"    {finding.name} ({finding.detail})")
    for change in when:
        print(f"[CHANGED WHEN] {change['name']} ({change['from']} -> {change['to']})")
    if not findings and not when:
        print(f"No breaking questionnaire changes since {ref}.")


def _report_json(
    ref: str, findings: list[Finding], when: list[dict[str, str]], covered: list[Any], *, ok: bool
) -> None:
    print(
        json.dumps(
            {
                "base": ref,
                "target": "working tree",
                "missing_migrations": [finding.as_dict() for finding in findings],
                "when_changes": when,
                "covered_by": covered,
                "ok": ok,
            },
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point: compare the release tag against the working tree."""
    args = _parse_args(argv)
    try:
        ref = args.base or release_tag(TOP)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"cannot read the release tags of {TOP}: {exc}", file=sys.stderr)
        return 2
    if ref is None:
        note = "no release tag found; there is no released questionnaire to compare against"
        print(json.dumps({"base": None, "ok": True, "note": note}) if args.json else f"skipping: {note}")
        return 0
    try:
        base_config = load_ref_config(TOP, ref)
        head_config = load_working_tree_config(TOP)
    except (CopierError, subprocess.CalledProcessError, OSError, tarfile.TarError, ValueError) as exc:
        print(f"cannot load {CONFIG_NAME} at {ref} or in the working tree: {exc}", file=sys.stderr)
        return 2
    base_questions = questions(base_config)
    head_questions = questions(head_config)
    findings = compare(base_questions, head_questions)
    when = when_changes(base_questions, head_questions)
    covered = new_migrations(base_config, head_config) if findings else []
    ok = not findings or bool(covered)
    if args.json:
        _report_json(ref, findings, when, covered, ok=ok)
    else:
        _report_text(ref, findings, when, covered)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
