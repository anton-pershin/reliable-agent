"""Tests for consistent planning: plan votes, execution, verification, and guards."""

from __future__ import annotations

import json

import pytest
from conftest import (
    FakeClock,
    ScriptedExecutor,
    ScriptedModel,
    config,
    logger,
    read_logs,
)
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from reliable_agent.config import config_from_overrides
from reliable_agent.contracts import (
    ActionDecision,
    ActionError,
    ActionRequest,
    ActionResult,
    Observation,
    PlanCandidate,
    PlanReview,
    VerificationResult,
)
from reliable_agent.engine import DecisionEngine
from reliable_agent.errors import ModelRequestError
from reliable_agent.model import PydanticAIModelClient
from reliable_agent.planning import derive_sub_seed, normalize_plan, vote_plans
from reliable_agent.runner import TaskRunner


def runner_for(model, executor, event_logger, clock):
    return TaskRunner(DecisionEngine(model, event_logger, clock=clock), executor)


def plan_of(*actions: ActionRequest) -> PlanCandidate:
    return PlanCandidate(actions=list(actions))


def partial_plan_of(*actions: ActionRequest) -> PlanCandidate:
    return PlanCandidate(actions=list(actions), reaches_goal=False)


def ok_observation(call_id: str, count: int = 1) -> Observation:
    return Observation(
        call_id=call_id,
        results=[ActionResult(status="ok", observation={"state": ["public"]})] * count,
    )


def failed_observation(call_id: str, error_type: str = "precondition_failed") -> Observation:
    return Observation(
        call_id=call_id,
        results=[
            ActionResult(
                status="error",
                error=ActionError(type=error_type, message="public failure"),
            )
        ],
    )


# AC1: plan contracts and vote


def test_vote_selects_majority_plan(action) -> None:
    other = ActionRequest(name="pick_up", arguments={"block": "a"})
    majority = plan_of(action)
    minority = plan_of(other)
    index, winner, counts = vote_plans([(0, minority), (1, majority), (2, majority)])
    assert index == 1
    assert winner == majority
    assert list(counts.values()) == [1, 2]


def test_vote_tie_selects_lowest_sample_index(action) -> None:
    first = plan_of(action)
    second = plan_of(ActionRequest(name="pick_up", arguments={"block": "a"}))
    index, winner, _ = vote_plans([(0, second), (1, first), (2, second)])
    assert index == 0
    assert winner == second


def test_vote_ignores_argument_order_in_json(action) -> None:
    one = PlanCandidate(
        actions=[ActionRequest(name="pick_up", arguments={"a": 1, "b": 2})],
    )
    reordered = PlanCandidate(
        actions=[ActionRequest(name="pick_up", arguments={"b": 2, "a": 1})],
    )
    assert normalize_plan(one) == normalize_plan(reordered)


def test_derive_sub_seed_is_deterministic() -> None:
    assert derive_sub_seed(7, 0) == 7000
    assert derive_sub_seed(7, 2) == 7002
    assert derive_sub_seed(7, 1) == derive_sub_seed(7, 1)
    assert derive_sub_seed(8, 0) != derive_sub_seed(7, 0)


def test_plan_candidate_allows_empty_completion_claim() -> None:
    candidate = PlanCandidate(actions=[], reaches_goal=True)
    assert candidate.reaches_goal is True
    assert PlanCandidate(actions=[]).reaches_goal is True


# AC2: execution and re-planning


async def test_plan_is_executed_in_order_then_final(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    model = ScriptedModel([], plans=[plan_of(action, second)])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert result.likely_incorrect is False
    assert [batch.actions for batch in executor.batches] == [[action], [second]]
    assert len(model.plan_calls) == 1
    assert len(model.verify_calls) == 1
    assert not model.calls  # a verified plan needs no final model request
    events = read_logs(stream)
    assert any(event["event"] == "plan_selected" for event in events)
    assert any(event["event"] == "plan_completed" for event in events)
    final = next(event for event in events if event["event"] == "final_decision")
    assert final["verified"] is True


async def test_action_failure_triggers_replan(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action), plan_of(second)],
    )
    executor = ScriptedExecutor(
        [failed_observation("episode-test-call-1"), ok_observation("episode-test-call-2")]
    )
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.plan_calls) == 2
    assert model.plan_calls[1]["round"] == 2
    abandoned = next(event for event in read_logs(stream) if event["event"] == "plan_abandoned")
    assert abandoned["cause"] == "precondition_failed"
    feedback = model.plan_calls[1]["feedback"]
    assert len(feedback) == 1
    assert "get_action_catalog" in feedback[0]
    assert "public failure" in feedback[0]


