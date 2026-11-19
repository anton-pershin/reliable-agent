"""Replay whether public observed transitions enable generic remaining-plan search."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

from agent_validation.blocks_world import TOOL_DESCRIPTIONS, BlocksWorldEnvironment
from reliable_agent.contracts import ActionRequest, LearnedActionRule, Task, ToolDescription
from reliable_agent.goal_evidence import formal_initial_state, formal_state_predicates
from reliable_agent.transition_learning import learn_action_rule, search_learned_plan

RUN = Path(
    "/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/"
    "20261119T064120-657465Z-6943992ba86a"
)


def learned_rule(
    action: dict, before: frozenset[str], after: frozenset[str]
) -> LearnedActionRule | None:
    return learn_action_rule(ActionRequest(**action), before, after)


def score_from_environment(environment: BlocksWorldEnvironment, plan: list[dict] | None) -> bool:
    if plan is None:
        return False
    candidate = copy.deepcopy(environment)
    for action in plan:
        raw_action = action.model_dump() if hasattr(action, "model_dump") else action
        if candidate.execute(raw_action)["status"] != "ok":
            return False
    return candidate.goal_satisfied()


def replay_episode(path: Path) -> dict:
    messages = [json.loads(line)["message"] for line in (path / "protocol.jsonl").read_text().splitlines()]
    record = json.loads((path / "record.json").read_text())
    task = next(message["task"] for message in messages if message.get("type") == "task")
    public_task = Task(
        id=task["id"],
        instructions=task["instructions"],
        input=task["input"],
        tools=[ToolDescription(**tool) for tool in TOOL_DESCRIPTIONS],
    )
    environment = BlocksWorldEnvironment.from_pddl(
        Path("/home/tony/reps/github/anton-pershin/agent-validation/config/blocks_world/problems")
        / f"{record['task_id']}.pddl"
    )
    rules: dict[str, LearnedActionRule] = {}
    pending = None
    before = formal_initial_state(task["input"])
    assert before is not None
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
        after = formal_state_predicates(result.get("observation", {}).get("state", []))
        assert after is not None
        environment_result = environment.execute(pending)
        if result["status"] == "ok" and environment_result["status"] == "ok":
            rule = learned_rule(pending, before, after)
            if rule is not None:
                if rule.name in rules and rules[rule.name] != rule:
                    rule_changes += 1
                rules[rule.name] = rule
        before = after
        plan, _ = search_learned_plan(
            public_task,
            after,
            rules,
            max_states=50_000,
            max_actions=max(0, 45 - action_count),
        )
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
        "first_plan": (
            [action.model_dump() for action in first_plan]
            if first_plan is not None
            else None
        ),
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
    output = Path("/tmp/opencode/ac3-transition-learning-production-replay.json")
    output.write_text(json.dumps(results, indent=2))
    print("saved", output)


if __name__ == "__main__":
    main()
