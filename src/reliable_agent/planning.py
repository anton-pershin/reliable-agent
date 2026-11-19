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


def plan_key(candidate: PlanCandidate, horizon: int = 0) -> str:
    """Return the normalized plan or its prefix as one stable string."""
    normalized = normalize_plan(candidate)
    if horizon > 0:
        normalized = normalized[:horizon]
    return format_plan(normalized)


def vote_plans(
    candidates: list[tuple[int, PlanCandidate]],
    *,
    horizon: int = 0,
    completion_full_plan: bool = False,
) -> tuple[int, PlanCandidate, dict[str, int]]:
    """Select one candidate plan by a majority vote.

    `candidates` pairs each plan with the index of the sample that produced it.
    When `horizon` is positive, votes compare only that many leading actions
    while the returned winner retains its full candidate actions. The winner
    is the most frequent normalized plan or prefix. Ties select the candidate
    with the lowest sample index. Candidates sharing the completion key must
    unanimously claim completion; the key is normally the voted prefix, but
    `completion_full_plan` uses the full retained plan when that is what will
    execute. Returns the winning sample index, the winning plan, and the vote
    count for each normalized plan.
    """
    counts: dict[tuple[tuple[str, str], ...], int] = {}
    first_index: dict[tuple[tuple[str, str], ...], int] = {}
    plans: dict[tuple[tuple[str, str], ...], PlanCandidate] = {}
    reaching: dict[tuple[tuple[str, str], ...], bool] = {}
    for sample_index, candidate in candidates:
        key = normalize_plan(candidate)
        if horizon > 0:
            key = key[:horizon]
        counts[key] = counts.get(key, 0) + 1
        completion_key = normalize_plan(candidate) if completion_full_plan else key
        reaching[completion_key] = (
            reaching.get(completion_key, True) and candidate.reaches_goal
        )
        if key not in first_index or sample_index < first_index[key]:
            first_index[key] = sample_index
            plans[key] = candidate
    winner = min(counts, key=lambda key: (-counts[key], first_index[key]))
    winner_plan = plans[winner]
    completion_key = normalize_plan(winner_plan) if completion_full_plan else winner
    if not reaching[completion_key] and winner_plan.reaches_goal:
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
