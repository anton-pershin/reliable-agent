"""Transport-independent asynchronous task runner."""

from __future__ import annotations

import asyncio
from typing import Protocol

from .contracts import (
    ActionAttempt,
    ActionBatch,
    FinalDecision,
    Observation,
    Task,
)
from .engine import DecisionEngine, action_signature


class ToolExecutor(Protocol):
    async def execute(self, batch: ActionBatch) -> Observation:
        pass


class TaskRunner:
    def __init__(self, engine: DecisionEngine, executor: ToolExecutor) -> None:
        self.engine = engine
        self.executor = executor

    async def run(self, task: Task) -> FinalDecision:
        state = self.engine.new_state(task)
        while True:
            decision = await self.engine.next_decision(state)
            if isinstance(decision, FinalDecision):
                return decision
            call_id = f"{state.episode_id}-call-{len(state.attempts) + 1}"
            retry_number = max(
                (
                    state.transient_retries.get(action_signature(action), 0)
                    for action in decision.actions
                ),
                default=0,
            )
            self.engine.logger.log(
                "action_request",
                call_id=call_id,
                actions=[action.model_dump() for action in decision.actions],
                retry_number=retry_number,
            )
            remaining = max(
                0.0,
                state.config.max_episode_seconds
                - (self.engine.clock() - state.started_at_monotonic),
            )
            try:
                observation = await asyncio.wait_for(
                    self.executor.execute(ActionBatch(call_id=call_id, actions=decision.actions)),
                    timeout=max(0.001, remaining),
                )
            except TimeoutError as exc:
                return self.engine.stop(state, "episode_time_exhausted", str(exc))
            except asyncio.CancelledError:
                return self.engine.stop(state, "cancelled")
            except Exception as exc:
                return self.engine.stop(state, "tool_execution_error", str(exc))
            if observation.call_id != call_id:
                return self.engine.stop(
                    state,
                    "protocol_error",
                    "Observation call identifier does not match the action request",
                )
            if len(observation.results) != len(decision.actions):
                return self.engine.stop(
                    state,
                    "protocol_error",
                    "Observation result count does not match the action batch",
                )
            attempt = ActionAttempt(
                call_id=call_id,
                actions=decision.actions,
                results=observation.results,
                retry_number=retry_number,
            )
            self.engine.record_attempt(state, attempt)


async def run_concurrently(runners: list[tuple[TaskRunner, Task]]) -> list[FinalDecision]:
    """Run independent episodes while preserving each runner's state and configuration."""
    if not runners:
        return []
    concurrency = min(runner.engine.logger.config.max_concurrency for runner, _ in runners)
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(runner: TaskRunner, task: Task) -> FinalDecision:
        async with semaphore:
            return await runner.run(task)

    return await asyncio.gather(*(bounded(runner, task) for runner, task in runners))