async def test_transient_retry_keeps_plan_head(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    model = ScriptedModel([final_decision], plans=[plan_of(action, second)])
    executor = ScriptedExecutor(
        [
            failed_observation("episode-test-call-1", "transient_failure"),
            ok_observation("episode-test-call-2"),
            ok_observation("episode-test-call-3"),
        ]
    )
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.plan_calls) == 1
    assert [batch.actions for batch in executor.batches] == [[action], [action], [second]]


async def test_replanning_filters_previously_failed_plans(task, action, final_decision) -> None:
    first = plan_of(action)
    second = plan_of(ActionRequest(name="pick_up", arguments={"block": "a"}))

    class DiversePlanModel(ScriptedModel):
        async def plan(self, state, remaining_seconds):
            self.plan_calls.append({"round": state.plan_rounds})
            if state.plan_rounds == 1:
                return [(index, first) for index in range(3)]
            # `first` wins the raw vote 2-1; filtering removes it instead.
            return [(0, second), (1, first), (2, first)]

    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = DiversePlanModel([final_decision])
    executor = ScriptedExecutor(
        [failed_observation("episode-test-call-1"), ok_observation("episode-test-call-2")]
    )
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    # Round 2 must select `second` although `first` had the majority,
    # because `first` failed in round 1.
    assert executor.batches[1].actions == second.actions
    events = read_logs(stream)
    candidates = [e for e in events if e["event"] == "plan_candidates"]
    assert candidates[1]["already_failed"] == 2


async def test_replanning_limit_stops_episode(task, action) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(max_replans=1), clock=clock)
    model = ScriptedModel([], plans=[plan_of(action), plan_of(action)])
    executor = ScriptedExecutor(
        [failed_observation("episode-test-call-1"), failed_observation("episode-test-call-2")]
    )
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is False
    assert result.likely_incorrect is True
    assert len(model.plan_calls) == 2
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["termination_reason"] == "replanning_limit_reached"


# AC3: completion verification


async def test_failed_verification_triggers_replan(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision, final_decision],
        plans=[plan_of(action), plan_of(action)],
        verifications=[
            VerificationResult(goal_satisfied=False, reason="(on a b) is missing"),
            VerificationResult(goal_satisfied=True, reason="all goals hold"),
        ],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.plan_calls) == 2
    rejected = next(event for event in read_logs(stream) if event["event"] == "completion_rejected")
    assert "verification failed" in rejected["feedback"].lower()


async def test_failed_verification_at_replan_limit_stops(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(max_replans=0), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action)],
        verifications=[VerificationResult(goal_satisfied=False, reason="goal missing")],
    )
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert result.likely_incorrect is True
    assert result.reason


async def test_verification_unavailable_accepts_final(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action)],
        verifications=[ModelRequestError("verification timeout")],
    )
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result is final_decision
    event = next(
        event for event in read_logs(stream) if event["event"] == "completion_verification"
    )
    assert event["verdict"] == "unavailable"


async def test_verification_disabled_accepts_final(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(completion_verification=False), clock=clock)
    model = ScriptedModel([final_decision], plans=[plan_of(action)])
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result is final_decision
    assert not model.verify_calls


async def test_verified_plan_needs_no_second_verification(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel([final_decision], plans=[plan_of(action)])
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.verify_calls) == 1
    assert not model.calls


async def test_partial_plan_exhaustion_skips_verification(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(plan_horizon=2), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    model = ScriptedModel(
        [final_decision],
        plans=[partial_plan_of(action), plan_of(second)],
    )
    executor = ScriptedExecutor(
        [ok_observation("episode-test-call-1"), ok_observation("episode-test-call-2")]
    )
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.plan_calls) == 2
    assert len(model.verify_calls) == 1  # only the completing plan is verified
    events = read_logs(stream)
    assert any(event["event"] == "plan_exhausted" for event in events)
    replans = [event for event in events if event["event"] == "plan_round"]
    assert replans[1]["cause"] == "plan_exhausted"
    # The exhausted partial plan made progress: no failure feedback.
    assert model.plan_calls[1]["feedback"] == []


