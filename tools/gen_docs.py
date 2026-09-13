#!/usr/bin/env python3
"""Generate the questionnaire-derived documentation, and check it for drift.

The questionnaire (`copier.yml` plus the `questions/*.yml` fragments) is the
single source of truth for this template's option set; `tools/questionnaire.py`
exposes it as data. This script renders every part of the docs that only
repeats that data, so none of it can silently drift again:

- `docs/reference/questionnaire.md`: the project-type list, the area-gate
  table with each area's recommended defaults, the detailed questions a gate
  reveals, and the trailing project-details questions.
- `README.md`: the per-area recommended settings table, the ask-order mermaid
  graph (each gate's Yes/No branch) and the task-runner bullet of the Features
  section.
- `README.md`: the support matrix table, generated from `support.yml` -- only
  when that file exists (W4 owns it; no `support.yml`, no block).

Every generated region sits between an explicit marker pair::

    <!-- BEGIN GENERATED: <name> (tools/gen_docs.py --write) -->
    ...
    <!-- END GENERATED: <name> -->

`--write` replaces those regions wholesale and never touches the hand-written
prose around them; `--check` renders the same text and exits non-zero when a
committed region differs (the CI gate). Both run offline.

Usage:
    python tools/gen_docs.py --check   # exit 1 when a generated block is stale
    python tools/gen_docs.py --write   # update the generated blocks
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import questionnaire  # noqa: E402
from tools.questionnaire import Question  # noqa: E402

README = TOP / "README.md"
QUESTIONNAIRE_DOC = TOP / "docs" / "reference" / "questionnaire.md"
SUPPORT_YML = TOP / "support.yml"

BEGIN = "<!-- BEGIN GENERATED: {name} (tools/gen_docs.py --write) -->"
END = "<!-- END GENERATED: {name} -->"

GATE_PREFIX = "use_recommended_"
INCLUDE_PREFIX = "include_"

# Conditions rendered in prose. The key is the `when` string exactly as the
# questionnaire writes it, so a changed condition is a loud generator failure
# instead of a stale sentence in the docs.
CONDITION_PROSE: dict[str, str] = {
    "{{ project_type in ['library', 'cli'] }}": "library / cli",
    "{{ project_type in ['library', 'cli', 'web_api'] }}": "library / cli / web_api",
    "{{ project_type in ['library', 'cli', 'data_science'] or kaggle }}": "library / cli / data_science / kaggle",
    "{{ not (project_type == 'ros2' and ros2_package_manager == 'pixi') }}": "not ros2 + pixi",
    "{{ include_scraping }}": "a `cli` base answers Yes to `include_scraping`",
    "{{ has_data_science }}": "the data_science layer is present",
    "{{ has_web_api }}": "the web_api layer is present",
    "{{ git_platform == 'github.com' }}": "`git_platform` = github.com",
    "{{ git_platform == 'gitlab.com' }}": "`git_platform` = gitlab.com",
}
ALL_TYPES = "all"

# Lines that start a paragraph of a question's help after the prompt itself
# (`Recommended: ...`, `Answer No to ...`): the prompt stops before them.
PROMPT_STOPS = ("Recommended: ", "Answer No to ", "Answer Yes ", "Deselect ", "If yes", "If true")

_PROJECT_TYPE_EQ = re.compile(r"^\{\{\s*project_type == '([a-z0-9_]+)'\s*\}\}$")
_HELP_BULLET = re.compile(r"^- ([A-Za-z0-9_.\-]+): (.*)$")

# Link targets for the task runners the questionnaire offers. The runner
# *names* come from the model (`labels`); only the URLs are curated here.
RUNNER_URLS: dict[str, str] = {
    "just": "https://just.systems",
    "task": "https://taskfile.dev",
    "poe": "https://github.com/nat-n/poethepoet",
    "make": "https://www.gnu.org/software/make/",
    "invoke": "https://www.pyinvoke.org",
    "duty": "https://duty.readthedocs.io",
    "pixi": "https://pixi.sh",
}


class GenDocsError(Exception):
    """The docs cannot be generated from the questionnaire."""


# ---------------------------------------------------------------------------
# Reading the question model.
# ---------------------------------------------------------------------------


def _mentions(question: Question, names: list[str]) -> bool:
    """True when the raw `when` expression references any of `names`."""
    when = str(question.when)
    return any(name in when for name in names)


def _mentions_project_type(question: Question, choice: str) -> bool:
    """True when a question is asked for one `project_type` choice.

    Either the `when` compares `project_type` to the literal, or it tests a
    derived boolean named after the choice (`online_judge`, ...).
    """
    when = str(question.when)
    if f"'{choice}'" in when:
        return True
    return re.search(rf"\b{re.escape(choice)}\b", when) is not None


@dataclass(frozen=True)
class Model:
    """The questionnaire, plus the groupings the generated docs are built from."""

    questions: tuple[Question, ...]

    @classmethod
    def load(cls, config: Path | None = None) -> Model:
        """Load the questionnaire from `copier.yml` (or another config)."""
        questions, _settings = questionnaire.load_questions(config)
        return cls(tuple(questions))

    @property
    def external(self) -> list[Question]:
        """The questions a user is actually asked (not `when: false` internals)."""
        return [q for q in self.questions if not q.internal]

    @property
    def gates(self) -> list[Question]:
        """The `use_recommended_*` area gates, in ask order."""
        return [q for q in self.external if q.name.startswith(GATE_PREFIX)]

    @property
    def includes(self) -> list[Question]:
        """The `include_*` opt-in layers, in ask order.

        Integration switches (`include_sentry`, `include_mcp`) share the
        prefix but are gate details, not layers.
        """
        return [
            q
            for q in self.external
            if q.name.startswith(INCLUDE_PREFIX) and not _mentions(q, [g.name for g in self.gates])
        ]

    @property
    def area_gates(self) -> list[Question]:
        """The top-level areas: gates no `include_*` opt-in owns."""
        includes = [q.name for q in self.includes]
        return [q for q in self.gates if not _mentions(q, includes)]

    @property
    def option_gates(self) -> list[Question]:
        """Gates an opt-in layer owns (`include_scraping` -> `use_recommended_scraping`)."""
        area = {q.name for q in self.area_gates}
        return [q for q in self.gates if q.name not in area]

    @property
    def project_details(self) -> list[Question]:
        """The trailing questions asked after the last gate (package, author, ...)."""
        gated = [q.name for q in self.gates] + [q.name for g in self.gates for q in self.details(g)]
        gated += [q.name for q in self.includes]
        last = max(index for index, q in enumerate(self.external) if q.name in gated)
        return self.external[last + 1 :]

    def question(self, name: str) -> Question:
        """The question with this name."""
        for candidate in self.questions:
            if candidate.name == name:
                return candidate
        msg = f"no question named {name!r} in the questionnaire"
        raise GenDocsError(msg)

    def details(self, gate: Question) -> list[Question]:
        """The detailed questions a gate reveals when answered No."""
        return [
            q
            for q in self.external
            if q.name != gate.name and not q.name.startswith(GATE_PREFIX) and _mentions(q, [gate.name])
        ]

    def is_detail(self, question: Question) -> bool:
        """True for a question revealed by answering No to a gate."""
        return any(_mentions(question, [gate.name]) for gate in self.gates)

    def follow_ups(self, choice: str) -> list[Question]:
        """The genre questions asked for one `project_type` choice.

        Gates, opt-in layers and the details they reveal are excluded: those
        are documented by the areas table, not as project-type follow-ups.
        """
        owned = {q.name for q in self.gates} | {q.name for q in self.includes}
        return [
            q
            for q in self.external
            if q.name not in owned
            and q.when is not None
            and not self.is_detail(q)
            and _mentions_project_type(q, choice)
        ]


# ---------------------------------------------------------------------------
# Reading the questionnaire's own help text.
# ---------------------------------------------------------------------------


def first_sentence(text: str) -> str:
    """A paragraph's first sentence.

    Only a `.`/`!`/`?` followed by a whitespace and a capital, digit, backtick
    or bracket ends a sentence, so abbreviations like `e.g. 0000-0002-...`
    and version numbers like `SQLAlchemy 2.0 + ...` stay intact.
    """
    end = re.search(r"[.!?]\s(?=[A-Z0-9`(])", text)
    return text[: end.start() + 1].strip() if end else text.strip()


def help_paragraph(question: Question, marker: str) -> str:
    """The first sentence after `marker` in a question's help text.

    The questionnaire's help strings have a fixed shape (`Recommended: ...`,
    `Answer No to ...`), which is why the recommendation and the opt-out
    behaviour can be lifted out of them instead of being restated here.
    """
    joined = " ".join(question.help.split())
    index = joined.find(marker)
    if index < 0:
        msg = f"question {question.name!r} has no {marker.strip()!r} line in its help"
        raise GenDocsError(msg)
    return first_sentence(joined[index + len(marker) :])


def recommended(gate: Question) -> str:
    """What a gate's recommended answer configures."""
    return help_paragraph(gate, "Recommended: ")


