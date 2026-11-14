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
    PlanReview,
    Task,
    ToolDescription,
    VerificationResult,
)
from reliable_agent.errors import ModelRequestError
from reliable_agent.observability import EventLogger


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ScriptedModel:
    def __init__(
        self, decisions, plans=None, verifications=None, reviews=None, goal_reviews=None
    ) -> None:
        self.decisions = list(decisions)
        self.plans = list(plans or [])
        self.verifications = list(verifications or [])
        self.reviews = list(reviews or [])
        self.goal_review_results = list(goal_reviews or [])
        self.calls = []
        self.plan_calls = []
        self.verify_calls = []
        self.review_calls = []
        self.goal_review_calls = []

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

    async def plan(self, state, remaining_seconds):
        self.plan_calls.append(
            {
                "round": state.plan_rounds,
                "attempts": len(state.attempts),
                "remaining": remaining_seconds,
                "feedback": list(state.validation_feedback),
            }
        )
        if not self.plans:
            raise ModelRequestError("no scripted plan")
        plan = self.plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        if isinstance(plan, list):
            # A list entry scripts one distinct candidate per sample index.
            return [(index, candidate) for index, candidate in enumerate(plan)]
        return [(index, plan) for index in range(state.config.plan_samples)]

    async def review_plans(self, state, candidates, remaining_seconds):
        self.review_calls.append([index for index, _ in candidates])
        if self.reviews:
            scripted = self.reviews.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return scripted
        return {index: PlanReview(valid=True) for index, _ in candidates}

    async def goal_reviews(self, state, candidates, remaining_seconds):
        self.goal_review_calls.append([index for index, _ in candidates])
        if self.goal_review_results:
            scripted = self.goal_review_results.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return scripted
        return {
            index: VerificationResult(goal_satisfied=True, reason="scripted default")
            for index, _ in candidates
        }

    async def verify(self, state, remaining_seconds):
        self.verify_calls.append({"attempts": len(state.attempts)})
        if self.verifications:
            verdict = self.verifications.pop(0)
            if isinstance(verdict, Exception):
                raise verdict
            return verdict
        return VerificationResult(goal_satisfied=True, reason="scripted default")


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
