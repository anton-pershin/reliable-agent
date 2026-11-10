from __future__ import annotations

import json

import pytest
from conftest import config, logger, read_logs
from pydantic_ai.exceptions import (
    ModelHTTPError,
    ModelRequestRejectedError,
    RunTimedOut,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from reliable_agent.contracts import (
    ActionAttempt,
    ActionDecision,
    FinalDecision,
    PlanCandidate,
)
from reliable_agent.errors import ModelRequestError
from reliable_agent.model import PydanticAIModelClient


async def test_pydantic_ai_structured_final_decision(task, final_decision) -> None:
    event_logger, stream = logger(config())

    def respond(messages, info):
        tool = next(tool for tool in info.output_tools if "FinalDecision" in tool.name)
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=final_decision.model_dump())],
            model_name="test",
            model_id="test:test",
            provider_name="test",
        )

    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    decision = await client.decide(state, 30)
    assert isinstance(decision, FinalDecision)
    assert decision.answer == "Task complete"
    events = read_logs(stream)
    response = next(event for event in events if event["event"] == "model_response")
    assert response["metadata"]["requested_model"] == "test"
    assert response["metadata"]["reported_model"] == "test:test"
    assert response["metadata"]["provider"] == "test"
    assert response["metadata"]["usage"]["requests"] == 1
    assert response["private_reasoning"] == "not-retained"


async def test_pydantic_ai_structured_action_decision(task, action) -> None:
    event_logger, _ = logger(config())
    output = ActionDecision(actions=[action]).model_dump()
    client = PydanticAIModelClient(
        event_logger,
        model=TestModel(custom_output_args=output),
    )
    state = client_decision_state(event_logger, task)
    decision = await client.decide(state, 30)
    assert isinstance(decision, ActionDecision)
    assert decision.actions[0].name == "get_action_catalog"


def client_decision_state(event_logger, task):
    from reliable_agent.contracts import TaskState

    return TaskState(
        episode_id=event_logger.episode_id,
        task=task,
        config=event_logger.config,
        started_at_monotonic=100.0,
    )


async def test_context_truncation_is_bounded_and_logged(task, action) -> None:
    event_logger, stream = logger(config(max_context_items=2))
    client = PydanticAIModelClient(event_logger, model=TestModel())
    state = client_decision_state(event_logger, task)
    for index in range(4):
        state.attempts.append(ActionAttempt(call_id=f"call-{index}", actions=[action], results=[]))
    prompt = json.loads(client._prompt(state))
    assert len(prompt["history"]) == 2
    assert prompt["history"][0]["call_id"] == "call-2"
    event = next(event for event in read_logs(stream) if event["event"] == "context_truncated")
    assert event["omitted_attempts"] == 2


async def test_structured_output_error_is_wrapped_and_logged(task, final_decision) -> None:
    event_logger, stream = logger(config())
    client = PydanticAIModelClient(
        event_logger,
        model=TestModel(custom_output_args=final_decision.model_dump()),
    )
    state = client_decision_state(event_logger, task)
    with pytest.raises(ModelRequestError):
        await client.decide(state, 30)
    event = next(event for event in read_logs(stream) if event["event"] == "model_error")
    assert event["error_type"] == "UnexpectedModelBehavior"


async def test_successful_output_repair_is_logged(task, action, final_decision) -> None:
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        tool = next(tool for tool in info.output_tools if "ActionDecision" in tool.name)
        output = (
            final_decision.model_dump()
            if calls == 1
            else ActionDecision(actions=[action]).model_dump()
        )
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=output)],
            model_name="test",
            provider_name="test",
        )

    event_logger, stream = logger(config(max_decision_retries=1))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    decision = await client.decide(state, 30)
    assert isinstance(decision, ActionDecision)
    assert calls == 2
    event = next(event for event in read_logs(stream) if event["event"] == "model_repair")
    assert event["validation_feedback"]


async def test_tool_rejection_activates_text_fallback(task, final_decision) -> None:
    calls = 0
    seen_tool_choice = None

    def respond(messages, info):
        nonlocal calls, seen_tool_choice
        calls += 1
        if calls == 1:
            raise ModelRequestRejectedError("test", "tool_choice is unsupported")
        seen_tool_choice = info.model_settings.get("tool_choice")
        return ModelResponse(
            parts=[TextPart(content=json.dumps(final_decision.model_dump()))],
            model_name="test",
            model_id="test:test",
            provider_name="test",
        )

    event_logger, stream = logger(config())
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    decision = await client.decide(state, 30)
    assert isinstance(decision, FinalDecision)
    assert calls == 2
    assert seen_tool_choice == "none"
    assert any(event["event"] == "text_fallback" for event in read_logs(stream))


async def test_text_mode_repairs_and_parses_fenced_json(task, final_decision) -> None:
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            content = "not-json"
        else:
            content = "```json\n" + json.dumps(final_decision.model_dump()) + "\n```"
        return ModelResponse(parts=[TextPart(content=content)], model_name="test")

    event_logger, stream = logger(config(output_mode="text", max_decision_retries=1))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    decision = await client.decide(state, 30)
    assert isinstance(decision, FinalDecision)
    assert calls == 2
    assert any(event["event"] == "model_repair" for event in read_logs(stream))