def declined(gate: Question) -> str:
    """What answering No to a gate does."""
    return help_paragraph(gate, "Answer No to ")


def prompt_line(question: Question) -> str:
    """The question's prompt: its help's first paragraph, before the markers."""
    lines: list[str] = []
    for line in question.help.splitlines():
        if not line.strip() or line.startswith(("- ", "  ")):
            break
        lines.append(line.strip())
    text = " ".join(lines)
    for stop in PROMPT_STOPS:
        index = text.find(stop)
        if index >= 0:
            text = text[:index]
    return _clip(text.strip(), 150) if text.strip() else question.name


def choice_help(question: Question) -> dict[str, str]:
    """`- value: description` bullets in a question's help, keyed by value.

    Continuation lines (indented past the bullet) are joined into the value's
    description, so a wrapped help string reads as one sentence here.
    """
    found: dict[str, str] = {}
    current = ""
    for line in question.help.splitlines():
        match = _HELP_BULLET.match(line)
        if match:
            value, description = match.groups()
            found[str(value)] = str(description).strip()
            current = str(value)
        elif current and line.startswith("  ") and line.strip():
            found[current] = f"{found[current]} {line.strip()}"
        else:
            current = ""
    return found


def condition(question: Question) -> str:
    """The `when` condition in prose, or `all` when the question always runs."""
    if question.when is None:
        return ALL_TYPES
    raw = str(question.when)
    match = _PROJECT_TYPE_EQ.match(raw)
    if match:
        return match.group(1)
    if raw in CONDITION_PROSE:
        return CONDITION_PROSE[raw]
    msg = f"question {question.name!r} has an unmapped when condition: {raw!r}"
    raise GenDocsError(msg)