async def test_empty_completion_claim_triggers_verification(task, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(plan_horizon=2), clock=clock)
    model = ScriptedModel([final_decision], plans=[PlanCandidate(actions=[], reaches_goal=True)])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.verify_calls) == 1
    assert not executor.batches  # no action ever ran


async def test_empty_non_reaching_candidate_is_excluded(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(plan_horizon=2), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[PlanCandidate(actions=[], reaches_goal=False)],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    # No valid candidate: reactive fallback completes through the decision path.
    assert result is final_decision
    assert len(model.calls) == 1
    assert any(event["event"] == "reactive_fallback" for event in read_logs(stream))


async def test_horizon_instructions_mention_horizon_and_flag(task) -> None:
    event_logger, _ = logger(config(plan_horizon=2))
    client = PydanticAIModelClient(event_logger, model=TestModel())
    instructions = client._plan_instructions()
    assert "at most 2 actions" in instructions
    assert "reaches_goal" in instructions
    default_logger, _ = logger(config())
    default_client = PydanticAIModelClient(default_logger, model=TestModel())
    assert "one complete plan" in default_client._plan_instructions()


# AC7 (spec 04): plan review


async def test_review_rejects_candidate_from_vote(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    good = ActionRequest(name="pick_up", arguments={"block": "a"})
    bad_plan = plan_of(action)
    good_plan = plan_of(good)
    model = ScriptedModel(
        [final_decision],
        plans=[[bad_plan, good_plan, good_plan]],
        reviews=[
            {
                0: PlanReview(valid=False, first_invalid_action_index=0, reason="bad first step"),
                1: PlanReview(valid=True, reason="fine"),
                2: PlanReview(valid=True, reason="fine"),
            }
        ],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert [batch.actions for batch in executor.batches] == [[good]]
    events = read_logs(stream)
    review = next(event for event in events if event["event"] == "plan_review")
    assert review["rejected"] == 1
    vote = next(event for event in events if event["event"] == "plan_vote")
    assert "get_action_catalog" not in str(vote["vote_counts"])


async def test_all_rejected_candidates_trigger_replan_with_feedback(
    task, action, final_decision
) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action), plan_of(action)],
        reviews=[
            {
                index: PlanReview(valid=False, first_invalid_action_index=0, reason="bad")
                for index in range(3)
            },
            {index: PlanReview(valid=True) for index in range(3)},
        ],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(model.plan_calls) == 2
    feedback = model.plan_calls[1]["feedback"]
    assert any("validity review" in entry for entry in feedback)
    assert any("first invalid action at index 0" in entry for entry in feedback)
    events = read_logs(stream)
    assert any(event["event"] == "plan_review_rejected" for event in events)


async def test_review_failure_keeps_candidates(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action)],
        reviews=[ModelRequestError("review unavailable")],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert [batch.actions for batch in executor.batches] == [[action]]
    assert any(event["event"] == "plan_review_error" for event in read_logs(stream))


async def test_review_disabled_by_config(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(plan_review_enabled=False), clock=clock)
    model = ScriptedModel([final_decision], plans=[plan_of(action)])
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is True
    assert not model.review_calls


async def test_review_truncates_plan_at_first_invalid_action(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    third = ActionRequest(name="pick_up", arguments={"block": "b"})
    # Round 1: one candidate, invalid at index 1: only the first action survives.
    # Round 2: a valid completing plan.
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action, second), plan_of(third)],
        reviews=[
            {
                index: PlanReview(
                    valid=False, first_invalid_action_index=1, reason="bad second step"
                )
                for index in range(3)
            },
            {0: PlanReview(valid=True), 1: PlanReview(valid=True), 2: PlanReview(valid=True)},
        ],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    # The truncated prefix ran, exhausted without verification, then replanned.
    assert [batch.actions for batch in executor.batches] == [[action], [third]]
    assert len(model.verify_calls) == 1
    events = read_logs(stream)
    truncated = next(event for event in events if event["event"] == "plan_review_truncated")
    assert truncated["truncated"] == 3
    assert truncated["dropped"] == 0
    assert any(event["event"] == "plan_exhausted" for event in events)