async def test_tool_mode_does_not_fallback(task) -> None:
    def respond(messages, info):
        raise ModelRequestRejectedError("test", "tool_choice is unsupported")

    event_logger, _ = logger(config(output_mode="tool"))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    with pytest.raises(ModelRequestError):
        await client.decide(state, 30)


def _plan_response(messages, info):
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name=tool.name,
                args={"actions": [{"name": "get_action_catalog", "arguments": {}}]},
            )
        ],
        model_name="test",
        model_id="test:test",
        provider_name="test",
    )


async def test_plan_token_cap_defaults_to_global_limit(task) -> None:
    seen = []

    def respond(messages, info):
        seen.append(info.model_settings.get("max_tokens"))
        return _plan_response(messages, info)

    event_logger, _ = logger(config(max_output_tokens=8000))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    await client.plan(state, 30)
    assert seen and all(value == 8000 for value in seen)


async def test_plan_token_cap_override_applies_to_plans_only(task, final_decision) -> None:
    seen = {}

    def respond(messages, info):
        # A single-output request (plan) has one output tool; the decision
        # union has one tool per member.
        purpose = "plan" if len(info.output_tools) == 1 else "decision"
        seen.setdefault(purpose, []).append(info.model_settings.get("max_tokens"))
        if purpose == "plan":
            return _plan_response(messages, info)
        tool = next(tool for tool in info.output_tools if "FinalDecision" in tool.name)
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=final_decision.model_dump())],
            model_name="test",
        )

    event_logger, _ = logger(config(max_output_tokens=8000, plan_max_output_tokens=1500))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    await client.plan(state, 30)
    await client.decide(state, 30)
    assert seen["plan"] and all(value == 1500 for value in seen["plan"])
    assert seen["decision"] and all(value == 8000 for value in seen["decision"])


async def test_review_plans_returns_verdicts(task) -> None:
    def respond(messages, info):
        tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool.name,
                    args={"valid": False, "first_invalid_action_index": 1, "reason": "bad"},
                )
            ],
            model_name="test",
        )

    event_logger, _ = logger(config())
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    candidates = [(0, PlanCandidate(actions=[{"name": "pick_up", "arguments": {"block": "a"}}]))]
    reviews = await client.review_plans(state, candidates, 60)
    assert reviews[0].valid is False
    assert reviews[0].first_invalid_action_index == 1


async def test_sample_retries_transient_failure_with_same_seed(task) -> None:
    calls = []

    def respond(messages, info):
        calls.append(info.model_settings.get("seed"))
        if len(calls) <= 2:
            # The first attempt of every sample fails transiently.
            raise ModelHTTPError(status_code=503, model_name="test", body="overloaded")
        return _plan_response(messages, info)

    event_logger, stream = logger(config(plan_samples=1, sample_retries=1))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    candidates = await client.plan(state, 30)
    assert len(candidates) == 1
    events = read_logs(stream)
    retries = [event for event in events if event["event"] == "sample_retry"]
    assert len(retries) >= 1
    assert all(event["purpose"] == "plan" for event in retries)
    assert {event["attempt"] for event in retries} == {2}
    # Both samples fired (1 + 1 spare) and every retry reused its sample's
    # derived sub-seed, so only two distinct seeds ever appear.
    assert len(calls) >= 3
    assert len(set(calls)) == 2


async def test_sample_retry_budget_is_bounded(task) -> None:
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        raise RunTimedOut("The agent run timed out.")

    event_logger, stream = logger(config(plan_samples=1, sample_retries=1))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    with pytest.raises(ModelRequestError):
        await client.plan(state, 30)
    # 2 samples (1 + 1 spare), each with 1 initial attempt + 1 retry.
    assert calls == 4
    events = read_logs(stream)
    assert sum(1 for event in events if event["event"] == "sample_retry") == 2


async def test_token_limit_failure_does_not_retry(task) -> None:
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        raise UnexpectedModelBehavior("Model token limit exceeded before any response")

    event_logger, stream = logger(config(plan_samples=1, sample_retries=3))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    with pytest.raises(ModelRequestError):
        await client.plan(state, 30)
    # 2 samples (1 + 1 spare), no retries for deterministic failures.
    assert calls == 2
    assert not any(event["event"] == "sample_retry" for event in read_logs(stream))


async def test_sample_retries_disabled_by_zero(task) -> None:
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        raise ModelHTTPError(status_code=503, model_name="test", body="overloaded")

    event_logger, stream = logger(config(plan_samples=1, sample_retries=0))
    client = PydanticAIModelClient(event_logger, model=FunctionModel(respond))
    state = client_decision_state(event_logger, task)
    with pytest.raises(ModelRequestError):
        await client.plan(state, 30)
    assert calls == 2
    assert not any(event["event"] == "sample_retry" for event in read_logs(stream))
