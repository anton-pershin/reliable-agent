"""Probe direct nonempty next-action generation against complete-plan first actions."""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings

from agent_validation.blocks_world import TOOL_DESCRIPTIONS, BlocksWorldEnvironment
from reliable_agent.contracts import PlanCandidate
from reliable_agent.planning import vote_plans

PROBLEMS = Path(
    "/home/tony/reps/github/anton-pershin/agent-validation/config/blocks_world/problems"
)
TASK_IDS = [
    "stack_ab",
    "stack_ba",
    "stack_ca",
    "restack_abc",
    "restack_bac",
    "restack_cab",
    "stack_three",
    "tower_four",
]
SAMPLES = 5
ORIGINAL_INSTRUCTIONS = "Solve the Blocks World task in the supplied PDDL problem. Use the available actions and observations. Declare completion only after the goal is satisfied. Return a concise answer, confidence, likely_incorrect, and a short reason."
DIRECT_INSTRUCTIONS = """You choose the single next action from public task information and observations.
Return exactly one DirectAction, never a plan, empty response, or final response. Use only the
public tools and their argument schemas. Check every declared precondition against the latest public
state. Choose a valid action that makes the most progress toward satisfying every goal predicate
with its exact argument order. If no available action directly establishes a missing goal predicate,
choose the first action needed to establish the preconditions of a future goal-producing action.
Avoid irrelevant actions, actions that undo satisfied goal predicates, and actions that repeat an
observed no-progress cycle. Use only public information; do not ask for reference plans or scores.
"""


class DirectAction(BaseModel):
    name: Literal["get_action_catalog", "pick_up", "put_down", "stack", "unstack"] = Field(
        description="Exact name of a public tool"
    )
    arguments: dict[str, str]


def action_key(action: dict) -> str:
    return json.dumps([action["name"], action["arguments"]], sort_keys=True)


def all_actions(problem_path: Path) -> list[dict]:
    text = problem_path.read_text()
    match = re.search(r"\(:objects\s+([^)]+)\)", text)
    objects = []
    if match:
        objects = [token for token in match.group(1).split() if token != "-" and token != "block"]
    actions = []
    for name in ("pick_up", "put_down"):
        actions.extend({"name": name, "arguments": {"block": obj}} for obj in objects)
    for name in ("stack", "unstack"):
        actions.extend(
            {"name": name, "arguments": {"block": first, "other_block": second}}
            for first in objects
            for second in objects
            if first != second
        )
    return actions


def shortest_distance(initial: BlocksWorldEnvironment, actions: list[dict]) -> int | None:
    if initial.goal_satisfied():
        return 0
    queue = deque([(initial, 0)])
    visited = {tuple(sorted(initial._state))}
    while queue:
        environment, depth = queue.popleft()
        if depth >= 20:
            continue
        for action in actions:
            next_environment = copy.deepcopy(environment)
            result = next_environment.execute(action)
            if result["status"] != "ok":
                continue
            state = tuple(sorted(next_environment._state))
            if state in visited:
                continue
            if next_environment.goal_satisfied():
                return depth + 1
            visited.add(state)
            queue.append((next_environment, depth + 1))
    return None


def optimal_first_actions(problem_path: Path) -> set[str]:
    initial = BlocksWorldEnvironment.from_pddl(problem_path)
    actions = all_actions(problem_path)
    distance = shortest_distance(initial, actions)
    first_actions = set()
    for action in actions:
        next_environment = copy.deepcopy(initial)
        result = next_environment.execute(action)
        if result["status"] != "ok":
            continue
        remaining = shortest_distance(next_environment, actions)
        if remaining is not None and remaining + 1 == distance:
            first_actions.add(action_key(action))
    return first_actions


def score(problem_path: Path, action: dict, optimal: set[str]) -> dict:
    environment = BlocksWorldEnvironment.from_pddl(problem_path)
    result = environment.execute(action)
    return {
        "valid": result["status"] == "ok",
        "optimal": action_key(action) in optimal,
        "error": result["error"]["message"] if result["status"] != "ok" else None,
    }