def default_prose(question: Question) -> str:
    """A question's default, readable in a table cell."""
    value = question.default
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        if "{{" in value:
            return f"`{' '.join(value.strip('{} ').split())}`"
        return f"`{value}`" if value else "(empty)"
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    return f"`{value}`"


def asked_for_values(question: Question) -> list[str]:
    """The literals a `when` compares a non-project_type variable to."""
    raw = str(question.when)
    if "project_type" in raw:
        return []
    return re.findall(r"== '([A-Za-z0-9_.\-]+)'", raw)


def _cell(text: str) -> str:
    """A markdown table cell: one line, no unescaped pipes."""
    return " ".join(text.split()).replace("|", "\\|")


def _wrap(text: str, prefix: str = "", continuation: str = "  ", width: int = 100) -> list[str]:
    """Greedy-wrap `text`, prefixing the first line and each continuation line."""
    lines: list[str] = []
    current = prefix
    for word in text.split():
        separator = "" if not current or current.endswith(" ") else " "
        if current.strip() and len(current) + len(separator) + len(word) > width:
            lines.append(current)
            current = f"{continuation}{word}"
        else:
            current = f"{current}{separator}{word}"
    if current:
        lines.append(current)
    return lines


def _es(text: str) -> str:
    """Escape text for a quoted mermaid node label.

    Mermaid labels are plain text, not markdown, so code backticks are
    dropped rather than rendered literally.
    """
    text = text.replace("`", "")
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _br(parts: list[str], width: int = 64) -> str:
    """Join `parts` with `, ` and wrap into mermaid `<br/>`-separated lines."""
    return "<br/>".join(_es(line) for line in _wrap(", ".join(parts), width=width, continuation=""))


