from __future__ import annotations

import asyncio
import io
import json
import os
import time

import pytest
from conftest import (
    FakeClock,
    ScriptedExecutor,
    ScriptedModel,
    action_decision,
    config,
    logger,
    read_logs,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from reliable_agent import TaskRunner
from reliable_agent.contracts import (
    ActionBatch,
    ActionDecision,
    ActionError,
    ActionRequest,
    ActionResult,
    FinalResponse,
    Observation,
)
from reliable_agent.engine import DecisionEngine as Engine
from reliable_agent.errors import ProtocolError
from reliable_agent.model import PydanticAIModelClient
from reliable_agent.protocol import JsonLinesToolExecutor, JsonLinesTransport


def make_runner(model, executor, event_logger, clock):
    return TaskRunner(Engine(model, event_logger, clock=clock), executor)


def transient_observation(call_id: str, count: int = 1) -> Observation:
    return Observation(
        call_id=call_id,
        results=[
            ActionResult(
                status="error",
                observation={"unchanged": True},
                error=ActionError(type="transient_failure", message="temporary"),
            )
            for _ in range(count)
        ],
    )


async def test_retry_cannot_exceed_action_budget(task, action) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(max_action_attempts=1, max_transient_retries=1), clock=clock)
    model = ScriptedModel([action_decision(action)])
    executor = ScriptedExecutor([transient_observation("episode-test-call-1")])
    result = await make_runner(model, executor, event_logger, clock).run(task)
    assert result.completed is False
    assert len(executor.batches) == 1


async def test_pending_retry_batch_cannot_exceed_action_budget(task, action) -> None:
    clock = FakeClock()
    event_logger, _ = logger(config(max_action_attempts=3, max_transient_retries=1), clock=clock)
    model = ScriptedModel([ActionDecision(actions=[action, action])])
    executor = ScriptedExecutor([transient_observation("episode-test-call-1", 2)])
    result = await make_runner(model, executor, event_logger, clock).run(task)
    assert result.completed is False
    assert len(executor.batches) == 1
    assert sum(len(batch.actions) for batch in executor.batches) == 2


async def test_decision_rejection_rechecks_time_budget(task, action) -> None:
    class LateInvalidModel:
        def __init__(self):
            self.calls = 0

        async def decide(self, state, remaining_seconds):
            self.calls += 1
            clock.advance(250)
            return ActionDecision(actions=[ActionRequest(name="unknown", arguments={})])

    clock = FakeClock()
    event_logger, _ = logger(config(), clock=clock)
    model = LateInvalidModel()
    result = await make_runner(model, ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert model.calls == 1


async def test_blocked_json_read_does_not_block_event_loop(action) -> None:
    class SlowReader:
        def readline(self, size=-1):
            time.sleep(0.05)
            return (
                json.dumps(
                    {
                        "protocol_version": 1,
                        "type": "observation",
                        "call_id": "call-1",
                        "results": [],
                    }
                )
                + "\n"
            )

    executor = JsonLinesToolExecutor(JsonLinesTransport(reader=SlowReader(), writer=io.StringIO()))
    started = time.monotonic()
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await asyncio.wait_for(
            executor.execute(ActionBatch(call_id="call-1", actions=[action])), timeout=0.01
        )
    assert time.monotonic() - started < 0.04


def protocol_task(task) -> str:
    return json.dumps(
        {
            "protocol_version": 1,
            "type": "task",
            "episode_id": "episode-test",
            "task": task.model_dump(),
        }
    )


async def test_final_write_is_interrupted_at_deadline(task, final_decision, monkeypatch) -> None:
    from reliable_agent.__main__ import run_json_episode

    class SleepingWriter:
        def __init__(self):
            self.content = ""

        def write(self, value):
            time.sleep(0.06)
            self.content += value

        def flush(self):
            pass

    writer = SleepingWriter()
    transport = JsonLinesTransport(reader=io.StringIO(protocol_task(task) + "\n"), writer=writer)
    monkeypatch.setattr(
        "reliable_agent.__main__.PydanticAIModelClient",
        lambda logger: ScriptedModel([final_decision]),
    )
    started = time.monotonic()
    await run_json_episode(
        config(max_episode_seconds=0.01, final_response_reserve_seconds=0), transport
    )
    assert time.monotonic() - started < 0.04
    assert writer.content == ""


async def test_partial_final_writer_emits_no_malformed_json(
    task, final_decision, monkeypatch
) -> None:
    from reliable_agent.__main__ import run_json_episode

    class PartialWriter:
        def __init__(self):
            self.content = ""

        def write(self, value):
            self.content += value[:5]
            time.sleep(0.06)
            self.content += value[5:]

        def flush(self):
            pass

    writer = PartialWriter()
    transport = JsonLinesTransport(reader=io.StringIO(protocol_task(task) + "\n"), writer=writer)
    monkeypatch.setattr(
        "reliable_agent.__main__.PydanticAIModelClient",
        lambda logger: ScriptedModel([final_decision]),
    )
    await run_json_episode(
        config(max_episode_seconds=0.01, final_response_reserve_seconds=0), transport
    )
    assert writer.content == ""


async def test_final_delivery_uses_atomic_file_descriptor_write(final_decision) -> None:
    from reliable_agent.protocol import write_final_with_deadline

    reader, writer = os.pipe()
    transport = JsonLinesTransport(writer=os.fdopen(writer, "w"))
    delivered = await write_final_with_deadline(transport, final_decision, time.monotonic() + 1)
    assert delivered is True
    os.close(writer)
    content = os.read(reader, 10000).decode()
    os.close(reader)
    assert json.loads(content)["type"] == "final"


async def test_timed_out_action_write_cannot_follow_final(task, action, monkeypatch) -> None:
    from reliable_agent.__main__ import run_json_episode

    class SleepingWriter:
        def __init__(self):
            self.messages = []

        def write(self, value):
            time.sleep(0.06)
            self.messages.append(value)

        def flush(self):
            pass

    writer = SleepingWriter()
    transport = JsonLinesTransport(reader=io.StringIO(protocol_task(task) + "\n"), writer=writer)
    monkeypatch.setattr(
        "reliable_agent.__main__.PydanticAIModelClient",
        lambda logger: ScriptedModel([action_decision(action)]),
    )
    await run_json_episode(
        config(max_episode_seconds=0.01, final_response_reserve_seconds=0), transport
    )
    await asyncio.sleep(0.08)
    message_types = [json.loads(message)["type"] for message in writer.messages]
    assert message_types == ["actions"]


async def test_failed_observation_preserves_requested_attempt(task, action) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action)])
    observation = Observation(call_id="episode-test-call-1", results=[])
    result = await make_runner(model, ScriptedExecutor([observation]), event_logger, clock).run(
        task
    )
    assert result.completed is False
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["action_attempts"] == 1


