"""Episode-local learning and bounded search over public formal transitions."""

from __future__ import annotations

import itertools
import json
import re
import time
from collections import deque
from collections.abc import Callable, Iterator

from .contracts import ActionRequest, LearnedActionRule, Task
from .goal_evidence import formal_goal_predicates, formal_objects

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_-]+)\}")


def learn_action_rule(
    action: ActionRequest,
    before: frozenset[str],
    after: frozenset[str],
) -> LearnedActionRule | None:
    """Generalize one successful public transition through exact argument tokens."""
    argument_by_value = {}
    for name, value in action.arguments.items():
        if not isinstance(value, str):
            return None
        normalized = value.lower()
        if normalized in argument_by_value and argument_by_value[normalized] != name:
            # Equal argument values make placeholder generalization ambiguous.
            return None
        argument_by_value[normalized] = name
    added = sorted(after - before)
    deleted = sorted(before - after)
    if not added and not deleted:
        return None

    def template(value: str) -> str:
        parts = value[1:-1].split()
        terms = [
            "{" + argument_by_value[part] + "}" if part in argument_by_value else part
            for part in parts[1:]
        ]
        return "(" + " ".join([parts[0], *terms]) + ")"

    return LearnedActionRule(
        name=action.name,
        # Observed consumed facts are a conservative previously valid context.
        # Persistent preconditions cannot be inferred from one transition and
        # are not invented here; environment feedback remains authoritative.
        preconditions=[template(value) for value in deleted],
        add_effects=[template(value) for value in added],
        delete_effects=[template(value) for value in deleted],
    )


def formal_transition_key(state: frozenset[str], action: ActionRequest) -> str:
    """Return a type-preserving key for a formal state/action pair."""
    return json.dumps(
        [sorted(state), action.name, action.arguments],
        sort_keys=True,
        ensure_ascii=False,
    )


def predict_action_state(
    rule: LearnedActionRule,
    action: ActionRequest,
    before: frozenset[str],
) -> frozenset[str] | None:
    """Apply an existing rule to an observed pre-state for consistency checking."""
    if any(not isinstance(value, str) for value in action.arguments.values()):
        return None
    arguments = {name: value.lower() for name, value in action.arguments.items()}
    try:
        preconditions = {_instantiate(value, arguments) for value in rule.preconditions}
        if not preconditions <= before:
            return None
        deleted = {_instantiate(value, arguments) for value in rule.delete_effects}
        added = {_instantiate(value, arguments) for value in rule.add_effects}
    except (KeyError, ValueError):
        return None
    return frozenset((before - deleted) | added)


def search_learned_plan(
    task: Task,
    current_state: frozenset[str],
    rules: dict[str, LearnedActionRule],
    *,
    max_states: int,
    max_actions: int,
    failed_transitions: frozenset[str] = frozenset(),
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list[ActionRequest] | None, int]:
    """Return a shortest plan over learned rules and the number of states visited."""
    goals = formal_goal_predicates(task.input)
    objects = formal_objects(task.input)
    if goals is None or objects is None or not rules:
        return None, 0
    queue = deque([(frozenset(current_state), [])])
    visited = {frozenset(current_state)}
    binding_checks = 0
    while queue and len(visited) <= max_states:
        if deadline is not None and clock() >= deadline:
            return None, len(visited)
        state, plan = queue.popleft()
        if goals <= state:
            return plan, len(visited)
        if len(plan) >= max_actions:
            continue
        # Public tool order, sorted objects, and canonical predicates make the
        # search result independent of dictionary/observation ordering.
        for tool in task.tools:
            rule = rules.get(tool.name)
            if rule is None:
                continue
            schema = tool.arguments_schema
            required = schema.get("required", [])
            domains = _binding_domains(schema, objects)
            if domains is None:
                continue
            for values in itertools.product(*domains):
                binding_checks += 1
                if (
                    deadline is not None
                    and binding_checks % 64 == 0
                    and clock() >= deadline
                ):
                    return None, len(visited)
                arguments = dict(zip(required, values, strict=True))
                action = ActionRequest(name=tool.name, arguments=arguments)
                if formal_transition_key(state, action) in failed_transitions:
                    continue
                try:
                    preconditions = {
                        _instantiate(value, arguments) for value in rule.preconditions
                    }
                    if not preconditions <= state:
                        continue
                    deleted = {_instantiate(value, arguments) for value in rule.delete_effects}
                    added = {_instantiate(value, arguments) for value in rule.add_effects}
                except (KeyError, ValueError):
                    continue
                next_state = frozenset((state - deleted) | added)
                if next_state == state or next_state in visited:
                    continue
                if len(visited) >= max_states:
                    return None, len(visited)
                visited.add(next_state)
                queue.append((next_state, [*plan, action]))
    return None, len(visited)


def iter_public_actions(task: Task) -> Iterator[ActionRequest]:
    """Enumerate public required-argument bindings, with parameterized tools first."""
    objects = formal_objects(task.input)
    if objects is None:
        return
    ordered_tools = sorted(
        enumerate(task.tools),
        key=lambda item: (not bool(item[1].arguments_schema.get("required", [])), item[0]),
    )
    for _, tool in ordered_tools:
        schema = tool.arguments_schema
        required = schema.get("required", [])
        domains = _binding_domains(schema, objects)
        if domains is None:
            continue
        for values in itertools.product(*domains):
            yield ActionRequest(
                name=tool.name,
                arguments=dict(zip(required, values, strict=True)),
            )


def _binding_domains(schema: dict, objects: tuple[str, ...]) -> list[list[str]] | None:
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if (
        not isinstance(required, list)
        or not all(isinstance(name, str) for name in required)
        or len(set(required)) != len(required)
        or not isinstance(properties, dict)
    ):
        return None
    domains = []
    for name in required:
        definition = properties.get(name)
        if not isinstance(definition, dict) or definition.get("type") != "string":
            # Boolean subschemas, missing schemas, and non-string arguments are
            # not safe to enumerate generically.
            return None
        enum = definition.get("enum")
        if enum is None:
            domain = list(objects)
        elif isinstance(enum, list) and all(isinstance(value, str) for value in enum):
            allowed = {value.lower() for value in enum}
            domain = [value for value in objects if value in allowed]
        else:
            return None
        if not domain:
            return None
        domains.append(domain)
    return domains


def _instantiate(template: str, arguments: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in arguments:
            raise KeyError(name)
        value = arguments[name].lower()
        if "{" in value or "}" in value:
            raise ValueError("placeholder braces in public argument")
        return value

    return "(" + _PLACEHOLDER_RE.sub(replace, template[1:-1]) + ")"