async def test_finalization_verification_unavailable_uses_gate(
    task, action, final_decision
) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision],
        plans=[plan_of(action)],
        verifications=[ModelRequestError("verification timeout")],
    )
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result is final_decision


async def test_reactive_verification_failure_gives_feedback(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel(
        [final_decision, final_decision],
        verifications=[
            VerificationResult(goal_satisfied=False, reason="goal missing"),
        ],
    )
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result is final_decision
    assert len(model.verify_calls) == 2
    assert "verification failed" in model.calls[1]["feedback"][-1].lower()


# AC4: premature-stop guard and reactive fallback


async def test_premature_stop_is_rejected_with_feedback(task, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    giving_up = final_decision.model_copy(
        update={"completed": False, "likely_incorrect": True, "reason": "no catalog"}
    )
    model = ScriptedModel([giving_up, final_decision])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result is final_decision
    assert len(model.calls) == 2
    assert "no action has succeeded" in model.calls[1]["feedback"][-1].lower()
    assert any(event["event"] == "decision_rejected" for event in read_logs(stream))


async def test_premature_stop_accepted_after_rejection_budget(task) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(max_decision_rejections=2), clock=clock)
    giving_up = {
        "completed": False,
        "likely_incorrect": True,
        "answer": "cannot",
        "confidence": 0.0,
        "reason": "no progress possible",
    }
    from reliable_agent.contracts import FinalDecision

    stops = [FinalDecision(**giving_up), FinalDecision(**giving_up)]
    model = ScriptedModel(stops)
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert len(model.calls) == 2


async def test_stop_after_successful_action_is_not_guarded(task, action) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    from reliable_agent.contracts import FinalDecision

    stop = FinalDecision(
        completed=False,
        answer="partial",
        confidence=0.2,
        likely_incorrect=True,
        reason="one action succeeded but the goal is unreachable",
    )
    # No scripted plans: the reactive loop decides each step.
    model = ScriptedModel([ActionDecision(actions=[action]), stop])
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result is stop
    assert len(model.calls) == 2


async def test_invalid_plans_fall_back_to_reactive(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    bad_plan = plan_of(ActionRequest(name="unknown_tool", arguments={}))
    model = ScriptedModel(
        [ActionDecision(actions=[action]), final_decision],
        plans=[bad_plan],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(executor.batches) == 1
    assert any(event["event"] == "reactive_fallback" for event in read_logs(stream))


async def test_plan_request_error_falls_back_to_reactive(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel(
        [ActionDecision(actions=[action]), final_decision],
        plans=[ModelRequestError("provider unavailable")],
    )
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(executor.batches) == 1
    fallback = next(event for event in read_logs(stream) if event["event"] == "reactive_fallback")
    assert "provider unavailable" in fallback["reason"]


async def test_model_without_plan_support_uses_reactive(task, action, final_decision) -> None:
    class DecideOnly:
        def __init__(self):
            self.decisions = [ActionDecision(actions=[action]), final_decision]

        async def decide(self, state, remaining_seconds):
            return self.decisions.pop(0)

    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    result = await runner_for(DecideOnly(), ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is True
    assert any(event["event"] == "reactive_fallback" for event in read_logs(stream))


# AC5: budgets and concurrency


async def test_plan_sampling_respects_episode_budget(task, action) -> None:
    clock = FakeClock()

    class SlowPlanModel:
        async def plan(self, state, remaining_seconds):
            clock.advance(265)
            raise ModelRequestError("too slow")

        async def decide(self, state, remaining_seconds):
            raise ModelRequestError("reactive also too slow")

        async def verify(self, state, remaining_seconds):
            return VerificationResult(goal_satisfied=True, reason="ok")

    event_logger, stream = logger(config(), clock=clock)
    result = await runner_for(SlowPlanModel(), ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["termination_reason"] == "episode_time_exhausted"


async def test_concurrent_episodes_keep_separate_plans(task, action, final_decision) -> None:
    from reliable_agent.runner import run_concurrently

    clock = FakeClock()
    first_logger, _ = logger(config(), episode_id="episode-a", clock=clock)
    second_logger, _ = logger(config(), episode_id="episode-b", clock=clock)
    first_action = ActionRequest(name="pick_up", arguments={"block": "a"})
    first = (
        runner_for(
            ScriptedModel([final_decision], plans=[plan_of(action)]),
            ScriptedExecutor(),
            first_logger,
            clock,
        ),
        task,
    )
    second = (
        runner_for(
            ScriptedModel([final_decision], plans=[plan_of(first_action)]),
            ScriptedExecutor(),
            second_logger,
            clock,
        ),
        task.model_copy(update={"id": "task-two"}),
    )
    results = await run_concurrently([first, second])
    assert all(result.completed for result in results)


# AC6: observability


async def test_plan_events_are_logged_with_episode_links(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(sensitive_values=["plan-secret"]), clock=clock)
    model = ScriptedModel([final_decision], plans=[plan_of(action)])
    await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    events = read_logs(stream)
    for name in ("plan_round", "plan_candidates", "plan_vote", "plan_selected", "plan_action"):
        matches = [event for event in events if event["event"] == name]
        assert matches, name
        assert all(event["episode_id"] == "episode-test" for event in matches)
    vote = next(event for event in events if event["event"] == "plan_vote")
    assert vote["winner_sample"] == 0
    verification = next(event for event in events if event["event"] == "completion_verification")
    assert verification["goal_satisfied"] is True


# AC7: configuration


def test_planning_overrides_parse() -> None:
    parsed = config_from_overrides(
        [
            "--model",
            "test",
            "--no-planning",
            "--plan-samples",
            "5",
            "--max-replans",
            "2",
            "--no-completion-verification",
        ]
    )
    assert parsed.planning_enabled is False
    assert parsed.plan_samples == 5
    assert parsed.max_replans == 2
    assert parsed.completion_verification is False


def test_planning_defaults() -> None:
    parsed = config_from_overrides(["--model", "test"])
    assert parsed.planning_enabled is True
    assert parsed.plan_samples == 3
    assert parsed.max_replans == 12
    assert parsed.completion_verification is True


def test_invalid_plan_sample_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        config(plan_samples=0)


# AC1 (model level): sub-seeds reach the provider settings


async def test_plan_samples_use_derived_sub_seeds(task) -> None:
    seen = []

    def respond(messages, info):
        seen.append(info.model_settings.get("seed"))
        tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool.name,
                    args={"actions": [{"name": "get_action_catalog", "arguments": {}}]},
                )
            ],
            model_name="test",
        )

    event_logger, stream = logger(config(random_seed=5, plan_samples=3))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    from test_model_client import client_decision_state

    state = client_decision_state(event_logger, task)
    state.plan_rounds = 1
    candidates = await client.plan(state, 30)
    assert len(candidates) == 3
    assert set(seen) <= {5000, 5001, 5002, 5003}  # one spare sample is fired
    requests = [event for event in read_logs(stream) if event["event"] == "model_request"]
    logged_seeds = {event["generation_settings"]["random_seed"] for event in requests}
    assert logged_seeds <= {5000, 5001, 5002, 5003}
    assert {index for index, _ in candidates} <= {0, 1, 2, 3}


async def test_plan_text_mode_parses_fenced_json(task, action) -> None:
    def respond(messages, info):
        content = (
            "```json\n"
            + json.dumps({"actions": [{"name": "get_action_catalog", "arguments": {}}]})
            + "\n```"
        )
        return ModelResponse(parts=[TextPart(content=content)], model_name="test")

    event_logger, _ = logger(config(output_mode="text", plan_samples=2))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    from test_model_client import client_decision_state

    state = client_decision_state(event_logger, task)
    state.plan_rounds = 1
    candidates = await client.plan(state, 30)
    assert len(candidates) == 2
    assert candidates[0][1].actions[0].name == "get_action_catalog"


async def test_all_failed_plan_samples_raise(task) -> None:
    def respond(messages, info):
        raise RuntimeError("provider down")

    event_logger, stream = logger(config(plan_samples=2))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    from test_model_client import client_decision_state

    state = client_decision_state(event_logger, task)
    state.plan_rounds = 1
    with pytest.raises(ModelRequestError):
        await client.plan(state, 30)
    errors = [event for event in read_logs(stream) if event["event"] == "plan_sample_error"]
    assert len(errors) == 3  # plan_samples=2 plus one spare sample
