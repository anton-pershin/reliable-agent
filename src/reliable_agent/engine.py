"""Stateful, benchmark-independent decision policy."""

from __future__ import annotations

import json
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
from .planning import plan_key, vote_plans


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

            if state.plan_actions:
                return self._emit_plan_action(state)

            if self._needs_plan_vote(state):
                outcome = await self._plan_round(state)
                if isinstance(outcome, FinalDecision):
                    return outcome
                # Recheck budgets after the vote: it consumes episode time.
                # A selected plan is emitted at the top of the loop; a reactive
                # fallback passes through to the model request below.
                continue

            if self._needs_finalization(state):
                outcome = await self._finalize(state)
                if isinstance(outcome, FinalDecision):
                    return outcome
                # Rejected or unavailable verification: re-plan next round.
                continue

            remaining = self._remaining(state) - self._reserve(state)
            try:
                decision = await self.model.decide(state, remaining)
            except ModelRequestError as exc:
                return self.stop(state, "model_request_error", str(exc))
            fallback = self._budget_fallback(state)
            if fallback is not None:
                return fallback
            if isinstance(decision, FinalDecision):
                accepted = await self._handle_final(state, decision)
                if accepted is None:
                    continue
                if accepted is decision:
                    # The model's own final decision: log it here. Controlled
                    # stops from _handle_final already logged their termination.
                    self.logger.log("final_decision", decision=decision.model_dump())
                    state.termination_reason = "completed" if decision.completed else "stopped"
                    self.logger.log(
                        "termination",
                        termination_reason=state.termination_reason,
                        action_attempts=state.action_attempts,
                        decision=decision.model_dump(),
                    )
                return accepted
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
        self._update_plan(state, attempt)

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

    def _needs_plan_vote(self, state: TaskState) -> bool:
        if not state.config.planning_enabled or state.reactive_mode:
            return False
        if state.plan_actions:
            return False
        return state.plan_rounds == 0 or state.plan_broken

    def _needs_finalization(self, state: TaskState) -> bool:
        return (
            state.config.planning_enabled
            and not state.reactive_mode
            and state.plan_rounds > 0
            and not state.plan_actions
            and not state.plan_broken
            and self._verification_active(state)
        )

    async def _finalize(self, state: TaskState) -> FinalDecision | bool:
        """Verify a completed plan before any completion declaration.

        Returns the synthesized final decision when the goal is verified and
        False otherwise: the caller re-plans. An unavailable verification is
        treated as a rejection, because an unverified completion claim from the
        model cannot be trusted.
        """
        verdict = await self._verify_completion(state)
        if verdict is not None and verdict.goal_satisfied:
            state.termination_reason = "completed"
            decision = FinalDecision(
                completed=True,
                answer="Task objective verified as satisfied.",
                confidence=0.95,
                likely_incorrect=False,
                reason=verdict.reason or "Every goal predicate matches the latest observation.",
            )
            self.logger.log("final_decision", decision=decision.model_dump(), verified=True)
            self.logger.log(
                "termination",
                termination_reason="completed",
                action_attempts=state.action_attempts,
                decision=decision.model_dump(),
            )
            return decision
        if verdict is None:
            feedback = "Completion verification is unavailable; the plan outcome is unverified."
            state.replan_cause = "verification_unavailable"
            state.validation_feedback.append(feedback)
            state.plan_broken = True
            self.logger.log("completion_rejected", level="ERROR", feedback=feedback)
            return False
        missing = ", ".join(verdict.missing_predicates) or "unknown"
        feedback = (
            f"Completion verification failed. Missing goal predicates: {missing}. {verdict.reason}"
        )
        if verdict.conflicting_predicates:
            conflicting = ", ".join(verdict.conflicting_predicates)
            feedback += (
                f" Conflicting predicates currently true instead: {conflicting}."
                " Undo or avoid them in the next plan."
            )
        state.replan_cause = "verification_failed"
        self.logger.log("completion_rejected", level="ERROR", feedback=feedback)
        state.validation_feedback.append(feedback)
        state.plan_broken = True
        self._mark_plan_failed(state)
        return False

    @staticmethod
    def _mark_plan_failed(state: TaskState) -> None:
        if state.active_plan_key and state.active_plan_key not in state.failed_plan_keys:
            state.failed_plan_keys.append(state.active_plan_key)

    async def _plan_round(self, state: TaskState) -> str | FinalDecision | None:
        if state.plan_rounds >= 1 + state.config.max_replans:
            return self.stop(
                state,
                "replanning_limit_reached",
                f"Re-planning limit reached after {state.plan_rounds} plan rounds.",
            )
        state.plan_rounds += 1
        cause = state.replan_cause or "initial"
        self.logger.log("plan_round", plan_round=state.plan_rounds, cause=cause)
        plan_method = getattr(self.model, "plan", None)
        if plan_method is None:
            state.reactive_mode = True
            self.logger.log(
                "reactive_fallback",
                level="ERROR",
                reason="Model client does not support plan requests",
            )
            return None
        remaining = self._remaining(state) - self._reserve(state)
        try:
            candidates = await plan_method(state, remaining)
        except ModelRequestError as exc:
            state.reactive_mode = True
            self.logger.log("reactive_fallback", level="ERROR", reason=str(exc))
            return None
        valid = []
        for index, candidate in candidates:
            if not candidate.actions:
                # An empty candidate is valid only as a completion claim: the
                # objective is already satisfied and must be verified now.
                if candidate.reaches_goal:
                    valid.append((index, candidate))
                continue
            if not self._validation_errors(state, ActionDecision(actions=candidate.actions)):
                valid.append((index, candidate))
        fresh = [
            (index, candidate)
            for index, candidate in valid
            if plan_key(candidate) not in state.failed_plan_keys
        ]
        self.logger.log(
            "plan_candidates",
            plan_round=state.plan_rounds,
            samples=len(candidates),
            valid=len(valid),
            already_failed=len(valid) - len(fresh),
            candidates=[candidate.model_dump() for _, candidate in candidates],
        )
        if not valid:
            state.reactive_mode = True
            self.logger.log(
                "reactive_fallback",
                level="ERROR",
                reason="No candidate plan passed action validation",
            )
            return None
        if self._plan_review_active(state):
            remaining = self._remaining(state) - self._reserve(state)
            review_method = getattr(self.model, "review_plans", None)
            try:
                reviews = await review_method(state, valid, remaining)
            except ModelRequestError as exc:
                # A wholesale review failure must not lose the round: keep all
                # valid candidates, as if the review were disabled.
                self.logger.log(
                    "plan_review_error",
                    level="ERROR",
                    plan_round=state.plan_rounds,
                    error_message=str(exc),
                )
                reviews = {}
            rejected = [
                (index, reviews[index])
                for index, _ in valid
                if index in reviews and not reviews[index].valid
            ]
            self.logger.log(
                "plan_review",
                plan_round=state.plan_rounds,
                reviewed=len(reviews),
                rejected=len(rejected),
                verdicts=[
                    {
                        "sample_index": index,
                        "valid": reviews[index].valid,
                        "first_invalid_action_index": reviews[index].first_invalid_action_index,
                        "reason": reviews[index].reason,
                    }
                    for index, _ in valid
                    if index in reviews
                ],
            )
            if rejected:
                adjusted = []
                truncated_count = 0
                for index, candidate in valid:
                    review = reviews.get(index)
                    if review is None or review.valid:
                        adjusted.append((index, candidate))
                        continue
                    k = review.first_invalid_action_index
                    if k is None or k >= len(candidate.actions):
                        # The review cannot name a breaking action inside the
                        # plan: keep the candidate as unverified.
                        adjusted.append((index, candidate))
                        continue
                    if k == 0:
                        continue
                    # Keep the valid prefix: a reviewed plan that breaks at
                    # action k still makes progress up to k. The prefix claims
                    # no completion, so exhaustion re-plans without verify.
                    adjusted.append(
                        (
                            index,
                            candidate.model_copy(
                                update={
                                    "actions": candidate.actions[:k],
                                    "reaches_goal": False,
                                }
                            ),
                        )
                    )
                    truncated_count += 1
                self.logger.log(
                    "plan_review_truncated",
                    plan_round=state.plan_rounds,
                    truncated=truncated_count,
                    dropped=len(rejected) - truncated_count,
                )
                valid = adjusted
                fresh = [
                    (index, candidate)
                    for index, candidate in valid
                    if plan_key(candidate) not in state.failed_plan_keys
                ]
            if not valid:
                # Every candidate failed the review: name the breaking actions
                # so the next round's planner avoids them, then re-plan.
                details = "; ".join(
                    f"candidate {index}: first invalid action at index "
                    f"{review.first_invalid_action_index} ({review.reason})"
                    for index, review in rejected
                )
                state.validation_feedback.append(
                    f"All candidate plans failed the validity review. {details}"
                )
                state.plan_broken = True
                state.replan_cause = "plan_review_rejected"
                self.logger.log(
                    "plan_review_rejected",
                    level="ERROR",
                    plan_round=state.plan_rounds,
                    rejected=len(rejected),
                )
                return None
        if not fresh:
            # Every valid candidate failed before in this episode: allow repeats.
            fresh = valid
        if self._goal_review_active(state):
            # Candidates that still claim completion are eligible for the goal
            # check. Truncated prefixes make progress by construction instead.
            checkable = [
                (index, candidate)
                for index, candidate in fresh
                if candidate.actions and candidate.reaches_goal
            ]
            if checkable:
                remaining = self._remaining(state) - self._reserve(state)
                review_method = getattr(self.model, "goal_reviews", None)
                try:
                    verdicts = await review_method(state, checkable, remaining)
                except ModelRequestError as exc:
                    self.logger.log(
                        "goal_review_error",
                        level="ERROR",
                        plan_round=state.plan_rounds,
                        error_message=str(exc),
                    )
                    verdicts = {}
                goal_ok = [
                    index
                    for index, _ in checkable
                    if verdicts.get(index) and verdicts[index].goal_satisfied
                ]
                self.logger.log(
                    "goal_review",
                    plan_round=state.plan_rounds,
                    checked=len(verdicts),
                    goal_ok=len(goal_ok),
                )
                if goal_ok:
                    # The goal check separates plans that look complete from
                    # plans that actually complete: vote among the verified few.
                    fresh = [
                        (index, candidate) for index, candidate in fresh if index in goal_ok
                    ]
        winner_index, winner, counts = vote_plans(fresh)
        self.logger.log(
            "plan_vote",
            plan_round=state.plan_rounds,
            winner_sample=winner_index,
            vote_counts=counts,
        )
        state.plan_actions = list(winner.actions)
        state.plan_broken = False
        state.replan_cause = None
        state.active_plan_key = plan_key(winner)
        state.active_plan_reaches_goal = winner.reaches_goal
        self.logger.log(
            "plan_selected",
            plan_round=state.plan_rounds,
            reaches_goal=winner.reaches_goal,
            actions=[action.model_dump() for action in winner.actions],
        )
        return "planned"

    def _emit_plan_action(self, state: TaskState) -> Decision:
        action = state.plan_actions[0]
        decision = ActionDecision(actions=[action])
        self.logger.log(
            "plan_action",
            plan_round=state.plan_rounds,
            remaining_plan_actions=len(state.plan_actions),
            decision=decision.model_dump(),
        )
        return decision

    def _update_plan(self, state: TaskState, attempt: ActionAttempt) -> None:
        if not state.plan_actions or len(attempt.actions) != 1:
            return
        if attempt.actions[0] != state.plan_actions[0]:
            return
        result = attempt.results[0] if attempt.results else None
        if result is not None and result.status == "ok":
            state.plan_actions = state.plan_actions[1:]
            if not state.plan_actions:
                if state.active_plan_reaches_goal:
                    self.logger.log("plan_completed", plan_round=state.plan_rounds)
                else:
                    # A horizon-limited plan ran out without claiming
                    # completion: re-plan immediately, no verification.
                    state.plan_broken = True
                    state.replan_cause = "plan_exhausted"
                    self.logger.log("plan_exhausted", plan_round=state.plan_rounds)
            return
        if state.pending_retry_actions:
            # The plan head waits for its transient-failure retry.
            return
        cause = result.error.type if result is not None and result.error else "unknown"
        message = result.error.message if result is not None and result.error else "unknown"
        dropped = len(state.plan_actions)
        state.plan_actions = []
        state.plan_broken = True
        state.replan_cause = "action_failure"
        self._mark_plan_failed(state)
        # Make the failure salient to the next plan round: the failed attempt
        # is one entry among many in the history, while this feedback states
        # the cause directly. It uses public observation data only.
        action = attempt.actions[0]
        state.validation_feedback.append(
            f"The planned action {action.name}"
            f"({json.dumps(action.arguments, sort_keys=True, ensure_ascii=False)}) failed: "
            f"{message} Plan again from the current state."
        )
        self.logger.log(
            "plan_abandoned",
            level="ERROR",
            plan_round=state.plan_rounds,
            cause=cause,
            dropped_actions=dropped,
        )

    async def _handle_final(
        self, state: TaskState, decision: FinalDecision
    ) -> FinalDecision | None:
        if decision.completed and self._verification_active(state):
            verdict = await self._verify_completion(state)
            if verdict is not None and verdict.goal_satisfied:
                return decision
            if verdict is None:
                feedback = (
                    "Completion verification is unavailable; "
                    "the completion claim cannot be accepted."
                )
            else:
                missing = ", ".join(verdict.missing_predicates) or "unknown"
                feedback = (
                    "Completion verification failed. "
                    f"Missing goal predicates: {missing}. {verdict.reason}"
                )
            self.logger.log(
                "completion_rejected",
                level="ERROR",
                feedback=feedback,
                decision=decision.model_dump(),
            )
            if state.config.planning_enabled and not state.reactive_mode:
                state.plan_broken = True
                state.replan_cause = "verification_failed"
                state.validation_feedback.append(feedback)
                return None
            if self._reject_decision(state, feedback, decision):
                return None
            return self.stop(state, "completion_verification_failed", feedback)
        if not decision.completed and self._stop_guard_active(state):
            feedback = (
                "No action has succeeded yet and the action and time budgets remain. "
                "Use the available tools to work toward the objective, or explain why "
                "no action can help."
            )
            if self._reject_decision(state, feedback, decision):
                return None
        return decision

    def _verification_active(self, state: TaskState) -> bool:
        return (
            state.config.completion_verification and getattr(self.model, "verify", None) is not None
        )

    def _plan_review_active(self, state: TaskState) -> bool:
        return (
            state.config.plan_review_enabled
            and getattr(self.model, "review_plans", None) is not None
        )

    def _goal_review_active(self, state: TaskState) -> bool:
        return (
            state.config.goal_review_enabled
            and getattr(self.model, "goal_reviews", None) is not None
        )

    def _stop_guard_active(self, state: TaskState) -> bool:
        succeeded = any(
            result.status == "ok" for attempt in state.attempts for result in attempt.results
        )
        if succeeded:
            return False
        if state.action_attempts >= state.config.max_action_attempts:
            return False
        return self._remaining(state) > self._reserve(state)

    async def _verify_completion(self, state: TaskState):
        remaining = self._remaining(state) - self._reserve(state)
        try:
            verdict = await self.model.verify(state, remaining)
        except ModelRequestError as exc:
            self.logger.log(
                "completion_verification",
                level="ERROR",
                verdict="unavailable",
                error_message=str(exc),
            )
            return None
        self.logger.log(
            "completion_verification",
            goal_satisfied=verdict.goal_satisfied,
            missing_predicates=verdict.missing_predicates,
            reason=verdict.reason,
        )
        return verdict

    def _budget_fallback(self, state: TaskState) -> FinalDecision | None:
        if (
            state.action_attempts >= state.config.max_action_attempts
            or state.action_attempts + len(state.pending_retry_actions)
            > state.config.max_action_attempts
        ):
            return self.stop(state, "action_budget_exhausted")
        if self._remaining(state) <= self._reserve(state):
            return self.stop(state, "episode_time_exhausted")
        return None

    def _reserve(self, state: TaskState) -> float:
        # Plan mode synthesizes its final responses: no model request must fit
        # in the reserve. Reactive mode writes its final response through the
        # model, so it keeps the full reserve.
        if (
            state.config.planning_enabled
            and not state.reactive_mode
            and self._verification_active(state)
        ):
            return min(state.config.final_response_reserve_seconds, 2.0)
        return state.config.final_response_reserve_seconds

    def _remaining(self, state: TaskState) -> float:
        elapsed = max(0.0, self.clock() - state.started_at_monotonic)
        return max(0.0, state.config.max_episode_seconds - elapsed)

    def _reject_decision(self, state: TaskState, feedback: str, decision: Decision) -> bool:
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
