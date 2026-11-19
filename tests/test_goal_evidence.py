from __future__ import annotations

import pytest

from reliable_agent.goal_evidence import formal_goal_verdict

PDDL = """(define (problem public-example)
  (:domain generic)
  (:objects a b c)
  (:init (on-table a))
  (:goal (and (on a b) (on-table c))) ; public conjunctive goal
)
"""


def test_formal_goal_requires_exact_public_predicates_and_argument_order() -> None:
    satisfied = formal_goal_verdict(
        PDDL.upper(), ["(ON A B)", "(on-table c)", "(clear a)"]
    )
    assert satisfied is not None
    assert satisfied.goal_satisfied is True
    assert satisfied.missing_predicates == []

    rejected = formal_goal_verdict(PDDL, ["(on b a)", "(on-table c)"])
    assert rejected is not None
    assert rejected.goal_satisfied is False
    assert rejected.missing_predicates == ["(on a b)"]
    assert rejected.conflicting_predicates == ["(on b a)"]


@pytest.mark.parametrize(
    "task_input",
    [
        "(define (problem x) (:goal (or (on a b) (on b a))))",
        "(define (problem x) (:goal (not (on a b))))",
        "(define (problem x) (:goal (and)))",
        "(define (problem x) (:goal (= a a)))",
        "(define (problem x) (:goal (and (on a b) (= a a))))",
        "(not-pddl (:goal (on a b)))",
        "(define (domain x) (:goal (on a b)))",
        "(define (problem x) (:goal (on a b)) (:goal (on b a)))",
        "not a formal expression",
    ],
)
def test_unsupported_goal_formats_return_model_fallback(task_input: str) -> None:
    assert formal_goal_verdict(task_input, ["(on a b)"]) is None


def test_excessively_nested_input_returns_model_fallback() -> None:
    nested = "(" * 1500 + "x" + ")" * 1500
    assert formal_goal_verdict(nested, ["(on a b)"]) is None


@pytest.mark.parametrize("state", [["on a b"], [{"state": "(on a b)"}], "on a b"])
def test_unstructured_state_returns_model_fallback(state) -> None:
    assert formal_goal_verdict(PDDL, state) is None
