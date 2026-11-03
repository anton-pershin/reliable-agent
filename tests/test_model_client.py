from __future__ import annotations

import json

import pytest
from conftest import config, logger, read_logs
from pydantic_ai.exceptions import ModelRequestRejectedError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from reliable_agent.contracts import ActionAttempt, ActionDecision, FinalDecision
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