def _clip(text: str, limit: int = 96, *, prefer_paren: bool = False) -> str:
    """Shorten `text` to at most `limit` characters.

    The cut prefers a sentence end, then (for mermaid labels) the opening
    parenthesis of a trailing explanation, then a word boundary.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    sentences = [match.end() for match in re.finditer(r"[.!?](?=\s+[A-Z0-9`(])", head)]
    if sentences and sentences[-1] >= limit // 2:
        return head[: sentences[-1]].strip()
    paren = head.rfind(" (")
    if prefer_paren and paren >= limit // 3:
        return head[:paren].strip()
    return f"{head.rsplit(' ', 1)[0]}…"


def _short_gate_label(model: Model, gate: Question, *, yes: bool) -> str:
    """A gate's Yes (recommended) or No (declined) branch label."""
    if yes:
        text = recommended(gate).removeprefix("yes — ").removeprefix("yes - ")
        return _es(_clip(text, 84, prefer_paren=True))
    details = model.details(gate)
    if details:
        return _br([f"ask: {', '.join(q.name for q in details)}"], 76)
    return _es(_clip(declined(gate), 84))


# ---------------------------------------------------------------------------
# The rendered blocks.
# ---------------------------------------------------------------------------


def render_project_types(model: Model) -> str:
    """`docs/reference/questionnaire.md`: the project-type choices."""
    question = model.question("project_type")
    described = choice_help(question)
    lines: list[str] = []
    for choice in question.choices:
        value = str(choice)
        description = described.get(value, "")
        lines += _wrap(f"**{value}** — {description}" if description else f"**{value}**", prefix="- ")
        follow = model.follow_ups(value)
        if follow:
            lines += _wrap("Questions asked when this is the base type:", prefix="  ", continuation="  ")
            lines += [line for item in follow for line in _detail_lines(item, indent="  ")]
    return "\n".join(lines)


def _area_table(model: Model) -> list[str]:
    """The area-gate table: gate, its recommended default, and when it is asked."""
    lines = ["| Area gate | Recommended default | Asked when |", "|---|---|---|"]
    lines += [f"| `{gate.name}` | {_cell(recommended(gate))} | {_cell(condition(gate))} |" for gate in model.area_gates]
    return lines


def render_areas(model: Model) -> str:
    """`docs/reference/questionnaire.md`: the area gates and opt-in layers."""
    lines = [
        (
            "Each area asks one gate question first: answering **Yes** configures it from the"
            " recommendation below, answering **No** reveals that area's detailed questions."
        ),
        "",
        *_area_table(model),
    ]
    if model.includes:
        lines += ["", "An opt-in layer adds its area to a combinable base:", ""]
        for layer in model.includes:
            text = (
                f"**`{layer.name}`** (asked when {condition(layer)}; default {default_prose(layer)})"
                f" — {prompt_line(layer)}"
            )
            lines += _wrap(text, prefix="- ")
    if model.option_gates:
        lines += ["", "An opt-in layer asks its own gate on top:", ""]
        for gate in model.option_gates:
            text = f"**`{gate.name}`** (asked when {condition(gate)}): {recommended(gate)}"
            lines += _wrap(text, prefix="- ")
    return "\n".join(lines)


def _choice_bullets(question: Question, described: dict[str, str]) -> list[tuple[str, str]]:
    """The (value, description) bullets to render for a question.

    Questions whose `choices` are a template (`package_manager`, `oj_kind`)
    declare their values only in the help text, so everything the help
    describes is rendered; otherwise the declared choices win.
    """
    if not question.choices:
        return list(described.items())
    return [(str(choice), described[str(choice)]) for choice in question.choices if str(choice) in described]


def _choice_values(question: Question, described: dict[str, str]) -> list[str]:
    """The choices with no help bullet, value plus label when the model has one.

    A long list (the SPDX license set) is rendered as bare values: the labels
    would triple its length without adding anything to look up.
    """
    labels = dict(zip(question.choices, question.labels, strict=True)) if question.labels else {}
    with_labels = len(question.choices) <= 20
    parts: list[str] = []
    for choice in question.choices:
        value = str(choice)
        if value in described:
            continue
        label = labels.get(choice) if with_labels else None
        parts.append(f"`{value}` ({label})" if label and label != value else f"`{value}`")
    return parts


