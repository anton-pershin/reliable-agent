from __future__ import annotations

import io
import json

import pytest

from reliable_agent.contracts import (
    ActionBatch,
    ActionDecision,
    ActionRequest,
    ActionResult,
    AgentConfig,
    FinalDecision,
    Observation,
    Task,
    ToolDescription,
)
from reliable_agent.observability import EventLogger


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ScriptedModel:
    def __init__(self, decisions) -> None:
        self.decisions = list(decisions)
        self.calls = []

    async def decide(self, state, remaining_seconds):
        self.calls.append(
            {
                "attempts": len(state.attempts),
                "feedback": list(state.validation_feedback),
                "remaining": remaining_seconds,
                "task_id": state.task.id,
            }
        )
        decision = self.decisions.pop(0)
        if isinstance(decision, Exception):
            raise decision
        return decision


class ScriptedExecutor:
    def __init__(self, observations=None) -> None:
        self.observations = list(observations or [])
        self.batches = []

    async def execute(self, batch: ActionBatch) -> Observation:
        self.batches.append(batch)
        if self.observations:
            return self.observations.pop(0)
        return Observation(
            call_id=batch.call_id,
            results=[
                ActionResult(status="ok", observation={"state": ["public"]}) for _ in batch.actions
            ],
        )


@pytest.fixture
def task() -> Task:
    return Task(
        id="task-one",
        instructions="Complete the public objective",
        input="public PDDL input",
        tools=[
            ToolDescription(
                name="get_action_catalog",
                description="List actions",
                arguments_schema={"type": "object", "additionalProperties": False},
            ),
            ToolDescription(
                name="pick_up",
                description="Pick up a block",
                arguments_schema={
                    "type": "object",
                    "properties": {"block": {"type": "string"}},
                    "required": ["block"],
                    "additionalProperties": False,
                },
            ),
        ],
    )


@pytest.fixture
def action() -> ActionRequest:
    return ActionRequest(name="get_action_catalog", arguments={})


@pytest.fixture
def final_decision() -> FinalDecision:
    return FinalDecision(
        completed=True,
        answer="Task complete",
        confidence=0.9,
        likely_incorrect=False,
        reason="Public evidence satisfies the objective",
    )


def config(**overrides) -> AgentConfig:
    values = {"model": "test", **overrides}
    return AgentConfig(**values)


def logger(config: AgentConfig, episode_id: str = "episode-test", clock=None):
    clock = clock or FakeClock()
    stream = io.StringIO()
    return EventLogger(episode_id, config, stream=stream, clock=clock), stream


def read_logs(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def action_decision(action: ActionRequest) -> ActionDecision:
    return ActionDecision(actions=[action])
