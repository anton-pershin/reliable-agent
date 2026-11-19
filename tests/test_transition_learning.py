from __future__ import annotations

from conftest import FakeClock, ScriptedModel, config, logger, read_logs

from reliable_agent.contracts import (
    ActionAttempt,
    ActionRequest,
    ActionResult,
    LearnedActionRule,
    PlanCandidate,
    Task,
    ToolDescription,
)
from reliable_agent.engine import DecisionEngine
from reliable_agent.goal_evidence import formal_initial_state, formal_state_predicates
from reliable_agent.transition_learning import (
    formal_transition_key,
    iter_public_actions,
    learn_action_rule,
    search_learned_plan,
)

TOOLS = [
    ToolDescription(
        name=name,
        description="Public test tool",
        arguments_schema={
            "type": "object",
            "properties": {name: {"type": "string"} for name in arguments},
            "required": list(arguments),
            "additionalProperties": False,
        },
    )
    for name, arguments in [
        ("pick_up", ["block"]),
        ("put_down", ["block"]),
        ("stack", ["block", "other_block"]),
        ("unstack", ["block", "other_block"]),
    ]
]

RESTACK = """(define (problem public-restack)
  (:domain generic)
  (:objects a b c - block)
  (:init (on a b) (on-table b) (on-table c) (clear a) (clear c) (hand-empty))
  (:goal (and (on-table a) (on b c)))
)
"""


def states(values: list[str]) -> frozenset[str]:
    result = formal_state_predicates(values)
    assert result is not None
    return result


def learned(name: str, arguments: dict, before: list[str], after: list[str]) -> LearnedActionRule:
    rule = learn_action_rule(
        ActionRequest(name=name, arguments=arguments), states(before), states(after)
    )
    assert rule is not None
    return rule


def learned_rules() -> dict[str, LearnedActionRule]:
    pick_up = learned(
        "pick_up",
        {"block": "a"},
        ["(clear a)", "(on-table a)", "(hand-empty)"],
        ["(holding a)"],
    )
    put_down = learned(
        "put_down", {"block": "a"}, ["(holding a)"], ["(clear a)", "(on-table a)", "(hand-empty)"]
    )
    stack = learned(
        "stack",
        {"block": "a", "other_block": "b"},
        ["(holding a)", "(clear b)"],
        ["(on a b)", "(clear a)", "(hand-empty)"],
    )
    unstack = learned(
        "unstack",
        {"block": "a", "other_block": "b"},
        ["(on a b)", "(clear a)", "(hand-empty)"],
        ["(holding a)", "(clear b)"],
    )
    return {rule.name: rule for rule in [pick_up, put_down, stack, unstack]}


def test_learn_action_rule_generalizes_exact_argument_tokens() -> None:
    rule = learned_rules()["pick_up"]
    assert rule.preconditions == [
        "(clear {block})",
        "(hand-empty)",
        "(on-table {block})",
    ]
    assert rule.add_effects == ["(holding {block})"]
    assert rule.delete_effects == rule.preconditions


def test_learned_rule_rejects_ambiguous_equal_argument_values() -> None:
    action = ActionRequest(name="stack", arguments={"block": "a", "other_block": "a"})
    assert learn_action_rule(action, states(["(holding a)"]), states(["(on a a)"])) is None


def test_search_over_learned_rules_solves_public_restack_task() -> None:
    task = Task(id="generic", instructions="Reach public goals", input=RESTACK, tools=TOOLS)
    initial = formal_initial_state(RESTACK)
    assert initial is not None
    plan, visited = search_learned_plan(
        task, initial, learned_rules(), max_states=50_000, max_actions=20
    )
    assert plan is not None
    assert [(action.name, action.arguments) for action in plan] == [
        ("unstack", {"block": "a", "other_block": "b"}),
        ("put_down", {"block": "a"}),
        ("pick_up", {"block": "b"}),
        ("stack", {"block": "b", "other_block": "c"}),
    ]
    assert visited < 50_000