def prompt_for(task_id: str) -> str:
    task = {
        "id": task_id,
        "instructions": ORIGINAL_INSTRUCTIONS,
        "input": (PROBLEMS / f"{task_id}.pddl").read_text(),
        "tools": TOOL_DESCRIPTIONS,
    }
    return json.dumps(
        {
            "task": task,
            "action_attempts": 0,
            "remaining_action_attempts": 45,
            "history": [],
            "validation_feedback": [],
            "format": "Return DirectAction only",
        },
        ensure_ascii=False,
    )


async def sample_one(task_id: str, sample: int, semaphore: asyncio.Semaphore) -> dict:
    started = time.monotonic()
    async with semaphore:
        try:
            agent = Agent(
                "openai:qwen/qwen3.5-9b",
                output_type=DirectAction,
                instructions=DIRECT_INSTRUCTIONS,
                model_settings=ModelSettings(temperature=0.7, max_tokens=2000),
                retries=1,
            )
            result = await agent.run(prompt_for(task_id), timeout=90)
            action = result.output.model_dump()
            error = None
        except Exception as exc:
            return {
                "task_id": task_id,
                "sample": sample,
                "elapsed": round(time.monotonic() - started, 2),
                "request_error": f"{type(exc).__name__}: {exc}"[:500],
            }
    return {
        "task_id": task_id,
        "sample": sample,
        "elapsed": round(time.monotonic() - started, 2),
        "request_error": error,
        "action": action,
    }


def voted_action(group: list[dict]) -> dict | None:
    candidates = [
        (result["sample"], PlanCandidate(actions=[result["action"]]))
        for result in group
        if "action" in result
    ]
    if not candidates:
        return None
    winner = vote_plans(candidates)[1]
    return winner.actions[0].model_dump()


def main_summary(results: list[dict]) -> None:
    prior = json.loads(Path("/tmp/opencode/ac3-invariant-plan-probe.json").read_text())
    for task_id in TASK_IDS:
        problem_path = PROBLEMS / f"{task_id}.pddl"
        optimal = optimal_first_actions(problem_path)
        group = [result for result in results if result["task_id"] == task_id]
        for result in group:
            if "action" in result:
                result.update(score(problem_path, result["action"], optimal))
        direct_vote = voted_action(group)
        direct_vote_score = (
            score(problem_path, direct_vote, optimal) if direct_vote is not None else None
        )
        print(
            f"{task_id:16s} DIRECT valid={sum(r.get('valid', False) for r in group)}/{len(group)} "
            f"optimal={sum(r.get('optimal', False) for r in group)}/{len(group)} "
            f"vote={direct_vote} vote_score={direct_vote_score}"
        )
        for strategy in ("goal_regression", "invariant_ledger"):
            old = [
                result
                for result in prior
                if result["task_id"] == task_id
                and result["strategy"] == strategy
                and result.get("candidate", {}).get("actions")
            ]
            converted = [
                {"sample": result["sample"], "action": result["candidate"]["actions"][0]}
                for result in old
            ]
            vote = voted_action(converted)
            vote_score = score(problem_path, vote, optimal) if vote is not None else None
            print(
                f"{'':16s} {strategy:18s} "
                f"valid={sum(score(problem_path, r['action'], optimal)['valid'] for r in converted)}/{SAMPLES} "
                f"optimal={sum(score(problem_path, r['action'], optimal)['optimal'] for r in converted)}/{SAMPLES} "
                f"vote_score={vote_score}"
            )
        print("  optimal first actions", sorted(optimal))
    output = Path("/tmp/opencode/ac3-direct-action-probe.json")
    output.write_text(json.dumps(results, indent=2))
    print("saved", output)


async def main() -> None:
    semaphore = asyncio.Semaphore(20)
    results = await asyncio.gather(
        *(
            sample_one(task_id, sample, semaphore)
            for task_id in TASK_IDS
            for sample in range(SAMPLES)
        )
    )
    main_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
