"""Stateful, benchmark-independent decision policy."""

from __future__ import annotations

import time

from jsonschema import ValidationError, validators

from .contracts import (
    ActionAttempt,
    ActionDecision,
    Decision,
    FinalDecision,
    PendingRetry,
    Task,
    TaskState,
)
from .errors import ModelRequestError
from .model import DecisionModel
from .observability import EventLogger


class DecisionEngine:
    def __init__(self, model: DecisionModel, logger: EventLogger, clock=time.monotonic) -> None:
        self.model = model
        self.logger = logger
        self.clock = clock

    def new_state(self, task: Task) -> TaskState:
        state = TaskState(
            episode_id=self.logger.episode_id,
            task=task,
            config=self.logger.config,
            started_at_monotonic=self.clock(),
        )
        self.logger.log_configuration()
        self.logger.log("task_received", task=task.model_dump())
        return state

    async def next_decision(self, state: TaskState) -> Decision:
        fallback = self._budget_fallback(state)
        if fallback is not None:
            return fallback

        if state.pending_retry_actions:
            pending = list(state.pending_retry_actions)
            state.pending_retry_actions = []
            for item in pending:
                state.transient_retries[item.occurrence_id] = item.retry_number
            self.logger.log(
                "transient_retry",
                actions=[item.action.model_dump() for item in pending],
                occurrence_ids=[item.occurrence_id for item in pending],
                retry_numbers=[item.retry_number for item in pending],
            )
            return ActionDecision(actions=[item.action for item in pending])

        while True:
            fallback = self._budget_fallback(state)
            if fallback is not None:
                return fallback
            remaining = self._remaining(state) - state.config.final_response_reserve_seconds
            try:
                decision = await self.model.decide(state, remaining)
            except ModelRequestError as exc:
                return self.stop(state, "model_request_error", str(exc))
            fallback = self._budget_fallback(state)
            if fallback is not None:
                return fallback
            if isinstance(decision, FinalDecision):
                self.logger.log("final_decision", decision=decision.model_dump())
                state.termination_reason = "completed" if decision.completed else "stopped"
                self.logger.log(
                    "termination",
                    termination_reason=state.termination_reason,
                    action_attempts=state.action_attempts,
                    decision=decision.model_dump(),
                )
                return decision
            if len(decision.actions) + state.action_attempts > state.config.max_action_attempts:
                feedback = (
                    "Action batch exceeds the remaining action budget. "
                    "Return fewer actions or stop."
                )
                if not self._reject_decision(state, feedback, decision):
                    return self.stop(state, "action_budget_exhausted", feedback)
                continue
            errors = self._validation_errors(state, decision)
            if errors:
                feedback = "Invalid action decision: " + " ".join(errors)
                if not self._reject_decision(state, feedback, decision):
                    return self.stop(state, "invalid_model_decision", feedback)
                continue
            self.logger.log("action_decision", decision=decision.model_dump())
            return decision

    def record_attempt(self, state: TaskState, attempt: ActionAttempt) -> None:
        state.attempts.append(attempt)
        self.logger.log(
            "action_observation",
            call_id=attempt.call_id,
            attempt=attempt.model_dump(),
            total_action_attempts=state.action_attempts,
        )
        occurrence_ids = attempt.occurrence_ids or [
            f"{attempt.call_id}:{index}" for index in range(len(attempt.actions))
        ]
        pending = []
        for index, (action, result) in enumerate(
            zip(attempt.actions, attempt.results, strict=False)
        ):
            if result.error and result.error.type == "transient_failure":
                occurrence_id = occurrence_ids[index]
                used = state.transient_retries.get(occurrence_id, 0)
                if used < state.config.max_transient_retries:
                    pending.append(
                        PendingRetry(
                            occurrence_id=occurrence_id,
                            action=action,
                            retry_number=used + 1,
                        )
                    )
        state.pending_retry_actions = pending

    def stop(self, state: TaskState, reason: str, details: str | None = None) -> FinalDecision:
        state.termination_reason = reason
        decision = FinalDecision(
            completed=False,
            answer="Task stopped before completion.",
            confidence=0.0,
            likely_incorrect=True,
            reason=details or reason,
        )
        self.logger.log(
            "termination",
            termination_reason=reason,
            details=details,
            action_attempts=state.action_attempts,
            rejected_decisions=state.rejected_decisions,
            decision=decision.model_dump(),
        )
        return decision

    def _budget_fallback(self, state: TaskState) -> FinalDecision | None:
        if (
            state.action_attempts >= state.config.max_action_attempts
            or state.action_attempts + len(state.pending_retry_actions)
            > state.config.max_action_attempts
        ):
            return self.stop(state, "action_budget_exhausted")
        if self._remaining(state) <= state.config.final_response_reserve_seconds:
            return self.stop(state, "episode_time_exhausted")
        return None

    def _remaining(self, state: TaskState) -> float:
        elapsed = max(0.0, self.clock() - state.started_at_monotonic)
        return max(0.0, state.config.max_episode_seconds - elapsed)

    def _reject_decision(self, state: TaskState, feedback: str, decision: ActionDecision) -> bool:
        state.rejected_decisions += 1
        state.validation_feedback.append(feedback)
        self.logger.log(
            "decision_rejected",
            level="ERROR",
            feedback=feedback,
            decision=decision.model_dump(),
            rejected_decisions=state.rejected_decisions,
        )
        return state.rejected_decisions < state.config.max_decision_rejections

    @staticmethod
    def _validation_errors(state: TaskState, decision: ActionDecision) -> list[str]:
        tools = {tool.name: tool for tool in state.task.tools}
        errors = []
        for action in decision.actions:
            tool = tools.get(action.name)
            if tool is None:
                errors.append(f"Unknown tool {action.name}.")
                continue
            if not tool.arguments_schema:
                continue
            try:
                validator = validators.validator_for(tool.arguments_schema)(tool.arguments_schema)
                validator.validate(action.arguments)
            except ValidationError as exc:
                errors.append(f"Arguments for {action.name}: {exc.message}")
            except Exception as exc:
                state.validation_feedback.append(
                    f"Schema validation unavailable for {action.name}: {type(exc).__name__}"
                )
        return errors
