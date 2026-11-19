"""Exact public evidence checks for grounded conjunctive formal goals."""

from __future__ import annotations

import re
from typing import Any

from .contracts import VerificationResult

_TOKEN_RE = re.compile(r"[()]|[^\s()]+")
_COMMENT_RE = re.compile(r";[^\n]*")
_UNSUPPORTED_OPERATORS = frozenset(
    {"and", "or", "not", "forall", "exists", "imply", "when", "=", "<", ">", "<=", ">="}
)


def formal_goal_verdict(task_input: str, state_values: Any) -> VerificationResult | None:
    """Check exact public predicates, returning None when the format is unsupported."""
    goals = _formal_goals(task_input)
    state = _state_predicates(state_values)
    if goals is None or state is None:
        return None
    missing = sorted(goal for goal in goals if goal not in state)
    goal_by_name = {
        _predicate_name(goal): goal
        for goal in missing
        if _predicate_name(goal) is not None
    }
    conflicting = sorted(
        {
            value
            for value in state
            if _predicate_name(value) in goal_by_name and value not in goals
        }
    )
    if not missing:
        reason = (
            f"Exact public formal-goal check: all {len(goals)} goal predicates "
            "are present in the latest state snapshot."
        )
    else:
        reason = "Exact public formal-goal check: missing " + ", ".join(missing) + "."
    return VerificationResult(
        goal_satisfied=not missing,
        missing_predicates=missing,
        conflicting_predicates=conflicting,
        reason=reason,
    )


def _formal_goals(task_input: str) -> frozenset[str] | None:
    try:
        expression = _parse_expression(task_input)
    except (TypeError, ValueError, RecursionError):
        return None
    if not expression or expression[0] != "define":
        return None
    problems = [
        child
        for child in expression[1:]
        if isinstance(child, list) and child and child[0] == "problem"
    ]
    if len(problems) != 1 or len(problems[0]) != 2:
        return None
    if not all(isinstance(part, str) and part for part in problems[0]):
        return None
    sections = [
        child
        for child in expression[1:]
        if isinstance(child, list) and child and child[0] == ":goal"
    ]
    if len(sections) != 1 or len(sections[0]) != 2:
        return None
    section = sections[0]
    goal = section[1]
    if not isinstance(goal, list) or not goal:
        return None
    if goal[0] == "and":
        if len(goal) == 1:
            return None
        predicates = goal[1:]
    else:
        predicates = [goal]
    if not predicates or any(not _atomic_predicate(value) for value in predicates):
        return None
    if any(value[0] in _UNSUPPORTED_OPERATORS for value in predicates):
        return None
    if any(part.startswith("?") for value in predicates for part in value):
        return None
    return frozenset(_format_predicate(value) for value in predicates)


def _state_predicates(values: Any) -> frozenset[str] | None:
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        return None
    predicates = []
    for value in values:
        try:
            expression = _parse_expression(value)
        except (ValueError, RecursionError):
            return None
        if not _atomic_predicate(expression):
            return None
        predicates.append(_format_predicate(expression))
    return frozenset(predicates)


def _atomic_predicate(value: Any) -> bool:
    return bool(value) and all(isinstance(part, str) for part in value)


def _format_predicate(value: list[str]) -> str:
    return "(" + " ".join(value) + ")"


def _predicate_name(value: str) -> str | None:
    parts = value[1:-1].split()
    return parts[0] if parts else None


def _parse_expression(text: str) -> list[Any]:
    if not isinstance(text, str):
        raise TypeError("formal expression must be text")
    tokens = _TOKEN_RE.findall(_COMMENT_RE.sub("", text.lower()))
    if not tokens or tokens[0] != "(":
        raise ValueError("formal expression must start with an opening parenthesis")
    position = 0

    def parse() -> list[Any]:
        nonlocal position
        if position >= len(tokens) or tokens[position] != "(":
            raise ValueError("expected opening parenthesis")
        position += 1
        expression = []
        while position < len(tokens):
            token = tokens[position]
            if token == ")":
                position += 1
                return expression
            if token == "(":
                expression.append(parse())
            else:
                expression.append(token)
                position += 1
        raise ValueError("unclosed parenthesis")

    result = parse()
    if position != len(tokens):
        raise ValueError("unexpected tokens after formal expression")
    return result
