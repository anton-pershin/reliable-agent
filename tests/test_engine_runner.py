from __future__ import annotations

import asyncio

from conftest import (
    FakeClock,
    ScriptedExecutor,
    ScriptedModel,
    action_decision,
    config,
    logger,
    read_logs,
)

from reliable_agent.contracts import (
    ActionBatch,
    ActionDecision,
    ActionError,
    ActionRequest,
    ActionResult,
    Observation,
)
from reliable_agent.engine import DecisionEngine
from reliable_agent.errors import ModelRequestError
from reliable_agent.runner import TaskRunner, run_concurrently


def runner_for(model, executor, event_logger, clock):
    return TaskRunner(DecisionEngine(model, event_logger, clock=clock), executor)


async def test_runner_retains_history_and_returns_final(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action), final_decision])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result is final_decision
    assert len(executor.batches) == 1
    assert model.calls[1]["attempts"] == 1
    assert executor.batches[0].call_id == "episode-test-call-1"
    events = read_logs(stream)
    assert any(event["event"] == "action_observation" for event in events)
    assert any(event["event"] == "final_decision" for event in events)


async def test_batches_share_call_id_and_count_every_member(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    second = ActionRequest(name="pick_up", arguments={"block": "a"})
    model = ScriptedModel([ActionDecision(actions=[action, second]), final_decision])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(executor.batches) == 1
    assert len(executor.batches[0].actions) == 2
    observation = next(
        event for event in read_logs(stream) if event["event"] == "action_observation"
    )
    assert observation["total_action_attempts"] == 2


async def test_transient_failure_retries_without_extra_model_call(
    task, action, final_decision
) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action), final_decision])
    transient = Observation(
        call_id="episode-test-call-1",
        results=[
            ActionResult(
                status="error",
                observation={"unchanged": True},
                error=ActionError(type="transient_failure", message="temporary"),
            )
        ],
    )
    executor = ScriptedExecutor([transient])
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert len(executor.batches) == 2
    assert executor.batches[0].actions == executor.batches[1].actions
    assert len(model.calls) == 2
    retry = next(event for event in read_logs(stream) if event["event"] == "transient_retry")
    assert retry["retry_numbers"] == [1]


async def test_transient_retry_limit_returns_failure_to_model(task, action, final_decision) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(max_transient_retries=1), clock=clock)
    model = ScriptedModel([action_decision(action), final_decision])
    first = Observation(
        call_id="episode-test-call-1",
        results=[
            ActionResult(
                status="error",
                error=ActionError(type="transient_failure", message="temporary"),
            )
        ],
    )
    second = first.model_copy(update={"call_id": "episode-test-call-2"})
    executor = ScriptedExecutor([first, second])
    await runner_for(model, executor, event_logger, clock).run(task)
    assert len(executor.batches) == 2
    assert len(model.calls) == 2


async def test_nontransient_failure_returns_to_model_without_retry(
    task, action, final_decision
) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action), final_decision])
    failure = Observation(
        call_id="episode-test-call-1",
        results=[
            ActionResult(
                status="error",
                error=ActionError(type="precondition_failed", message="invalid state"),
            )
        ],
    )
    executor = ScriptedExecutor([failure])
    await runner_for(model, executor, event_logger, clock).run(task)
    assert len(executor.batches) == 1
    assert len(model.calls) == 2


async def test_invalid_action_is_rejected_before_execution(task, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    invalid = ActionDecision(actions=[ActionRequest(name="unknown", arguments={})])
    model = ScriptedModel([invalid, final_decision])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is True
    assert not executor.batches
    assert model.calls[1]["feedback"]
    assert any(event["event"] == "decision_rejected" for event in read_logs(stream))


async def test_action_budget_stops_without_completion(task, action) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(max_action_attempts=2), clock=clock)
    model = ScriptedModel([action_decision(action), action_decision(action)])
    executor = ScriptedExecutor()
    result = await runner_for(model, executor, event_logger, clock).run(task)
    assert result.completed is False
    assert result.likely_incorrect is True
    assert len(executor.batches) == 2
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["termination_reason"] == "action_budget_exhausted"


async def test_final_response_reserve_prevents_model_request(task, action) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action)])

    class AdvancingExecutor(ScriptedExecutor):
        async def execute(self, batch):
            observation = await super().execute(batch)
            clock.advance(265)
            return observation

    result = await runner_for(model, AdvancingExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert len(model.calls) == 1
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["termination_reason"] == "episode_time_exhausted"


async def test_model_error_has_controlled_fallback(task) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel([ModelRequestError("provider unavailable")])
    result = await runner_for(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert result.likely_incorrect is True


async def test_observation_count_mismatch_is_protocol_error(task, action) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action)])
    observation = Observation(call_id="episode-test-call-1", results=[])
    result = await runner_for(model, ScriptedExecutor([observation]), event_logger, clock).run(task)
    assert result.completed is False
    assert "result count" in result.reason


async def test_tool_timeout_is_controlled(task, action) -> None:
    class SlowExecutor:
        async def execute(self, batch: ActionBatch):
            await asyncio.sleep(0.05)
            return Observation(call_id=batch.call_id, results=[])

    clock = FakeClock()
    event_logger, _ = logger(
        config(max_episode_seconds=0.01, final_response_reserve_seconds=0), clock=clock
    )
    model = ScriptedModel([action_decision(action)])
    result = await runner_for(model, SlowExecutor(), event_logger, clock).run(task)
    assert result.completed is False


async def test_concurrent_runners_do_not_share_state(task, final_decision) -> None:
    clock = FakeClock()
    first_logger, _ = logger(config(), episode_id="episode-a", clock=clock)
    second_logger, _ = logger(config(), episode_id="episode-b", clock=clock)
    first_final = final_decision.model_copy(update={"answer": "A"})
    second_final = final_decision.model_copy(update={"answer": "B"})
    runners = [
        (
            runner_for(ScriptedModel([first_final]), ScriptedExecutor(), first_logger, clock),
            task,
        ),
        (
            runner_for(ScriptedModel([second_final]), ScriptedExecutor(), second_logger, clock),
            task.model_copy(update={"id": "task-two"}),
        ),
    ]
    results = await run_concurrently(runners)
    assert [result.answer for result in results] == ["A", "B"]


async def test_logs_redact_credentials_and_keep_event_links(task, final_decision) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(sensitive_values=["short"]), clock=clock)
    secret_task = task.model_copy(update={"input": "OPENAI_API_KEY=secret-value and short"})
    model = ScriptedModel([final_decision])
    await runner_for(model, ScriptedExecutor(), event_logger, clock).run(secret_task)
    raw = stream.getvalue()
    assert "secret-value" not in raw
    assert "short" not in raw
    events = read_logs(stream)
    assert all(event["episode_id"] == "episode-test" for event in events)
    assert [event["event_index"] for event in events] == list(range(1, len(events) + 1))
    configuration = next(event for event in events if event["event"] == "configuration")
    assert configuration["config"]["max_output_tokens"] == 8000
