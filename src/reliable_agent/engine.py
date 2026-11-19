"""Stateful, benchmark-independent decision policy."""

from __future__ import annotations

import json
import time

from jsonschema import ValidationError, validators

from .contracts import (
    ActionAttempt,
    ActionDecision,
    ActionRequest,
    Decision,
    FinalDecision,
    PendingRetry,
    PlanCandidate,
    Task,
    TaskState,
    VerificationResult,
)
from .errors import ModelRequestError
from .goal_evidence import (
    formal_goal_verdict,
    formal_initial_state,
    formal_state_predicates,
)
from .model import DecisionModel
from .observability import EventLogger
from .planning import plan_key, vote_plans
from .transition_learning import (
    formal_transition_key,
    iter_public_actions,
    learn_action_rule,
    predict_action_state,
    search_learned_plan,
)


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
            formal_completion = self._formal_completion(state)
            if formal_completion is not None:
                return formal_completion

            if state.completion_check_pending:
                outcome = await self._check_intermediate_completion(state)
                if isinstance(outcome, FinalDecision):
                    return outcome
                continue

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
        observation_key = self._public_observation_key(state)
        formal_before = self._current_formal_state(state)
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
        self._record_observed_transition(state, observation_key, attempt)
        self._learn_observed_transition(state, formal_before, attempt)

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
            return self._verified_completion(state, verdict)
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

    async def _check_intermediate_completion(
        self, state: TaskState
    ) -> FinalDecision | bool:
        """Stop a non-reaching full plan early if its state already satisfies the goal."""
        verdict = await self._verify_completion(state)
        state.completion_check_pending = False
        if verdict is not None and verdict.goal_satisfied:
            return self._verified_completion(state, verdict)
        self.logger.log(
            "intermediate_completion_check",
            verdict="unavailable" if verdict is None else "not_satisfied",
            remaining_plan_actions=len(state.plan_actions),
            plan_broken=state.plan_broken,
        )
        return False

    def _verified_completion(
        self, state: TaskState, verdict: VerificationResult
    ) -> FinalDecision:
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

    @staticmethod
    def _mark_plan_failed(state: TaskState) -> None:
        if state.active_plan_key and state.active_plan_key not in state.failed_plan_keys:
            state.failed_plan_keys.append(state.active_plan_key)

    async def _plan_round(self, state: TaskState) -> str | FinalDecision | None:
        round_limit = 1 + state.config.max_replans
        if state.config.plan_execution_horizon or state.config.plan_horizon:
            # Ordinary prefix progress must not hit the recovery-oriented
            # re-planning limit before the action budget. Each prefix emits at
            # least one action, so an action-budget-sized ceiling is sufficient
            # even when failure rounds and transient retries consume attempts.
            round_limit = max(round_limit, 1 + state.config.max_action_attempts)
        if state.plan_rounds >= round_limit:
            return self.stop(
                state,
                "replanning_limit_reached",
                f"Re-planning limit reached after {state.plan_rounds} plan rounds.",
            )
        state.plan_rounds += 1
        cause = state.replan_cause or "initial"
        self.logger.log("plan_round", plan_round=state.plan_rounds, cause=cause)
        learned_actions, visited = self._learned_plan(state)
        if learned_actions is not None:
            candidate = PlanCandidate(actions=learned_actions, reaches_goal=True)
            errors = (
                self._validation_errors(state, ActionDecision(actions=learned_actions))
                if learned_actions
                else []
            )
            if not errors:
                state.plan_actions = list(learned_actions)
                state.completion_check_pending = False
                state.plan_broken = False
                state.replan_cause = None
                state.active_plan_key = plan_key(candidate)
                state.active_plan_reaches_goal = True
                self.logger.log(
                    "learned_plan",
                    plan_round=state.plan_rounds,
                    actions=[action.model_dump() for action in learned_actions],
                    learned_actions=sorted(state.learned_action_rules),
                    visited_states=visited,
                )
                self.logger.log(
                    "plan_selected",
                    plan_round=state.plan_rounds,
                    reaches_goal=True,
                    actions=[action.model_dump() for action in learned_actions],
                    selection_source="learned_public_transitions",
                )
                return "planned"
            self.logger.log(
                "learned_plan_invalid",
                level="ERROR",
                plan_round=state.plan_rounds,
                errors=errors,
            )
        elif visited:
            self.logger.log(
                "learned_plan_unavailable",
                plan_round=state.plan_rounds,
                visited_states=visited,
                learned_actions=sorted(state.learned_action_rules),
            )
        if (
            state.config.transition_exploration_enabled
            and state.config.transition_learning_enabled
            and state.config.transition_tabu_enabled
            and state.replan_cause == "action_failure"
            and not (state.config.plan_execution_horizon or state.config.plan_horizon)
        ):
            exploration = self._exploration_action(state)
            if exploration is not None:
                candidate = PlanCandidate(actions=[exploration], reaches_goal=False)
                state.plan_actions = [exploration]
                state.completion_check_pending = False
                state.plan_broken = False
                state.replan_cause = None
                state.active_plan_key = plan_key(candidate)
                state.active_plan_reaches_goal = False
                self.logger.log(
                    "transition_exploration",
                    plan_round=state.plan_rounds,
                    action=exploration.model_dump(),
                    learned_actions=sorted(state.learned_action_rules),
                )
                self.logger.log(
                    "plan_selected",
                    plan_round=state.plan_rounds,
                    reaches_goal=False,
                    actions=[exploration.model_dump()],
                    selection_source="public_transition_exploration",
                )
                return "planned"
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
        formal_verdict = self._formal_goal_verdict(state)
        if formal_verdict is not None and not formal_verdict.goal_satisfied:
            actionable = [(index, candidate) for index, candidate in valid if candidate.actions]
            if actionable and len(actionable) < len(valid):
                self.logger.log(
                    "formal_empty_completion_suppressed",
                    plan_round=state.plan_rounds,
                    suppressed=len(valid) - len(actionable),
                    missing_predicates=formal_verdict.missing_predicates,
                )
                valid = actionable
        if not state.attempts:
            # Before any environment action has supplied evidence, an empty
            # completion claim is only a model assertion. Identical empty
            # claims otherwise form an artificial majority over diverse action
            # plans, causing verification/replanning loops without progress.
            # Keep them when they are the only valid candidates: an initially
            # satisfied objective can still be verified immediately.
            actionable = [(index, candidate) for index, candidate in valid if candidate.actions]
            if actionable:
                suppressed = len(valid) - len(actionable)
                if suppressed:
                    self.logger.log(
                        "empty_completion_suppressed",
                        plan_round=state.plan_rounds,
                        suppressed=suppressed,
                        actionable=len(actionable),
                    )
                valid = actionable
        if state.config.plan_execution_horizon > 0 or state.config.plan_horizon > 0:
            # An execution horizon is independent of the prompt horizon: full
            # plan samples can therefore retain their action diversity while
            # the engine votes on and executes only an agreed prefix. A prompt
            # horizon remains a fallback for backward compatibility.
            horizon = state.config.plan_execution_horizon or state.config.plan_horizon
            truncated = 0
            adjusted = []
            for index, candidate in valid:
                if len(candidate.actions) > horizon:
                    candidate = candidate.model_copy(
                        update={
                            "actions": candidate.actions[:horizon],
                            "reaches_goal": False,
                        }
                    )
                    truncated += 1
                adjusted.append((index, candidate))
            valid = adjusted
            self.logger.log(
                "plan_horizon_enforced",
                plan_round=state.plan_rounds,
                horizon=horizon,
                truncated=truncated,
            )
        if state.config.transition_tabu_enabled:
            tried = state.tried_transitions.get(self._public_observation_key(state), [])
            repeated = []
            novel = []
            for index, candidate in valid:
                if (
                    candidate.actions
                    and self._transition_action_key(candidate.actions[0]) in tried
                ):
                    repeated.append((index, candidate))
                else:
                    novel.append((index, candidate))
            if repeated:
                self.logger.log(
                    "transition_tabu",
                    plan_round=state.plan_rounds,
                    suppressed=len(repeated),
                    remaining=len(novel),
                    all_repeated=not novel,
                    actions=[candidate.actions[0].model_dump() for _, candidate in repeated],
                )
                if not novel:
                    descriptions = ", ".join(
                        candidate.actions[0].name
                        + "("
                        + json.dumps(
                            candidate.actions[0].arguments,
                            sort_keys=True,
                            ensure_ascii=False,
                        )
                        + ")"
                        for _, candidate in repeated
                    )
                    state.validation_feedback.append(
                        "Every candidate repeats an action already observed from the current "
                        f"public state: {descriptions}. Propose a different action or an empty "
                        "completion claim only when public evidence satisfies the objective."
                    )
                    state.plan_broken = True
                    state.replan_cause = "repeated_transition"
                    return None
                valid = novel
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
        completion_full_plan = bool(state.config.plan_vote_horizon) and not (
            state.config.plan_execution_horizon or state.config.plan_horizon
        )
        completion_horizon = 0 if completion_full_plan else state.config.plan_vote_horizon
        if self._goal_review_active(state):
            # Preserve completion verdicts for the whole normalized vote group.
            # Goal review checks only reaching candidates; dropping a
            # non-reaching member must not make the survivors look unanimous.
            group_reaching: dict[str, bool] = {}
            for _, candidate in fresh:
                key = plan_key(candidate, completion_horizon)
                group_reaching[key] = group_reaching.get(key, True) and candidate.reaches_goal
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
                    filtered = [
                        (index, candidate) for index, candidate in fresh if index in goal_ok
                    ]
                    fresh = [
                        (
                            index,
                            candidate
                            if group_reaching[plan_key(candidate, completion_horizon)]
                            else candidate.model_copy(update={"reaches_goal": False}),
                        )
                        for index, candidate in filtered
                    ]
        winner_index, winner, counts = vote_plans(
            fresh,
            horizon=state.config.plan_vote_horizon,
            completion_full_plan=completion_full_plan,
        )
        self.logger.log(
            "plan_vote",
            plan_round=state.plan_rounds,
            winner_sample=winner_index,
            vote_counts=counts,
            horizon=state.config.plan_execution_horizon or state.config.plan_horizon,
            vote_horizon=state.config.plan_vote_horizon,
        )
        winner = await self._review_selected_prefix(state, winner_index, winner)
        if winner is None:
            return None
        state.plan_actions = list(winner.actions)
        state.completion_check_pending = False
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

    async def _review_selected_prefix(
        self, state: TaskState, winner_index: int, winner: PlanCandidate
    ) -> PlanCandidate | None:
        """Apply one short-prefix validity review after the vote."""
        if not self._selected_plan_review_active(state) or not winner.actions:
            return winner
        remaining = self._remaining(state) - self._reserve(state)
        try:
            review = await self.model.review_selected_plan(state, winner, remaining)
        except ModelRequestError as exc:
            self.logger.log(
                "selected_plan_review_error",
                level="ERROR",
                plan_round=state.plan_rounds,
                winner_sample=winner_index,
                error_message=str(exc),
            )
            return winner
        self.logger.log(
            "selected_plan_review",
            plan_round=state.plan_rounds,
            winner_sample=winner_index,
            valid=review.valid,
            first_invalid_action_index=review.first_invalid_action_index,
            reason=review.reason,
        )
        k = review.first_invalid_action_index
        if review.valid or k is None or k >= len(winner.actions):
            return winner
        if k == 0:
            key = plan_key(winner)
            if key not in state.failed_plan_keys:
                state.failed_plan_keys.append(key)
            feedback = (
                "The selected plan prefix failed validity review at action 0: "
                f"{review.reason} Plan again from the current state."
            )
            state.validation_feedback.append(feedback)
            state.plan_broken = True
            state.replan_cause = "selected_plan_review_rejected"
            self.logger.log(
                "selected_plan_review_rejected",
                level="ERROR",
                plan_round=state.plan_rounds,
                winner_sample=winner_index,
                first_invalid_action_index=0,
                reason=review.reason,
            )
            return None
        winner = winner.model_copy(
            update={"actions": winner.actions[:k], "reaches_goal": False}
        )
        self.logger.log(
            "selected_plan_review_truncated",
            plan_round=state.plan_rounds,
            winner_sample=winner_index,
            first_invalid_action_index=k,
            retained_actions=k,
        )
        return winner

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

    def _current_formal_state(self, state: TaskState) -> frozenset[str] | None:
        if not state.config.transition_learning_enabled:
            return None
        if not state.attempts:
            return formal_initial_state(state.task.input)
        latest = state.attempts[-1].results
        if not latest or not all(
            isinstance(result.observation.get("state"), list) for result in latest
        ):
            return None
        return formal_state_predicates(latest[-1].observation["state"])

    def _learn_observed_transition(
        self,
        state: TaskState,
        before: frozenset[str] | None,
        attempt: ActionAttempt,
    ) -> None:
        if before is None or len(attempt.actions) != 1 or len(attempt.results) != 1:
            return
        action = attempt.actions[0]
        result = attempt.results[0]
        transition_key = formal_transition_key(before, action)
        if result.status != "ok":
            if result.error is not None and result.error.type == "transient_failure":
                return
            if transition_key not in state.failed_formal_transitions:
                state.failed_formal_transitions.append(transition_key)
            self.logger.log(
                "failed_formal_transition",
                plan_round=state.plan_rounds,
                action=action.model_dump(),
            )
            return
        if transition_key in state.failed_formal_transitions:
            state.failed_formal_transitions.remove(transition_key)
            self.logger.log(
                "formal_transition_recovered",
                plan_round=state.plan_rounds,
                action=action.model_dump(),
            )
        if action.name in state.rejected_learned_actions:
            return
        after = formal_state_predicates(attempt.results[0].observation.get("state"))
        if after is None:
            return
        existing = state.learned_action_rules.get(action.name)
        if existing is not None:
            predicted = predict_action_state(existing, action, before)
            if predicted == after:
                self.logger.log(
                    "transition_rule_confirmed",
                    plan_round=state.plan_rounds,
                    action=action.model_dump(),
                )
                return
            # A prediction mismatch, including an unexpected no-op, invalidates
            # the existing rule and any remaining tail based on it.
            state.learned_action_rules.pop(action.name, None)
            state.rejected_learned_actions.append(action.name)
            state.plan_actions = []
            state.completion_check_pending = False
            state.plan_broken = True
            state.replan_cause = "transition_rule_conflict"
            self.logger.log(
                "transition_rule_conflict",
                level="ERROR",
                plan_round=state.plan_rounds,
                action=action.model_dump(),
                previous_rule=existing.model_dump(),
                predicted_state=sorted(predicted) if predicted is not None else None,
                observed_state=sorted(after),
            )
            return
        rule = learn_action_rule(action, before, after)
        if rule is None:
            return
        state.learned_action_rules[action.name] = rule
        self.logger.log(
            "transition_rule_learned",
            plan_round=state.plan_rounds,
            action=action.model_dump(),
            rule=rule.model_dump(),
            learned_actions=len(state.learned_action_rules),
        )

    def _learned_plan(
        self, state: TaskState
    ) -> tuple[list[ActionRequest] | None, int]:
        current = self._current_formal_state(state)
        if current is None or state.config.plan_execution_horizon or state.config.plan_horizon:
            return None, 0
        return search_learned_plan(
            state.task,
            current,
            state.learned_action_rules,
            max_states=state.config.learned_search_max_states,
            max_actions=max(0, state.config.max_action_attempts - state.action_attempts),
            failed_transitions=frozenset(state.failed_formal_transitions),
            deadline=self.clock() + max(0.0, self._remaining(state) - self._reserve(state)),
            clock=self.clock,
        )

    def _exploration_action(self, state: TaskState) -> ActionRequest | None:
        current = self._current_formal_state(state)
        if current is None:
            return None
        tried = set(state.tried_transitions.get(self._public_observation_key(state), []))
        failed = frozenset(state.failed_formal_transitions)
        deadline = self.clock() + max(0.0, self._remaining(state) - self._reserve(state))
        for index, action in enumerate(iter_public_actions(state.task), start=1):
            if index > state.config.exploration_max_candidates:
                self.logger.log(
                    "transition_exploration_exhausted",
                    reason="candidate_limit",
                    checked=index - 1,
                )
                return None
            if index % 64 == 0 and self.clock() >= deadline:
                self.logger.log(
                    "transition_exploration_exhausted",
                    level="ERROR",
                    reason="deadline",
                    checked=index,
                )
                return None
            if (
                action.name in state.learned_action_rules
                or action.name in state.rejected_learned_actions
            ):
                continue
            if self._transition_action_key(action) in tried:
                continue
            if formal_transition_key(current, action) in failed:
                continue
            if self._validation_errors(state, ActionDecision(actions=[action])):
                continue
            return action
        return None

    def _record_observed_transition(
        self, state: TaskState, observation_key: str, attempt: ActionAttempt
    ) -> None:
        """Remember one public state/action pair for optional cycle suppression."""
        if (
            not state.config.transition_tabu_enabled
            or len(attempt.actions) != 1
            or len(attempt.results) != 1
        ):
            return
        result = attempt.results[0]
        if result.error is not None and result.error.type == "transient_failure":
            # Transient failures are retried independently; they are not evidence
            # that the same transition should be avoided later.
            return
        action = attempt.actions[0]
        action_key = self._transition_action_key(action)
        tried = state.tried_transitions.setdefault(observation_key, [])
        if action_key not in tried:
            tried.append(action_key)
        self.logger.log(
            "observed_transition",
            action=action.model_dump(),
            status=result.status,
            known_transitions_from_state=len(tried),
        )

    @staticmethod
    def _transition_action_key(action: ActionRequest) -> str:
        """Use the same type-preserving JSON canonicalization as plan voting."""
        return plan_key(PlanCandidate(actions=[action]))

    @staticmethod
    def _public_observation_key(state: TaskState) -> str:
        """Canonicalize the latest public state without interpreting its domain."""
        if not state.attempts:
            payload = {"initial_input": state.task.input}
        else:
            latest = state.attempts[-1]
            observations = [result.observation for result in latest.results]
            if observations and all("state" in observation for observation in observations):
                # Observation metadata such as the last action name is not part
                # of the public state and would disguise an otherwise exact cycle.
                payload = {"states": [observation["state"] for observation in observations]}
            elif observations and all(observations):
                payload = {"observations": observations}
            else:
                # With no public observation, different attempts cannot safely
                # be identified as the same state.
                payload = {"unobserved_attempt": latest.call_id}
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

    def _update_plan(self, state: TaskState, attempt: ActionAttempt) -> None:
        if not state.plan_actions or len(attempt.actions) != 1:
            return
        if attempt.actions[0] != state.plan_actions[0]:
            return
        result = attempt.results[0] if attempt.results else None
        if result is not None and result.status == "ok":
            state.plan_actions = state.plan_actions[1:]
            if (
                state.config.intermediate_completion_verification_enabled
                and not state.active_plan_reaches_goal
                and not (state.config.plan_execution_horizon or state.config.plan_horizon)
                and self._verification_active(state)
            ):
                state.completion_check_pending = True
                self.logger.log(
                    "intermediate_completion_check_scheduled",
                    plan_round=state.plan_rounds,
                    remaining_plan_actions=len(state.plan_actions),
                )
            if not state.plan_actions:
                if state.active_plan_reaches_goal:
                    self.logger.log("plan_completed", plan_round=state.plan_rounds)
                else:
                    # Exhaustion requests re-planning. An enabled full-plan
                    # intermediate check can run first and accept a goal that
                    # was reached before the predicted tail.
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
        state.completion_check_pending = False
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

    def _formal_goal_verdict(self, state: TaskState) -> VerificationResult | None:
        if not state.config.formal_goal_checking_enabled or not state.attempts:
            return None
        latest = state.attempts[-1].results
        if not latest or not all(
            isinstance(result.observation.get("state"), list) for result in latest
        ):
            return None
        return formal_goal_verdict(
            state.task.input, latest[-1].observation["state"]
        )

    def _formal_completion(self, state: TaskState) -> FinalDecision | None:
        verdict = self._formal_goal_verdict(state)
        if verdict is None or not verdict.goal_satisfied:
            return None
        self.logger.log(
            "completion_verification",
            goal_satisfied=True,
            missing_predicates=[],
            reason=verdict.reason,
            verification_source="formal_public_state",
        )
        return self._verified_completion(state, verdict)

    def _verification_active(self, state: TaskState) -> bool:
        return (
            state.config.completion_verification and getattr(self.model, "verify", None) is not None
        )

    def _plan_review_active(self, state: TaskState) -> bool:
        return (
            state.config.plan_review_enabled
            and getattr(self.model, "review_plans", None) is not None
        )

    def _selected_plan_review_active(self, state: TaskState) -> bool:
        return (
            state.config.selected_plan_review_enabled
            and getattr(self.model, "review_selected_plan", None) is not None
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
        formal_verdict = self._formal_goal_verdict(state)
        if formal_verdict is not None:
            self.logger.log(
                "completion_verification",
                goal_satisfied=formal_verdict.goal_satisfied,
                missing_predicates=formal_verdict.missing_predicates,
                reason=formal_verdict.reason,
                verification_source="formal_public_state",
            )
            return formal_verdict
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