def _detail_lines(question: Question, indent: str = "") -> list[str]:
    """One detailed question, its choices, and its documented default."""
    kind = question.type or "str"
    head = f"**`{question.name}`** ({kind}; default {default_prose(question)}) — {prompt_line(question)}"
    lines = _wrap(head, prefix=f"{indent}- ", continuation=f"{indent}  ")
    described = choice_help(question)
    for value, description in _choice_bullets(question, described):
        lines += _wrap(f"**`{value}`** — {description}", prefix=f"{indent}  - ", continuation=f"{indent}    ")
    undescribed = _choice_values(question, described)
    if undescribed:
        lines += _wrap(f"One of: {' · '.join(undescribed)}.", prefix=f"{indent}  ", continuation=f"{indent}  ")
    return lines


def render_detailed_questions(model: Model) -> str:
    """`docs/reference/questionnaire.md`: what each gate reveals."""
    header = [
        "Answering **No** to a gate reveals that area's detailed questions:",
    ]
    sections: list[str] = []
    for gate in model.gates:
        part = [
            f"### `{gate.name}`",
            "",
            f"{prompt_line(gate)} Recommended: {recommended(gate)}",
            "",
            f"Answer **No** to {declined(gate)}",
        ]
        details = [line for item in model.details(gate) for line in _detail_lines(item)]
        if details:
            part += ["", *details]
        sections.append("\n".join(part))
    return "\n".join(header) + "\n\n" + "\n\n".join(sections)


def render_project_details(model: Model) -> str:
    """`docs/reference/questionnaire.md`: the trailing project-details questions."""
    lines = [
        "| Question | Default | Asked when | Prompt |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{question.name}` | {_cell(default_prose(question))} | {_cell(condition(question))}"
        f" | {_cell(prompt_line(question))} |"
        for question in model.project_details
    ]
    return "\n".join(lines)


def render_features_areas(model: Model) -> str:
    """`README.md`: the per-area recommended settings table."""
    return "\n".join(_area_table(model))


def render_features_task_runner(model: Model) -> str:
    """`README.md`: the task-runner bullet, with the questionnaire's default."""
    runners = model.question("task_runner")
    pixi = model.question("task_runner_pixi")
    text = (
        f"A task runner of your choice ({_runner_list(runners)}) driving lint / type-check / test / docs"
        " — one shared task definition, invoked by CI too. With `package_manager` = pixi, the choices are"
        f" {_runner_list(pixi)} (poethepoet is not offered there)."
    )
    return "\n".join(_wrap(text, prefix="- "))


def _runner_list(question: Question) -> str:
    """One task runner's choices, linked, with the questionnaire's default marked."""
    labels = question.labels or [str(choice) for choice in question.choices]
    parts: list[str] = []
    for choice, label in zip(question.choices, labels, strict=True):
        name = f"[{label.replace(' ', '&nbsp;')}]({RUNNER_URLS[choice]})" if choice in RUNNER_URLS else label
        parts.append(f"{name} (default)" if choice == question.default else name)
    return " / ".join(parts)


def render_support_table(support: dict[str, Any]) -> str:
    """`README.md`: the support matrix, from `support.yml`'s `supported:` list.

    The columns are the entry keys, in the order the file writes them, so the
    table follows whatever shape W4 settles on instead of pinning one here.
    """
    rows = support.get("supported")
    if not isinstance(rows, list) or not rows:
        msg = "support.yml has no non-empty `supported:` list"
        raise GenDocsError(msg)
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            msg = "every `supported:` entry must be a mapping"
            raise GenDocsError(msg)
        columns += [str(key) for key in row if str(key) not in columns]
    lines = [f"| {' | '.join(columns)} |", f"|{'---|' * len(columns)}"]
    for row in rows:
        cells = [_cell(_support_cell(row.get(column))) for column in columns]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines)


def _support_cell(value: Any) -> str:
    """One support-matrix cell."""
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "—"
    return f"`{value}`"


def load_support(path: Path) -> dict[str, Any]:
    """Read `support.yml`."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{path.name} must hold a mapping"
        raise GenDocsError(msg)
    return data


# ---------------------------------------------------------------------------
# The mermaid graph.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AskGroup:
    """One `project_type` branch: the questions asked, and for which base."""

    choice: str
    questions: list[Question]
    first_index: int


def _ask_groups(model: Model) -> list[_AskGroup]:
    """The project-type branches: each base's follow-up questions, in ask order."""
    order = {q.name: index for index, q in enumerate(model.questions)}
    groups: list[_AskGroup] = []
    for choice in model.question("project_type").choices:
        questions = model.follow_ups(str(choice))
        if questions:
            groups.append(_AskGroup(str(choice), questions, min(order[q.name] for q in questions)))
    return groups


