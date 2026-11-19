"""Probe model-compiled predicate transition search on public task data only."""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import re
import time
from collections import deque
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ModelSettings

from agent_validation.blocks_world import (
    TOOL_DESCRIPTIONS,
    BlocksWorldEnvironment,
    parse_problem,
)

PROBLEMS = Path(
    "/home/tony/reps/github/anton-pershin/agent-validation/config/blocks_world/problems"
)
TASK_IDS = [
    "stack_ab",
    "stack_ba",
    "restack_abc",
    "restack_bac",
    "stack_three",
    "tower_four",
    "unstack_tower",
]
SAMPLES = 3
INSTRUCTIONS = "Solve the supplied task using the available public actions and observations."

COMPILER_INSTRUCTIONS = """You compile a public task into a generic predicate transition system.
Do not return a plan and do not use task identity or external answers. Use only the supplied task,
its input, and public tool descriptions/schemas.

Return atomic string predicates such as '(predicate arg1 arg2)'. Copy initial_state and goals
from the task input without solving or changing argument order. List every public object that can
bind tool arguments in objects. For every tool that can change state, return one ActionRule:
- name must exactly match the tool name;
- preconditions are atomic predicates required immediately before the action;
- add_effects and delete_effects describe every state change from its public description;
- placeholders use exact tool argument names in braces, for example '{item}' for an 'item' argument;
- static predicates use no placeholders;
- distinct_argument_pairs contains pairs of argument names that must denote different objects.
Derive resource possession, availability, occupancy, and argument direction carefully. Do not omit
an effect needed for later preconditions. Tools with no state change may be omitted. Use no private
reasoning in the output, only the requested structured public model.
"""


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionRule(Contract):
    name: str
    preconditions: list[str] = Field(default_factory=list)
    add_effects: list[str] = Field(default_factory=list)
    delete_effects: list[str] = Field(default_factory=list)
    distinct_argument_pairs: list[tuple[str, str]] = Field(default_factory=list)


class WorldModel(Contract):
    objects: list[str]
    initial_state: list[str]
    goals: list[str]
    actions: list[ActionRule]


def predicate(text: str) -> str:
    inner = text.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    return "(" + " ".join(inner.lower().split()) + ")"


def expected_predicates(values) -> set[str]:
    return {"(" + " ".join((value[0].replace("_", "-"), *value[1:])) + ")" for value in values}


def instantiate(text: str, arguments: dict[str, str]) -> str:
    class Arguments(dict):
        def __missing__(self, key):
            raise KeyError(key)

    if re.search(r"\{[^}]+\}", text):
        text = text.format_map(Arguments(arguments))
    if "{" in text or "}" in text:
        raise ValueError("unresolved placeholder")
    return predicate(text)


def search(model: WorldModel, tools: list[dict], max_states: int = 100_000) -> list[dict] | None:
    tools_by_name = {tool["name"]: tool for tool in tools}
    rules = {rule.name: rule for rule in model.actions}
    objects = list(dict.fromkeys(model.objects))
    initial = frozenset(predicate(value) for value in model.initial_state)
    goals = frozenset(predicate(value) for value in model.goals)
    queue = deque([(initial, [])])
    visited = {initial}
    while queue and len(visited) <= max_states:
        state, plan = queue.popleft()
        if goals <= state:
            return plan
        if len(plan) >= 50:
            continue
        for name, rule in rules.items():
            tool = tools_by_name.get(name)
            if tool is None:
                continue
            properties = tool.get("arguments_schema", {}).get("properties", {})
            required = tool.get("arguments_schema", {}).get("required", [])
            if any(properties.get(argument, {}).get("type") != "string" for argument in required):
                continue
            for values in itertools.product(objects, repeat=len(required)):
                arguments = dict(zip(required, values, strict=True))
                if any(
                    arguments.get(first) == arguments.get(second)
                    for first, second in rule.distinct_argument_pairs
                ):
                    continue
                try:
                    preconditions = {
                        instantiate(value, arguments) for value in rule.preconditions
                    }
                    if not preconditions <= state:
                        continue
                    deleted = {instantiate(value, arguments) for value in rule.delete_effects}
                    added = {instantiate(value, arguments) for value in rule.add_effects}
                except (KeyError, ValueError):
                    continue
                next_state = frozenset((state - deleted) | added)
                if next_state == state or next_state in visited:
                    continue
                visited.add(next_state)
                queue.append(
                    (
                        next_state,
                        [*plan, {"name": name, "arguments": arguments}],
                    )
                )
    return None


def environment_score(problem_path: Path, plan: list[dict] | None) -> dict:
    if plan is None:
        return {"environment_valid": False, "environment_goal": False, "error": "no plan"}
    environment = BlocksWorldEnvironment.from_pddl(problem_path)
    for action in plan:
        result = environment.execute(action)
        if result["status"] != "ok":
            return {
                "environment_valid": False,
                "environment_goal": False,
                "error": result["error"]["message"],
            }
    return {
        "environment_valid": True,
        "environment_goal": environment.goal_satisfied(),
        "error": None,
    }


async def compile_one(task_id: str, sample: int, semaphore: asyncio.Semaphore) -> dict:
    problem_path = PROBLEMS / f"{task_id}.pddl"
    task_input = problem_path.read_text()
    prompt = json.dumps(
        {
            "task": {"instructions": INSTRUCTIONS, "input": task_input},
            "tools": TOOL_DESCRIPTIONS,
            "format": "Return WorldModel only",
        }
    )
    started = time.monotonic()
    async with semaphore:
        try:
            agent = Agent(
                "openai:qwen/qwen3.5-9b",
                output_type=WorldModel,
                instructions=COMPILER_INSTRUCTIONS,
                model_settings=ModelSettings(temperature=0.7, max_tokens=5000),
                retries=1,
            )
            result = await agent.run(prompt, timeout=90)
            model = result.output
            error = None
        except Exception as exc:
            return {
                "task_id": task_id,
                "sample": sample,
                "elapsed": round(time.monotonic() - started, 2),
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
    plan = search(model, TOOL_DESCRIPTIONS)
    problem = parse_problem(problem_path)
    score = environment_score(problem_path, plan)
    return {
        "task_id": task_id,
        "sample": sample,
        "elapsed": round(time.monotonic() - started, 2),
        "error": error,
        "initial_exact": {predicate(x) for x in model.initial_state}
        == expected_predicates(problem.initial_state),
        "goals_exact": {predicate(x) for x in model.goals}
        == expected_predicates(problem.goals),
        "plan": plan,
        **score,
        "world_model": model.model_dump(),
    }


async def main() -> None:
    semaphore = asyncio.Semaphore(12)
    results = await asyncio.gather(
        *(
            compile_one(task_id, sample, semaphore)
            for task_id in TASK_IDS
            for sample in range(SAMPLES)
        )
    )
    output = Path("/tmp/opencode/ac3-world-model-probe.json")
    output.write_text(json.dumps(results, indent=2))
    for result in results:
        print(
            f"{result['task_id']:16s} sample={result['sample']} "
            f"goal={result.get('environment_goal')} valid={result.get('environment_valid')} "
            f"initial={result.get('initial_exact')} goals={result.get('goals_exact')} "
            f"plan={len(result['plan']) if result.get('plan') is not None else '-'} "
            f"seconds={result['elapsed']} error={result.get('error')}",
            flush=True,
        )
    print("solved", sum(result.get("environment_goal", False) for result in results), "/", len(results))
    print("saved", output)


if __name__ == "__main__":
    asyncio.run(main())