def test_learned_search_respects_remaining_action_bound() -> None:
    task_input = """(define (problem public-stack)
      (:domain generic)
      (:objects a b - block)
      (:init (on-table a) (on-table b) (clear a) (clear b) (hand-empty))
      (:goal (and (on a b))))
    """
    task = Task(id="generic", instructions="Reach public goal", input=task_input, tools=TOOLS)
    initial = formal_initial_state(task_input)
    assert initial is not None
    rules = learned_rules()
    assert search_learned_plan(task, initial, rules, max_states=1000, max_actions=1)[0] is None
    plan, _ = search_learned_plan(task, initial, rules, max_states=1000, max_actions=2)
    assert plan is not None and len(plan) == 2


def test_learned_search_skips_observed_failed_formal_transition() -> None:
    task_input = """(define (problem public-stack)
      (:domain generic)
      (:objects a b - block)
      (:init (on-table a) (on-table b) (clear a) (clear b) (hand-empty))
      (:goal (and (on a b))))
    """
    task = Task(id="generic", instructions="Reach public goal", input=task_input, tools=TOOLS)
    initial = formal_initial_state(task_input)
    assert initial is not None
    failed_action = ActionRequest(name="pick_up", arguments={"block": "a"})
    failed = frozenset({formal_transition_key(initial, failed_action)})
    plan, _ = search_learned_plan(
        task,
        initial,
        learned_rules(),
        max_states=1000,
        max_actions=2,
        failed_transitions=failed,
    )
    assert plan is None


def test_learned_search_honors_deadline() -> None:
    task = Task(id="generic", instructions="Reach public goals", input=RESTACK, tools=TOOLS)
    initial = formal_initial_state(RESTACK)
    assert initial is not None
    clock = FakeClock(100)
    plan, _ = search_learned_plan(
        task,
        initial,
        learned_rules(),
        max_states=1000,
        max_actions=20,
        deadline=100,
        clock=clock,
    )
    assert plan is None


async def test_engine_uses_learned_plan_without_model_sampling(task) -> None:
    task_input = """(define (problem public-pickup)
      (:domain generic)
      (:objects a b - block)
      (:init (on-table a) (clear a) (hand-empty))
      (:goal (and (holding a))))
    """
    formal_task = task.model_copy(update={"input": task_input})
    clock = FakeClock()
    event_logger, stream = logger(
        config(transition_learning_enabled=True, formal_goal_checking_enabled=True), clock=clock
    )
    model = ScriptedModel([])
    engine = DecisionEngine(model, event_logger, clock=clock)
    state = engine.new_state(formal_task)
    state.learned_action_rules["pick_up"] = learned_rules()["pick_up"]
    decision = await engine.next_decision(state)
    assert decision.actions[0] == ActionRequest(name="pick_up", arguments={"block": "a"})
    assert not model.plan_calls
    event = next(event for event in read_logs(stream) if event["event"] == "plan_selected")
    assert event["selection_source"] == "learned_public_transitions"


def test_conflicting_observed_rule_is_disabled_episode_locally(task) -> None:
    task_input = """(define (problem public-pickup)
      (:domain generic)
      (:objects a - block)
      (:init (on-table a) (clear a) (hand-empty))
      (:goal (and (holding a))))
    """
    formal_task = task.model_copy(update={"input": task_input})
    clock = FakeClock()
    event_logger, _ = logger(config(transition_learning_enabled=True), clock=clock)
    engine = DecisionEngine(ScriptedModel([]), event_logger, clock=clock)
    state = engine.new_state(formal_task)
    action = ActionRequest(name="pick_up", arguments={"block": "a"})
    engine.record_attempt(
        state,
        ActionAttempt(
            call_id="first",
            actions=[action],
            results=[ActionResult(status="ok", observation={"state": ["(holding a)"]})],
        ),
    )
    assert "pick_up" in state.learned_action_rules
    engine.record_attempt(
        state,
        ActionAttempt(
            call_id="conflict",
            actions=[action],
            results=[
                ActionResult(
                    status="ok",
                    observation={"state": ["(holding a)", "(unexpected a)"]},
                )
            ],
        ),
    )
    assert not state.learned_action_rules
    assert state.rejected_learned_actions == ["pick_up"]
    assert state.plan_broken is True
    assert state.replan_cause == "transition_rule_conflict"