def _ask_label() -> Callable[[list[Question]], str]:
    """Build the `ask: ...` node label for a group of questions."""

    def label(questions: list[Question]) -> str:
        parts: list[str] = []
        for question in questions:
            choices = [str(choice) for choice in question.choices] or list(choice_help(question))
            values = choices or asked_for_values(question)
            parts.append(f"{question.name} ({' / '.join(values)})" if values else question.name)
        return f"ask: {_br(parts)}"

    return label


class _Graph:
    """Accumulates mermaid lines for one questionnaire and hands out node ids."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.lines: list[str] = []
        self._counter = count()

    def node(self, prefix: str) -> str:
        """A fresh node id with this prefix."""
        return f"{prefix}{next(self._counter)}"

    def add(self, *lines: str) -> None:
        """Append lines to the graph."""
        self.lines.extend(lines)


def _split_asks(model: Model, first_gate: Question) -> tuple[list[_AskGroup], list[_AskGroup]]:
    """Split the project-type branches into pre-gate and mid-sequence ones."""
    first = min(index for index, q in enumerate(model.questions) if q.name == first_gate.name)
    groups = _ask_groups(model)
    return (
        [group for group in groups if group.first_index < first],
        [group for group in groups if group.first_index >= first],
    )


def _graph_project_types(graph: _Graph, early: list[_AskGroup], early_ids: list[str], head: list[Question]) -> None:
    """Branch from `project_type` to the bases' follow-ups and the head gates."""
    ask_label = _ask_label()
    for group, node in zip(early, early_ids, strict=True):
        graph.add(f'    PT -->|{group.choice}| {node}["{ask_label(group.questions)}"]')
    when = condition(head[0])
    edge = f"    PT -->|{when}|" if when != ALL_TYPES else "    PT -->"
    graph.add(f'{edge} {_gate_id(head[0])}{{"{_gate_label(head[0])}"}}')
    if len(head) > 1:
        graph.add(f'    PT -->|other| {_gate_id(head[1])}{{"{_gate_label(head[1])}"}}')
    target = _gate_id(head[-1])
    graph.add(*[f"    {node} --> {target}" for node in early_ids])


def _graph_branches(graph: _Graph, gate: Question, after: str) -> None:
    """A gate's Yes/No branches and their rejoin."""
    graph.add(*_gate_branches(graph.model, gate, _gate_id(gate)))
    graph.add(f"    {_yes_id(gate)} --> {after}", f"    {_no_id(gate)} --> {after}")


def _graph_asks(graph: _Graph, late: list[_AskGroup], late_ids: list[str], after_ids: list[str], entry: str) -> None:
    """The mid-sequence project-type asks (`online_judge`), each a Yes/No diamond."""
    ask_label = _ask_label()
    previous = entry
    for group, diamond, after in zip(late, late_ids, after_ids, strict=True):
        ask = graph.node("Q")
        graph.add(f'    {diamond}{{"{_es(group.choice)}?"}}')
        if previous != diamond:
            graph.add(f"    {previous} --> {diamond}")
        graph.add(
            f'    {diamond} -->|Yes| {ask}["{ask_label(group.questions)}"]',
            f"    {ask} --> {after}",
            f"    {diamond} -->|No| {after}",
        )
        previous = after


def _graph_tail(graph: _Graph, tail: list[Question], entries: list[str], after_ids: list[str], entry: str) -> None:
    """Chain the remaining gates; every branch rejoins at the next stage."""
    previous = entry
    for index, gate in enumerate(tail):
        after = after_ids[index]
        if entries[index] != _gate_id(gate):
            layer = (
                f'    {entries[index]}{{"{_layer_label(graph.model, gate)}?"}}'
                if previous == entries[index]
                else f'    {previous} --> {entries[index]}{{"{_layer_label(graph.model, gate)}?"}}'
            )
            graph.add(
                layer,
                f'    {entries[index]} -->|Yes| {_gate_id(gate)}{{"{_gate_label(gate)}"}}',
                f"    {entries[index]} -->|No| {after}",
            )
        elif previous == _gate_id(gate):
            graph.add(f'    {_gate_id(gate)}{{"{_gate_label(gate)}"}}')
        else:
            graph.add(f'    {previous} --> {_gate_id(gate)}{{"{_gate_label(gate)}"}}')
        _graph_branches(graph, gate, after)
        previous = after


