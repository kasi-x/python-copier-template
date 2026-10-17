#!/usr/bin/env python3
"""Questionnaire surface: ask order, presets, explanations, proposals, validation.

Responsibility: the tools that answer from the questionnaire's own words
without rendering anything -- `list_questions`, `list_presets`,
`explain_choice`, `suggest_config`, `validate_answers` -- plus the one helper
(`_explain_text`) that routes an `explain_choice` call to the `explain.*`
function it names. Filesystem only, no render, no network (validation runs
copier's own questionnaire pass, which is still not a render).
"""

# WHYNOT: the functions below are registered through @mcp_interface.tool(server)
# inside register_*(); their call edge is the decorator, invisible to
# the checker.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import cli  # noqa: E402
from architekton import explain  # noqa: E402
from architekton import mcp_interface  # noqa: E402
from architekton import suggest  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402


def explain_text(
    question: str | None,
    value: str | None,
    preset: str | None,
    deviate_question: str | None,
    deviate_value: str | None,
) -> str:
    """The explanation text for one `explain_choice` call (the tool itself only wraps errors)."""
    if preset is not None:
        return explain.explain_preset(preset)
    if deviate_question is not None and deviate_value is not None:
        return explain.explain_deviation(deviate_question, deviate_value)
    if question is not None:
        return explain.explain_answer(question, value)
    msg = "pass preset=, question=[value=], or deviate_question= + deviate_value="
    raise ToolError(msg)


def register_questionnaire(server: Any) -> None:
    """Register the questionnaire tools on `server`."""

    @mcp_interface.tool(server)
    def list_questions(*, asked_only: bool = True) -> dict[str, Any]:
        """Every question in ask order, with its type, default, condition, help and choices.

        Returns {"count", "questions"}. `asked_only=False` also lists the derived
        values (`internal: true`): they are computed, never answered. A question
        with `choices_template` instead of `choices` narrows its choices from
        earlier answers. Cost: filesystem only.
        """
        schema = suggest.questionnaire_schema(asked_only=asked_only)
        return {"count": schema["count"], "questions": schema["questions"]}

    @mcp_interface.tool(server)
    def list_presets() -> dict[str, Any]:
        """The ready-made answer sets: each preset's name and the answers it pins.

        Returns {"count", "presets"}: each `name` and the `answers` it pins (a
        starting point for an answer set; the CLI's `--preset` takes the name).
        Cost: filesystem only.
        """
        presets = [{"name": name, "answers": cli.preset_answers(name)} for name in cli.available_presets()]
        return {"count": len(presets), "presets": presets}

    @mcp_interface.tool(server)
    def explain_choice(
        question: str | None = None,
        value: str | None = None,
        preset: str | None = None,
        deviate_question: str | None = None,
        deviate_value: str | None = None,
    ) -> dict[str, Any]:
        """Why a preset or an answer, in the questionnaire's own words.

        Pass `preset`, or `question` (and optionally `value`), or
        `deviate_question` + `deviate_value` for what changes when that answer
        differs from the recommendation. Returns {"explanation"}.
        Cost: filesystem only.
        """
        try:
            text = explain_text(question, value, preset, deviate_question, deviate_value)
        except explain.ExplainError as exc:
            raise ToolError(str(exc)) from exc
        return {"explanation": text}

    @mcp_interface.tool(server)
    def suggest_config(requirements: str) -> dict[str, Any]:
        """Rank the presets against requirement words ("an internal API with Postgres").

        Returns {"requirements", "matches"}: each match's preset, score, reasons
        and pinned answers. Deterministic keyword matching, not a model.
        Cost: filesystem only.
        """
        matches = suggest.suggest_presets([requirements])
        return {"requirements": requirements, "matches": [match.as_dict() for match in matches]}

    @mcp_interface.tool(server)
    def validate_answers(answers: dict[str, Any]) -> dict[str, Any]:
        """Check a proposed answer set before generating from it.

        Returns {"ok", "errors"}; each error is {question, reason} and names the
        valid choices when a value is outside them. Fix every error, then
        generate. Cost: reads the questionnaire, no render, no network.
        """
        return suggest.validate_answers(dict(answers)).as_dict()
