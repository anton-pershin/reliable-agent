"""Compare public planning instructions by free offline plan sampling."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from pydantic_ai import Agent, ModelSettings

from agent_validation.blocks_world import TOOL_DESCRIPTIONS, BlocksWorldEnvironment
from reliable_agent.contracts import PlanCandidate
from reliable_agent.model import _PLAN_GOAL_REGRESSION_INSTRUCTIONS, _PLAN_INSTRUCTIONS
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
INVARIANT_INSTRUCTIONS = _PLAN_INSTRUCTIONS + """Before choosing the actions, privately build a transition ledger with one
entry per proposed action. For each entry identify: (1) every public fact and resource that the
action requires immediately before it runs; (2) every fact or resource the action consumes or makes
unavailable; (3) every fact or resource it establishes; and (4) the goal predicates still outstanding
afterward. Use the tool descriptions to derive these entries; do not assume effects that are not
supported by public information.

If an action requires a fact that is currently false, insert earlier actions that establish that fact
before using it. Never assume that possession, availability, accessibility, or occupancy persists
after an action consumes or changes it. When an action changes a relationship, remove the old
incompatible relationship before checking later actions. Recheck every subsequent precondition
against the updated ledger, not the original state. Finally, verify that the last ledger contains
every goal predicate with its exact argument order and that no action is invalid at its position.
Return only the resulting forward-ordered PlanCandidate; keep the ledger as private reasoning.
"""
STRATEGIES = {
    "goal_regression": _PLAN_GOAL_REGRESSION_INSTRUCTIONS,
    "invariant_ledger": INVARIANT_INSTRUCTIONS,
}


def environment_score(problem_path: Path, candidate: PlanCandidate) -> dict:
    environment = BlocksWorldEnvironment.from_pddl(problem_path)
    valid_prefix = 0
    error = None
    for action in candidate.actions:
        result = environment.execute(action.model_dump())
        if result["status"] != "ok":
            error = result["error"]["message"]
            break
        valid_prefix += 1
    return {
        "valid_prefix": valid_prefix,
        "valid_complete": error is None,
        "solves": error is None and environment.goal_satisfied(),
        "error": error,
    }


def prompt_for(task_id: str) -> str:
    problem_path = PROBLEMS / f"{task_id}.pddl"
    task = {
        "id": task_id,
        "instructions": ORIGINAL_INSTRUCTIONS,
        "input": problem_path.read_text(),
        "tools": TOOL_DESCRIPTIONS,
    }
    return json.dumps(
        {
            "task": task,
            "action_attempts": 0,
            "remaining_action_attempts": 45,
            "history": [],
            "validation_feedback": [],
            "prompt_version": "consistent-planning-v1",
            "format": "Return PlanCandidate only",
        },
        ensure_ascii=False,
    )


async def sample_one(
    task_id: str, strategy: str, sample: int, semaphore: asyncio.Semaphore
) -> dict:
    started = time.monotonic()
    async with semaphore:
        try:
            agent = Agent(
                "openai:qwen/qwen3.5-9b",
                output_type=PlanCandidate,
                instructions=STRATEGIES[strategy],
                model_settings=ModelSettings(temperature=0.7, max_tokens=3000),
                retries=1,
            )
            result = await agent.run(prompt_for(task_id), timeout=90)
            candidate = result.output
            error = None
        except Exception as exc:
            return {
                "task_id": task_id,
                "strategy": strategy,
                "sample": sample,
                "elapsed": round(time.monotonic() - started, 2),
                "request_error": f"{type(exc).__name__}: {exc}"[:500],
            }
    score = environment_score(PROBLEMS / f"{task_id}.pddl", candidate)
    return {
        "task_id": task_id,
        "strategy": strategy,
        "sample": sample,
        "elapsed": round(time.monotonic() - started, 2),
        "request_error": error,
        "candidate": candidate.model_dump(),
        **score,
    }


def summarize(results: list[dict]) -> None:
    for strategy in STRATEGIES:
        print("\nSTRATEGY", strategy)
        strategy_results = [result for result in results if result["strategy"] == strategy]
        for task_id in TASK_IDS:
            group = [result for result in strategy_results if result["task_id"] == task_id]
            candidates = [
                (result["sample"], PlanCandidate(**result["candidate"]))
                for result in group
                if "candidate" in result
            ]
            voted = None
            top_count = 0
            if candidates:
                _, winner, counts = vote_plans(candidates, horizon=1)
                voted = environment_score(PROBLEMS / f"{task_id}.pddl", winner)["solves"]
                top_count = max(counts.values())
            print(
                f"{task_id:16s} solves={sum(r.get('solves', False) for r in group)}/{len(group)} "
                f"valid={sum(r.get('valid_complete', False) for r in group)}/{len(group)} "
                f"voted={voted} top_first_action_votes={top_count} "
                f"mean_valid_prefix={sum(r.get('valid_prefix', 0) for r in group) / len(group):.1f} "
                f"request_errors={sum(bool(r.get('request_error')) for r in group)}"
            )
        print(
            "TOTAL",
            "sample_solves",
            sum(result.get("solves", False) for result in strategy_results),
            "/",
            len(strategy_results),
            "voted_task_solves",
            sum(
                (
                    lambda candidates: (
                        environment_score(
                            PROBLEMS / f"{task_id}.pddl",
                            vote_plans(candidates, horizon=1)[1],
                        )["solves"]
                        if candidates
                        else False
                    )
                )(
                    [
                        (result["sample"], PlanCandidate(**result["candidate"]))
                        for result in strategy_results
                        if result["task_id"] == task_id and "candidate" in result
                    ]
                )
                for task_id in TASK_IDS
            ),
            "/",
            len(TASK_IDS),
        )


async def main() -> None:
    semaphore = asyncio.Semaphore(20)
    results = await asyncio.gather(
        *(
            sample_one(task_id, strategy, sample, semaphore)
            for strategy in STRATEGIES
            for task_id in TASK_IDS
            for sample in range(SAMPLES)
        )
    )
    output = Path("/tmp/opencode/ac3-invariant-plan-probe.json")
    output.write_text(json.dumps(results, indent=2))
    summarize(results)
    print("saved", output)


if __name__ == "__main__":
    asyncio.run(main())
