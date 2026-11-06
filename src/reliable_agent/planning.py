"""Candidate plan normalization and majority vote."""

from __future__ import annotations

import json

from .contracts import PlanCandidate


def normalize_plan(candidate: PlanCandidate) -> tuple[tuple[str, str], ...]:
    """Return a canonical, comparable form of a candidate plan."""
    return tuple(
        (action.name, json.dumps(action.arguments, sort_keys=True, ensure_ascii=False))
        for action in candidate.actions
    )


def vote_plans(
    candidates: list[tuple[int, PlanCandidate]],
) -> tuple[int, PlanCandidate, dict[str, int]]:
    """Select one candidate plan by a majority vote.

    `candidates` pairs each plan with the index of the sample that produced it.
    The winner is the most frequent normalized plan. Ties select the candidate
    with the lowest sample index. Returns the winning sample index, the winning
    plan, and the vote count for each distinct normalized plan.
    """
    counts: dict[tuple[tuple[str, str], ...], int] = {}
    first_index: dict[tuple[tuple[str, str], ...], int] = {}
    plans: dict[tuple[tuple[str, str], ...], PlanCandidate] = {}
    for sample_index, candidate in candidates:
        key = normalize_plan(candidate)
        counts[key] = counts.get(key, 0) + 1
        plans[key] = candidate
        if key not in first_index:
            first_index[key] = sample_index
    winner = min(counts, key=lambda key: (-counts[key], first_index[key]))
    readable = {format_plan(key): count for key, count in counts.items()}
    return first_index[winner], plans[winner], readable


def format_plan(key: tuple[tuple[str, str], ...]) -> str:
    return " -> ".join(f"{name}({arguments})" for name, arguments in key)


def derive_sub_seed(random_seed: int, sample_index: int) -> int:
    """Derive the deterministic sub-seed of one plan sample."""
    return random_seed * 1000 + sample_index
