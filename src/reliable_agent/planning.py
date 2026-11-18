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


def plan_key(candidate: PlanCandidate) -> str:
    """Return the normalized plan as one stable string."""
    return format_plan(normalize_plan(candidate))


def vote_plans(
    candidates: list[tuple[int, PlanCandidate]],
) -> tuple[int, PlanCandidate, dict[str, int]]:
    """Select one candidate plan by a majority vote.

    `candidates` pairs each plan with the index of the sample that produced it.
    The winner is the most frequent normalized plan. Ties select the candidate
    with the lowest sample index. Candidates sharing that plan must unanimously
    claim completion; otherwise the winner is non-reaching. Returns the winning
    sample index, the winning plan, and the vote count for each normalized plan.
    """
    counts: dict[tuple[tuple[str, str], ...], int] = {}
    first_index: dict[tuple[tuple[str, str], ...], int] = {}
    plans: dict[tuple[tuple[str, str], ...], PlanCandidate] = {}
    reaching: dict[tuple[tuple[str, str], ...], bool] = {}
    for sample_index, candidate in candidates:
        key = normalize_plan(candidate)
        counts[key] = counts.get(key, 0) + 1
        reaching[key] = reaching.get(key, True) and candidate.reaches_goal
        if key not in first_index or sample_index < first_index[key]:
            first_index[key] = sample_index
            plans[key] = candidate
    winner = min(counts, key=lambda key: (-counts[key], first_index[key]))
    winner_plan = plans[winner]
    if not reaching[winner] and winner_plan.reaches_goal:
        # A normalized prefix may come from both a short completion claim and
        # a truncated longer plan. Do not let race completion order decide
        # whether to verify: every member must agree that the prefix completes.
        winner_plan = winner_plan.model_copy(update={"reaches_goal": False})
    readable = {format_plan(key): count for key, count in counts.items()}
    return first_index[winner], winner_plan, readable


def format_plan(key: tuple[tuple[str, str], ...]) -> str:
    return " -> ".join(f"{name}({arguments})" for name, arguments in key)


def derive_sub_seed(random_seed: int, sample_index: int) -> int:
    """Derive the deterministic sub-seed of one plan sample."""
    return random_seed * 1000 + sample_index