async def test_identical_actions_have_independent_retry_allowances(
    task, action, final_decision
) -> None:
    clock = FakeClock()
    event_logger, stream = logger(config(max_transient_retries=2), clock=clock)
    model = ScriptedModel([ActionDecision(actions=[action, action]), final_decision])
    executor = ScriptedExecutor(
        [
            transient_observation("episode-test-call-1", 2),
            transient_observation("episode-test-call-2", 2),
            transient_observation("episode-test-call-3", 2),
        ]
    )
    await make_runner(model, executor, event_logger, clock).run(task)
    assert len(executor.batches) == 3
    retries = [event for event in read_logs(stream) if event["event"] == "transient_retry"]
    assert retries[0]["retry_numbers"] == [1, 1]
    assert retries[1]["retry_numbers"] == [2, 2]


async def test_model_cancellation_is_controlled_and_logged(task) -> None:
    class CancelledModel:
        async def decide(self, state, remaining_seconds):
            raise asyncio.CancelledError

    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    result = await make_runner(CancelledModel(), ScriptedExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert result.reason == "cancelled"
    assert any(event["event"] == "termination" for event in read_logs(stream))


async def test_executor_cancellation_preserves_attempt(task, action) -> None:
    class CancelledExecutor:
        async def execute(self, batch):
            raise asyncio.CancelledError

    clock = FakeClock()
    event_logger, stream = logger(config(), clock=clock)
    model = ScriptedModel([action_decision(action)])
    result = await make_runner(model, CancelledExecutor(), event_logger, clock).run(task)
    assert result.completed is False
    assert result.reason == "cancelled"
    termination = next(event for event in read_logs(stream) if event["event"] == "termination")
    assert termination["action_attempts"] == 1


def test_structured_fields_are_redacted() -> None:
    secret = "configured-secret"
    event_logger, stream = logger(config(sensitive_values=[secret]), episode_id=secret)
    event_logger.log("task_received", call_id=secret, model=secret, provider=secret)
    raw = stream.getvalue()
    assert secret not in raw


def test_quoted_json_credentials_are_redacted() -> None:
    event_logger, stream = logger(config())
    payload = '{"api_key": "unlisted-json-secret", "password":"another-secret"}'
    event_logger.log("task_received", task={"input": payload})
    raw = stream.getvalue()
    assert "unlisted-json-secret" not in raw
    assert "another-secret" not in raw


def test_main_fallback_redacts_pydantic_input(task, capsys) -> None:
    from reliable_agent.__main__ import main

    secret = "sensitive-input-value"
    payload = json.dumps(
        {
            "protocol_version": 1,
            "type": "task",
            "episode_id": "episode",
            "task": {"unexpected": secret},
        }
    )
    import sys

    original = sys.stdin
    sys.stdin = io.StringIO(payload + "\n")
    try:
        status = main(["--model", "test", "--sensitive-value", secret])
    finally:
        sys.stdin = original
    assert status == 1
    assert secret not in capsys.readouterr().err


def test_strict_boolean_flags() -> None:
    with pytest.raises(ValueError):
        FinalResponse(
            completed=1,
            answer="x",
            confidence=0.5,
            likely_incorrect="false",
            reason="invalid",
        )


def test_non_json_numbers_are_rejected(action) -> None:
    transport = JsonLinesTransport(writer=io.StringIO())
    with pytest.raises(ProtocolError):
        transport.write_actions(
            ActionBatch(
                call_id="call-1",
                actions=[ActionRequest(name="tool", arguments={"number": float("nan")})],
            )
        )


async def test_seed_is_passed_to_pydantic_ai(task, final_decision) -> None:
    seen = {}

    def respond(messages, info):
        seen["seed"] = info.model_settings.get("seed")
        tool = next(tool for tool in info.output_tools if "FinalDecision" in tool.name)
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=final_decision.model_dump())]
        )

    event_logger, _ = logger(config(random_seed=7))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    from test_model_client import client_decision_state

    await client.decide(client_decision_state(event_logger, task), 30)
    assert seen["seed"] == 7
