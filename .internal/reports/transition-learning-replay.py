"""Replay whether public observed transitions enable generic remaining-plan search."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

from agent_validation.blocks_world import TOOL_DESCRIPTIONS, BlocksWorldEnvironment
from probe_world_model import ActionRule, WorldModel, environment_score, predicate, search
from analyze_ac3_candidate import goal_predicates

RUN = Path(
    "/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/"
    "20261119T064120-657465Z-6943992ba86a"
)


def objects(task_input: str) -> list[str]:
    match = re.search(r"\(:objects\s+([^)]+)\)", task_input)
    if not match:
        return []
    return [part for part in match.group(1).split() if part not in {"-", "block"}]


def templatize(value: str, arguments: dict) -> str:
    parts = predicate(value)[1:-1].split()
    replacements = {str(argument): name for name, argument in arguments.items()}
    return "(" + " ".join("{" + replacements[part] + "}" if part in replacements else part for part in parts) + ")"


def learned_rule(action: dict, before: set[str], after: set[str]) -> ActionRule:
    arguments = action["arguments"]
    added = sorted(after - before)
    deleted = sorted(before - after)
    return ActionRule(
        name=action["name"],
        # A consumed public fact is a conservative previously observed context.
        # Persistent preconditions remain unknown in this zero-GPU replay.
        preconditions=[templatize(value, arguments) for value in deleted],
        add_effects=[templatize(value, arguments) for value in added],
        delete_effects=[templatize(value, arguments) for value in deleted],
    )


def score_from_environment(environment: BlocksWorldEnvironment, plan: list[dict] | None) -> bool:
    if plan is None:
        return False
    candidate = copy.deepcopy(environment)
    for action in plan:
        if candidate.execute(action)["status"] != "ok":
            return False
    return candidate.goal_satisfied()


def replay_episode(path: Path) -> dict:
    messages = [json.loads(line)["message"] for line in (path / "protocol.jsonl").read_text().splitlines()]
    record = json.loads((path / "record.json").read_text())
    task = next(message["task"] for message in messages if message.get("type") == "task")
    environment = BlocksWorldEnvironment.from_pddl(
        Path("/home/tony/reps/github/anton-pershin/agent-validation/config/blocks_world/problems")
        / f"{record['task_id']}.pddl"
    )
    goals = sorted(goal_predicates(task["input"]))
    rules: dict[str, ActionRule] = {}
    pending = None
    before = {predicate(value) for value in environment.observation()["state"]}
    rule_changes = 0
    first_solving_step = None
    first_plan = None
    action_count = 0
    for message in messages:
        if message.get("type") == "actions":
            pending = message["actions"][0]
            continue
        if message.get("type") != "observation" or pending is None:
            continue
        action_count += 1
        result = message["results"][0]
        after = {predicate(value) for value in result.get("observation", {}).get("state", [])}
        environment_result = environment.execute(pending)
        if result["status"] == "ok" and environment_result["status"] == "ok":
            rule = learned_rule(pending, before, after)
            if rule.name in rules and rules[rule.name] != rule:
                rule_changes += 1
            rules[rule.name] = rule
        before = after
        model = WorldModel(
            objects=objects(task["input"]),
            initial_state=sorted(after),
            goals=goals,
            actions=list(rules.values()),
        )
        plan = search(model, TOOL_DESCRIPTIONS)
        if score_from_environment(environment, plan):
            first_solving_step = action_count
            first_plan = plan
            break
        pending = None
    return {
        "task_id": record["task_id"],
        "repeat": record["repeat"],
        "actual_success": record["success"],
        "actual_actions": record["action_attempts"],
        "learned_rules": sorted(rules),
        "rule_changes": rule_changes,
        "first_solving_step": first_solving_step,
        "first_plan": first_plan,
    }


def main() -> None:
    results = [replay_episode(path) for path in (RUN / "episodes").glob("*")]
    results.sort(key=lambda result: (result["repeat"], result["task_id"]))
    failures = [result for result in results if not result["actual_success"]]
    rescued = [result for result in failures if result["first_solving_step"] is not None]
    print("episodes", len(results), "actual failures", len(failures))
    print("failures with a valid learned-rule remaining plan", len(rescued))
    for result in results:
        print(
            f"{result['repeat']} {result['task_id']:16s} actual={result['actual_success']} "
            f"learned_plan_at={result['first_solving_step']} "
            f"rules={result['learned_rules']} changes={result['rule_changes']}"
        )
    output = Path("/tmp/opencode/ac3-transition-learning-replay.json")
    output.write_text(json.dumps(results, indent=2))
    print("saved", output)


if __name__ == "__main__":
    main()