def test_argument_learning_preserves_predicate_head_on_name_collision() -> None:
    rule = learned(
        "stack",
        {"block": "on", "other_block": "a"},
        ["(holding on)", "(clear a)"],
        ["(on on a)", "(clear on)", "(hand-empty)"],
    )
    assert "(on {block} {other_block})" in rule.add_effects
    assert all(not value.startswith("({") for value in rule.add_effects)


def test_learned_search_enforces_state_cap_before_enqueue() -> None:
    task = Task(id="generic", instructions="Reach public goals", input=RESTACK, tools=TOOLS)
    initial = formal_initial_state(RESTACK)
    assert initial is not None
    plan, visited = search_learned_plan(
        task, initial, learned_rules(), max_states=1, max_actions=20
    )
    assert plan is None
    assert visited == 1


def test_learned_search_deadline_checked_during_large_binding_expansion() -> None:
    class TickClock:
        def __init__(self) -> None:
            self.value = 0

        def __call__(self) -> int:
            self.value += 1
            return self.value

    objects = " ".join(f"a{index}" for index in range(64))
    task_input = (
        "(define (problem many-objects) (:domain generic) "
        f"(:objects {objects} - block) "
        "(:init (on-table a0) (clear a0) (hand-empty)) "
        "(:goal (and (holding a1))))"
    )
    task = Task(id="generic", instructions="Reach public goal", input=task_input, tools=TOOLS)
    initial = formal_initial_state(task_input)
    assert initial is not None
    clock = TickClock()
    plan, _ = search_learned_plan(
        task,
        initial,
        {"pick_up": learned_rules()["pick_up"]},
        max_states=100_000,
        max_actions=5,
        deadline=2,
        clock=clock,
    )
    assert plan is None
    assert clock.value >= 2


def test_boolean_property_schema_disables_learned_search_safely() -> None:
    modified = []
    for tool in TOOLS:
        if tool.name == "pick_up":
            tool = tool.model_copy(
                update={
                    "arguments_schema": {
                        "type": "object",
                        "properties": {"block": True},
                        "required": ["block"],
                    }
                }
            )
        modified.append(tool)
    task = Task(id="generic", instructions="Reach public goals", input=RESTACK, tools=modified)
    initial = formal_initial_state(RESTACK)
    assert initial is not None
    plan, _ = search_learned_plan(
        task, initial, learned_rules(), max_states=1000, max_actions=20
    )
    assert plan is None


def test_masked_consistent_effects_do_not_disable_existing_rule(task) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(transition_learning_enabled=True), clock=clock)
    engine = DecisionEngine(ScriptedModel([]), event_logger, clock=clock)
    state = engine.new_state(task)
    action = ActionRequest(name="pick_up", arguments={"block": "a"})
    state.learned_action_rules["pick_up"] = LearnedActionRule(
        name="pick_up", add_effects=["(p {block})", "(q {block})"]
    )
    engine._learn_observed_transition(
        state,
        states(["(p a)"]),
        ActionAttempt(
            call_id="masked",
            actions=[action],
            results=[
                ActionResult(status="ok", observation={"state": ["(p a)", "(q a)"]})
            ],
        ),
    )
    assert "pick_up" in state.learned_action_rules
    assert not state.rejected_learned_actions


def test_unexpected_noop_disables_existing_rule(task) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(transition_learning_enabled=True), clock=clock)
    engine = DecisionEngine(ScriptedModel([]), event_logger, clock=clock)
    state = engine.new_state(task)
    action = ActionRequest(name="pick_up", arguments={"block": "a"})
    state.learned_action_rules["pick_up"] = LearnedActionRule(
        name="pick_up", add_effects=["(p {block})"]
    )
    engine._learn_observed_transition(
        state,
        states([]),
        ActionAttempt(
            call_id="noop",
            actions=[action],
            results=[ActionResult(status="ok", observation={"state": []})],
        ),
    )
    assert not state.learned_action_rules
    assert state.rejected_learned_actions == ["pick_up"]


