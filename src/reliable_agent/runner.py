"""Transport-independent asynchronous task runner."""

from __future__ import annotations

import asyncio
from typing import Protocol

from .contracts import (
    ActionAttempt,
    ActionBatch,
    ActionError,
    ActionResult,
    FinalDecision,
    Observation,
    Task,
)
from .engine import DecisionEngine


class ToolExecutor(Protocol):
    async def execute(self, batch: ActionBatch) -> Observation:
        pass


class TaskRunner:
    def __init__(self, engine: DecisionEngine, executor: ToolExecutor) -> None:
        self.engine = engine
        self.executor = executor

    async def run(self, task: Task) -> FinalDecision:
        state = self.engine.new_state(task)
        attempt: ActionAttempt | None = None
        try:
            while True:
                pending_retries = list(state.pending_retry_actions)
                decision = await self.engine.next_decision(state)
                if isinstance(decision, FinalDecision):
                    return decision
                call_id = f"{state.episode_id}-call-{len(state.attempts) + 1}"
                occurrence_ids = (
                    [item.occurrence_id for item in pending_retries]
                    if pending_retries
                    else [f"{call_id}:{index}" for index in range(len(decision.actions))]
                )
                retry_number = max(
                    (item.retry_number for item in pending_retries),
                    default=0,
                )
                attempt = ActionAttempt(
                    call_id=call_id,
                    actions=decision.actions,
                    occurrence_ids=occurrence_ids,
                    retry_number=retry_number,
                )
                self.engine.logger.log(
                    "action_request",
                    call_id=call_id,
                    occurrence_ids=occurrence_ids,
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
                        self.executor.execute(
                            ActionBatch(call_id=call_id, actions=decision.actions)
                        ),
                        timeout=max(0.001, remaining),
                    )
                except TimeoutError as exc:
                    self._record_failed_attempt(state, attempt, "episode_time_exhausted", str(exc))
                    return self.engine.stop(state, "episode_time_exhausted", str(exc))
                except Exception as exc:
                    self._record_failed_attempt(state, attempt, "tool_execution_error", str(exc))
                    return self.engine.stop(state, "tool_execution_error", str(exc))
                if observation.call_id != call_id:
                    details = "Observation call identifier does not match the action request"
                    self._record_failed_attempt(state, attempt, "protocol_error", details)
                    return self.engine.stop(state, "protocol_error", details)
                if len(observation.results) != len(decision.actions):
                    details = "Observation result count does not match the action batch"
                    self._record_failed_attempt(state, attempt, "protocol_error", details)
                    return self.engine.stop(state, "protocol_error", details)
                attempt.results = observation.results
                self.engine.record_attempt(state, attempt)
                attempt = None
        except asyncio.CancelledError:
            if attempt is not None:
                self._record_failed_attempt(state, attempt, "cancelled", "Episode cancelled")
            return self.engine.stop(state, "cancelled")

    def _record_failed_attempt(
        self,
        state,
        attempt: ActionAttempt,
        error_type: str,
        message: str,
    ) -> None:
        if attempt.results:
            return
        attempt.results = [
            ActionResult(
                status="error",
                observation={"outcome": "uncertain"},
                error=ActionError(type=error_type, message=message),
            )
            for _ in attempt.actions
        ]
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