def render_mermaid(model: Model) -> str:
    """The questionnaire's ask order, with each gate's Yes/No branches."""
    gates = model.gates
    if not gates:
        msg = "the questionnaire has no use_recommended_* gate to draw"
        raise GenDocsError(msg)
    head, tail = gates[:2], gates[2:]
    early, late = _split_asks(model, head[0])
    graph = _Graph(model)
    early_ids = [graph.node("Q") for _ in early]
    late_ids = [graph.node("D") for _ in late]
    entries = [graph.node("L") if _layer_var(gate) or gate in model.option_gates else _gate_id(gate) for gate in tail]
    includes_id = "INC" if model.includes else None
    first_tail = entries[0] if tail else "PD"
    late_after = [*late_ids[1:], includes_id or first_tail] if late_ids else []
    after_head = late_ids[0] if late_ids else includes_id or first_tail
    graph.add("flowchart TD", "    Start([Start]) --> PT[project_type]")
    _graph_project_types(graph, early, early_ids, head)
    for index, gate in enumerate(head):
        after = _gate_id(head[index + 1]) if index + 1 < len(head) else after_head
        _graph_branches(graph, gate, after)
    _graph_asks(graph, late, late_ids, late_after, after_head)
    if includes_id:
        names = _br([f"ask: {', '.join(q.name for q in model.includes)}"], 56)
        label = f'INC["{names}<br/>(each only for the bases it combines with)"]'
        graph.add(f"    {label}" if late_ids else f"    {after_head} --> {label}")
    _graph_tail(graph, tail, entries, [*entries[1:], "PD"], includes_id or after_head)
    details = _br([q.name for q in model.project_details])
    graph.add(f'    PD["Project details: {details}"]', "    PD --> End([Generate project])")
    return "\n".join(graph.lines)


def _gate_id(gate: Question) -> str:
    """Stable node id for a gate diamond."""
    return f"G_{gate.name.removeprefix(GATE_PREFIX)}"


def _yes_id(gate: Question) -> str:
    """Node id of a gate's Yes node."""
    return f"{_gate_id(gate)}_yes"


def _no_id(gate: Question) -> str:
    """Node id of a gate's No node."""
    return f"{_gate_id(gate)}_no"


def _gate_label(gate: Question) -> str:
    """A gate diamond's label: the question, and when it is asked."""
    when = condition(gate)
    if when == ALL_TYPES:
        return f"{gate.name}?"
    return f"{_es(gate.name)}?<br/>({_es(when)})"


def _layer_var(gate: Question) -> str | None:
    """The `has_*` layer variable a gate's condition tests, if any."""
    match = re.match(r"^\{\{\s*(has_[a-z_]+)\s*\}\}$", str(gate.when))
    return match.group(1) if match else None


def _layer_label(model: Model, gate: Question) -> str:
    """The layer question asked before a layer-gated area gate."""
    variable = _layer_var(gate)
    if variable:
        return f"{variable.removeprefix('has_').replace('_', ' ')} layer"
    option = next((q for q in model.includes if str(q.when) and q.name in str(gate.when)), None)
    return option.name if option else "option"


def _gate_branches(model: Model, gate: Question, node_id: str) -> list[str]:
    """A gate's Yes/No edges, labelled from its own help text."""
    yes = _short_gate_label(model, gate, yes=True)
    no = _short_gate_label(model, gate, yes=False)
    return [
        f'    {node_id} -->|Yes| {_yes_id(gate)}["{yes}"]',
        f'    {node_id} -->|No| {_no_id(gate)}["{no}"]',
    ]


# ---------------------------------------------------------------------------
# Targets, check and write.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """One generated block: where it lives, its marker name and its renderer."""

    path: Path
    block: str
    render: Callable[[Model], str]

    def begin(self) -> str:
        """The opening marker line."""
        return BEGIN.format(name=self.block)

    def end(self) -> str:
        """The closing marker line."""
        return END.format(name=self.block)

    def pattern(self) -> re.Pattern[str]:
        """The compiled marker pair, with the body as the `body` group."""
        return re.compile(
            rf"{re.escape(self.begin())}\n(?P<body>.*?)\n{re.escape(self.end())}",
            re.DOTALL,
        )

    def render_text(self, model: Model) -> str:
        """The block body for this questionnaire."""
        text = self.render(model)
        if "<!-- BEGIN GENERATED" in text or "<!-- END GENERATED" in text:
            msg = f"the {self.block!r} block renders marker text"
            raise GenDocsError(msg)
        return text