async def test_learned_planning_falls_back_when_horizon_active(task, action) -> None:
    task_input = """(define (problem public-pickup)
      (:domain generic)
      (:objects a b - block)
      (:init (on-table a) (clear a) (hand-empty))
      (:goal (and (holding a))))
    """
    formal_task = task.model_copy(update={"input": task_input})
    clock = FakeClock()
    event_logger, stream = logger(
        config(transition_learning_enabled=True, plan_execution_horizon=1), clock=clock
    )
    model = ScriptedModel([], plans=[PlanCandidate(actions=[action])])
    engine = DecisionEngine(model, event_logger, clock=clock)
    state = engine.new_state(formal_task)
    state.learned_action_rules["pick_up"] = learned_rules()["pick_up"]
    decision = await engine.next_decision(state)
    assert decision.actions == [action]
    assert len(model.plan_calls) == 1
    assert not any(event["event"] == "learned_plan" for event in read_logs(stream))


def test_public_action_iterator_uses_schema_domains_and_parameterized_tools_first() -> None:
    catalog = ToolDescription(
        name="catalog",
        description="Public metadata",
        arguments_schema={"type": "object", "properties": {}, "required": []},
    )
    pickup = next(tool for tool in TOOLS if tool.name == "pick_up")
    pickup = pickup.model_copy(
        update={
            "arguments_schema": {
                "type": "object",
                "properties": {"block": {"type": "string", "enum": ["a"]}},
                "required": ["block"],
            }
        }
    )
    task = Task(
        id="generic", instructions="Use public actions", input=RESTACK, tools=[catalog, pickup]
    )
    actions = list(iter_public_actions(task))
    assert actions == [
        ActionRequest(name="pick_up", arguments={"block": "a"}),
        ActionRequest(name="catalog", arguments={}),
    ]


async def test_permanent_failure_can_explore_unknown_action_without_model(task, action) -> None:
    task_input = """(define (problem public-exploration)
      (:domain generic)
      (:objects a b - block)
      (:init (on-table a) (clear a) (hand-empty))
      (:goal (and (holding a))))
    """
    formal_task = task.model_copy(update={"input": task_input})
    clock = FakeClock()
    event_logger, stream = logger(
        config(
            transition_learning_enabled=True,
            transition_exploration_enabled=True,
            transition_tabu_enabled=True,
            formal_goal_checking_enabled=True,
            exploration_max_candidates=1,
        ),
        clock=clock,
    )
    model = ScriptedModel([])
    engine = DecisionEngine(model, event_logger, clock=clock)
    state = engine.new_state(formal_task)
    engine.record_attempt(
        state,
        ActionAttempt(
            call_id="failed-catalog",
            actions=[action],
            results=[
                ActionResult(
                    status="error",
                    observation={"state": ["(on-table a)", "(clear a)", "(hand-empty)"]},
                    error={"type": "precondition_failed", "message": "public failure"},
                )
            ],
        ),
    )
    state.plan_rounds = 1
    state.plan_broken = True
    state.replan_cause = "action_failure"
    decision = await engine.next_decision(state)
    expected = ActionRequest(name="pick_up", arguments={"block": "a"})
    assert decision.actions == [expected]
    assert not model.plan_calls
    event = next(event for event in read_logs(stream) if event["event"] == "plan_selected")
    assert event["selection_source"] == "public_transition_exploration"
    state.learned_action_rules["pick_up"] = learned_rules()["pick_up"]
    assert engine._exploration_action(state) is None


async def test_exploration_without_tabu_uses_model_fallback(task, action) -> None:
    task_input = """(define (problem public-exploration)
      (:domain generic)
      (:objects a - block)
      (:init (on-table a) (clear a) (hand-empty))
      (:goal (and (holding a))))
    """
    formal_task = task.model_copy(update={"input": task_input})
    clock = FakeClock()
    event_logger, _ = logger(
        config(transition_learning_enabled=True, transition_exploration_enabled=True),
        clock=clock,
    )
    model = ScriptedModel([], plans=[PlanCandidate(actions=[action])])
    engine = DecisionEngine(model, event_logger, clock=clock)
    state = engine.new_state(formal_task)
    state.plan_rounds = 1
    state.plan_broken = True
    state.replan_cause = "action_failure"
    decision = await engine.next_decision(state)
    assert decision.actions == [action]
    assert len(model.plan_calls) == 1