def targets(support: Path = SUPPORT_YML) -> list[Target]:
    """Every generated block, in file order.

    The support matrix is only generated when `support.yml` exists: W4 owns
    that file, and its README block appears with it.
    """
    blocks = [
        Target(QUESTIONNAIRE_DOC, "project-types", render_project_types),
        Target(QUESTIONNAIRE_DOC, "areas", render_areas),
        Target(QUESTIONNAIRE_DOC, "detailed-questions", render_detailed_questions),
        Target(QUESTIONNAIRE_DOC, "project-details", render_project_details),
        Target(README, "features-areas", render_features_areas),
        Target(README, "features-mermaid", _mermaid_block),
        Target(README, "features-task-runner", render_features_task_runner),
    ]
    if support.is_file():
        blocks.append(Target(README, "support-table", _support_block(support)))
    return blocks


def _mermaid_block(model: Model) -> str:
    """The README mermaid block, fences included."""
    return f"```mermaid\n{render_mermaid(model)}\n```"


def _support_block(support: Path) -> Callable[[Model], str]:
    """A renderer for README's support matrix, bound to `support.yml`."""

    def render(_model: Model) -> str:
        return render_support_table(load_support(support))

    return render


def _relative(path: Path) -> str:
    return str(path.relative_to(TOP)) if path.is_relative_to(TOP) else str(path)


def _drift(target: Target, actual: str, expected: str) -> str:
    """Describe the first line where a committed block differs from the model."""
    committed = actual.splitlines()
    wanted = expected.splitlines()
    for index, (left, right) in enumerate(zip(committed, wanted, strict=False), start=1):
        if left != right:
            return f"{_relative(target.path)}: {target.block} differs at line {index}\n  - {left}\n  + {right}"
    if len(committed) != len(wanted):
        extra = wanted[len(committed)] if len(wanted) > len(committed) else committed[len(wanted)]
        return (
            f"{_relative(target.path)}: {target.block} has {len(committed)} lines, expected {len(wanted)}\n  ± {extra}"
        )
    return f"{_relative(target.path)}: {target.block} differs"


def check(model: Model, blocks: list[Target]) -> list[str]:
    """Return one problem per stale or missing generated block."""
    problems: list[str] = []
    for target in blocks:
        match = target.pattern().search(target.path.read_text(encoding="utf-8"))
        if match is None:
            problems.append(f"{_relative(target.path)}: no generated block {target.block!r} (add its markers)")
            continue
        expected = target.render_text(model)
        if match.group("body") != expected:
            problems.append(_drift(target, match.group("body"), expected))
    return problems


def write(model: Model, blocks: list[Target]) -> list[str]:
    """Replace every generated block; return the blocks that changed."""
    changed: list[str] = []
    for target in blocks:
        text = target.path.read_text(encoding="utf-8")
        match = target.pattern().search(text)
        if match is None:
            msg = f"{_relative(target.path)}: no generated block {target.block!r} (add its markers)"
            raise GenDocsError(msg)
        expected = target.render_text(model)
        if match.group("body") == expected:
            continue
        target.path.write_text(text[: match.start("body")] + expected + text[match.end("body") :], encoding="utf-8")
        changed.append(f"{_relative(target.path)}: {target.block}")
    return changed


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit non-zero when a generated block is stale (default)")
    mode.add_argument("--write", action="store_true", help="rewrite the generated blocks")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: check or rewrite the generated blocks."""
    args = _parse_args(argv)
    model = Model.load()
    blocks = targets()
    if args.write:
        changed = write(model, blocks)
        if not changed:
            print(f"{len(blocks)} generated block(s) already up to date")
            return 0
        print("updated:\n  " + "\n  ".join(changed))
        return 0
    problems = check(model, blocks)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("generated docs are stale; run: python tools/gen_docs.py --write", file=sys.stderr)
        return 1
    print(f"{len(blocks)} generated block(s) in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
