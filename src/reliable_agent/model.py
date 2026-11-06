"""Pydantic AI model access and public prompt construction."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from pydantic import TypeAdapter
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.exceptions import ModelRequestRejectedError
from pydantic_ai.messages import RetryFeedbackPart, RetryPromptPart, ToolReturnPart
from pydantic_ai.models import Model

from .config import validate_config
from .contracts import (
    Decision,
    ModelMetadata,
    PlanCandidate,
    TaskState,
    VerificationResult,
)
from .errors import ModelRequestError
from .observability import EventLogger
from .planning import derive_sub_seed

_BASELINE_INSTRUCTIONS = """You solve tasks through public observations and tool results.
Choose either a nonempty batch of actions or a final response. Use only tools described in the task.
Before each action, check its declared preconditions against the latest public state and choose actions that can be valid.
Do not assume an action succeeded when its result is missing, failed, rejected, or uncertain.
Before declaring completion, compare every goal predicate with the latest public state. If any goal predicate is missing or inconsistent, continue acting or stop with completed=false and likely_incorrect=true.
Declare completion only when the public evidence establishes that the task objective is satisfied.
For every final response, give a concise answer, calibrated confidence, a strict likely_incorrect
boolean, and a short evidence-based reason. Set likely_incorrect=true when the answer is uncertain,
incomplete, or based on failed or missing evidence. Never ask for private scores or reference plans.
"""
_PLAN_INSTRUCTIONS = """You plan tasks through public observations and tool results.
Return one complete plan: an ordered list of actions that satisfies the task objective
from the current public state. Use only the tools described in the task and give every
action the arguments its schema requires. Before each planned action, check its declared
preconditions against the state that the earlier planned actions produce. Every action
must be valid at the moment it runs in the order of the plan. Do not include actions
that the objective does not need. Do not declare completion inside a plan.
Predicate argument order matters: a goal predicate holds only with its exact arguments
in their exact order. For each goal predicate with several arguments, choose the actions
whose effects produce exactly that argument order, and check the direction again before
you return the plan.
"""
_VERIFY_INSTRUCTIONS = """You verify whether public evidence satisfies the task goal.
Extract every goal predicate from the task input. For each goal predicate, search the
latest observation for the exact same text: the same predicate name and the same
arguments in the same order. A goal predicate (pred x y) matches only a state line with
the same name and the same arguments in the same order; (pred y x) is a different
predicate. List in missing_predicates every goal predicate that has no exact match in
the latest observation. When latest_observation is null, compare the goal with the
initial state in the task input instead. Set goal_satisfied=true only when
missing_predicates is empty. Use only public task information and observations.
"""
_DECISION_ADAPTER = TypeAdapter(Decision)
_PLAN_ADAPTER = TypeAdapter(PlanCandidate)
_VERIFICATION_ADAPTER = TypeAdapter(VerificationResult)


class DecisionModel(Protocol):
    async def decide(self, state: TaskState, remaining_seconds: float) -> Decision:
        pass

    async def plan(
        self, state: TaskState, remaining_seconds: float
    ) -> list[tuple[int, PlanCandidate]]:
        pass

    async def verify(self, state: TaskState, remaining_seconds: float) -> VerificationResult:
        pass


class PydanticAIModelClient:
    def __init__(self, logger: EventLogger, model: Model | str | None = None) -> None:
        self.logger = logger
        self.config = logger.config
        self.model = model or self.config.model
        validate_config(self.config)

    async def decide(self, state: TaskState, remaining_seconds: float) -> Decision:
        return await self._structured(
            output_type=Decision,
            adapter=_DECISION_ADAPTER,
            instructions=_BASELINE_INSTRUCTIONS,
            purpose="decision",
            format_hint="Return ActionDecision or FinalDecision only",
            state=state,
            remaining_seconds=remaining_seconds,
            operation_id=self._operation_id(state),
            seed=None,
        )

    async def plan(
        self, state: TaskState, remaining_seconds: float
    ) -> list[tuple[int, PlanCandidate]]:
        count = self.config.plan_samples

        async def sample(index: int) -> tuple[int, PlanCandidate]:
            seed = derive_sub_seed(self.config.random_seed, index)
            candidate = await self._structured(
                output_type=PlanCandidate,
                adapter=_PLAN_ADAPTER,
                instructions=_PLAN_INSTRUCTIONS,
                purpose="plan",
                format_hint="Return PlanCandidate only",
                state=state,
                remaining_seconds=remaining_seconds,
                operation_id=f"plan-{state.plan_rounds}-sample-{index + 1}",
                seed=seed,
            )
            return index, candidate

        results = await asyncio.gather(
            *(sample(index) for index in range(count)), return_exceptions=True
        )
        candidates = []
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.log(
                    "plan_sample_error",
                    level="ERROR",
                    plan_round=state.plan_rounds,
                    sample_index=index,
                    error_type=type(result).__name__,
                    error_message=str(result),
                )
            else:
                candidates.append(result)
        if not candidates:
            raise ModelRequestError(f"All {count} plan samples failed")
        return candidates

    async def verify(self, state: TaskState, remaining_seconds: float) -> VerificationResult:
        return await self._structured(
            output_type=VerificationResult,
            adapter=_VERIFICATION_ADAPTER,
            instructions=_VERIFY_INSTRUCTIONS,
            purpose="verification",
            format_hint="Return VerificationResult only",
            state=state,
            remaining_seconds=remaining_seconds,
            operation_id=self._operation_id(state, prefix="verify"),
            seed=None,
            prompt=self._verification_prompt(state),
        )

    async def _structured(
        self,
        *,
        output_type: Any,
        adapter: TypeAdapter,
        instructions: str,
        purpose: str,
        format_hint: str,
        state: TaskState,
        remaining_seconds: float,
        operation_id: str,
        seed: int | None,
        prompt: str | None = None,
    ) -> Any:
        if self.config.output_mode == "text":
            return await self._text_output(
                adapter=adapter,
                instructions=instructions,
                purpose=purpose,
                format_hint=format_hint,
                state=state,
                remaining_seconds=remaining_seconds,
                operation_id=operation_id,
                seed=seed,
                prompt=prompt,
            )
        try:
            return await self._tool_output(
                output_type=output_type,
                instructions=instructions,
                purpose=purpose,
                format_hint=format_hint,
                state=state,
                remaining_seconds=remaining_seconds,
                operation_id=operation_id,
                seed=seed,
                prompt=prompt,
            )
        except ModelRequestRejectedError as exc:
            if self.config.output_mode != "auto":
                raise ModelRequestError(f"Tool output was rejected: {exc}") from exc
            self.logger.log(
                "text_fallback",
                purpose=purpose,
                reason="Provider rejected the tool-output contract",
                error_type=type(exc).__name__,
            )
            return await self._text_output(
                adapter=adapter,
                instructions=instructions,
                purpose=purpose,
                format_hint=format_hint,
                state=state,
                remaining_seconds=remaining_seconds,
                operation_id=operation_id,
                seed=seed,
                prompt=prompt,
            )

    async def _tool_output(
        self,
        *,
        output_type: Any,
        instructions: str,
        purpose: str,
        format_hint: str,
        state: TaskState,
        remaining_seconds: float,
        operation_id: str,
        seed: int | None,
        prompt: str | None = None,
    ) -> Any:
        prompt = prompt if prompt is not None else self._prompt(state, format_hint)
        self.logger.log(
            "model_request",
            operation_id=operation_id,
            purpose=purpose,
            output_mode="tool",
            requested_model=self.config.model,
            prompt=prompt,
            generation_settings=self._generation_settings(seed),
        )
        try:
            agent = Agent(
                self.model,
                output_type=output_type,
                instructions=instructions,
                model_settings=self._model_settings(seed=seed),
                retries=self.config.max_decision_retries,
            )
            result = await agent.run(
                prompt,
                timeout=min(self.config.model_timeout_seconds, remaining_seconds),
            )
        except ModelRequestRejectedError:
            raise
        except Exception as exc:
            self._log_model_error(operation_id, exc)
            raise ModelRequestError(f"Model request failed: {type(exc).__name__}: {exc}") from exc
        self._log_repairs(result, operation_id)
        self._log_result(result, operation_id, "tool", purpose)
        return result.output

    async def _text_output(
        self,
        *,
        adapter: TypeAdapter,
        instructions: str,
        purpose: str,
        format_hint: str,
        state: TaskState,
        remaining_seconds: float,
        operation_id: str,
        seed: int | None,
        prompt: str | None = None,
    ) -> Any:
        base_prompt = (prompt if prompt is not None else self._prompt(state, format_hint)) + (
            "\nReturn only one JSON object matching this schema:\n"
        )
        schema = json.dumps(adapter.json_schema(), ensure_ascii=False)
        feedback = ""
        for attempt in range(self.config.max_decision_retries + 1):
            prompt = base_prompt + schema + feedback
            self.logger.log(
                "model_request",
                operation_id=f"{operation_id}-text-{attempt + 1}",
                purpose=purpose,
                output_mode="text",
                requested_model=self.config.model,
                prompt=prompt,
                generation_settings=self._generation_settings(seed),
            )
            try:
                agent = Agent(
                    self.model,
                    output_type=str,
                    instructions=instructions,
                    model_settings=self._model_settings(seed=seed, tool_choice="none"),
                    retries=0,
                )
                result = await agent.run(
                    prompt,
                    timeout=min(self.config.model_timeout_seconds, remaining_seconds),
                )
            except Exception as exc:
                self._log_model_error(operation_id, exc)
                raise ModelRequestError(
                    f"Text model request failed: {type(exc).__name__}: {exc}"
                ) from exc
            text = result.output
            try:
                output = adapter.validate_python(json.loads(self._strip_markdown_fence(text)))
            except (ValueError, TypeError, RecursionError) as exc:
                feedback = (
                    f"\nThe previous response was not valid for the {purpose} schema: {exc}\n"
                    "Return only corrected JSON without Markdown or commentary."
                )
                self.logger.log(
                    "model_repair",
                    operation_id=operation_id,
                    purpose=purpose,
                    repair_type="text_json_validation",
                    validation_feedback=str(exc),
                    attempt=attempt + 1,
                )
                continue
            self._log_result(result, operation_id, "text", purpose)
            return output
        raise ModelRequestError(f"Text output did not satisfy the {purpose} schema")

    def _prompt(
        self, state: TaskState, format_hint: str = "Return ActionDecision or FinalDecision only"
    ) -> str:
        history = state.public_history()
        if len(history) > self.config.max_context_items:
            omitted = len(history) - self.config.max_context_items
            history = history[-self.config.max_context_items :]
            self.logger.log(
                "context_truncated",
                omitted_attempts=omitted,
                retained_attempts=len(history),
            )
        return json.dumps(
            {
                "task": state.task.model_dump(),
                "action_attempts": state.action_attempts,
                "remaining_action_attempts": max(
                    0, self.config.max_action_attempts - state.action_attempts
                ),
                "history": history,
                "validation_feedback": state.validation_feedback,
                "prompt_version": self.config.prompt_version,
                "format": format_hint,
            },
            ensure_ascii=False,
            default=str,
        )

    def _verification_prompt(self, state: TaskState) -> str:
        latest_results = None
        if state.attempts:
            latest_results = [result.model_dump() for result in state.attempts[-1].results]
        return json.dumps(
            {
                "task": {
                    "id": state.task.id,
                    "instructions": state.task.instructions,
                    "input": state.task.input,
                },
                "latest_observation": latest_results,
                "format": "Return VerificationResult only",
            },
            ensure_ascii=False,
            default=str,
        )

    def _log_result(self, result, operation_id: str, output_mode: str, purpose: str) -> None:
        response = result.response
        reported_model = getattr(response, "model_id", None) or getattr(
            response, "model_name", None
        )
        provider = getattr(response, "provider_name", None)
        finish_reason = getattr(response, "finish_reason", None)
        unavailable = [
            name
            for name, value in (
                ("reported_model", reported_model),
                ("provider", provider),
                ("finish_reason", finish_reason),
            )
            if value is None
        ]
        metadata = ModelMetadata(
            requested_model=self.config.model or "",
            reported_model=reported_model,
            provider=provider,
            usage=self._usage(result.usage),
            finish_reason=finish_reason,
            unavailable=unavailable,
        )
        output = result.output
        self.logger.log(
            "model_response",
            operation_id=operation_id,
            purpose=purpose,
            output_mode=output_mode,
            metadata=metadata.model_dump(),
            public_output=output.model_dump() if hasattr(output, "model_dump") else output,
            private_reasoning="not-retained",
        )

    def _log_repairs(self, result, operation_id: str) -> None:
        for message in result.new_messages():
            for part in message.parts:
                if isinstance(part, (RetryPromptPart, RetryFeedbackPart)) or (
                    isinstance(part, ToolReturnPart) and part.outcome == "retried"
                ):
                    self.logger.log(
                        "model_repair",
                        operation_id=operation_id,
                        repair_type=type(part).__name__,
                        validation_feedback=part.content,
                        retry_details=str(getattr(part, "retry", None)),
                    )

    def _log_model_error(self, operation_id: str, exc: Exception) -> None:
        self.logger.log(
            "model_error",
            level="ERROR",
            operation_id=operation_id,
            requested_model=self.config.model,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    def _model_settings(self, seed: int | None = None, **overrides) -> ModelSettings:
        values = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "seed": self.config.random_seed if seed is None else seed,
            **overrides,
        }
        return ModelSettings(**values)

    def _generation_settings(self, seed: int | None = None) -> dict[str, Any]:
        return {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_output_tokens,
            "random_seed": self.config.random_seed if seed is None else seed,
            "output_mode": self.config.output_mode,
        }

    def _operation_id(self, state: TaskState, prefix: str = "model") -> str:
        return f"{prefix}-{len(state.attempts) + len(state.validation_feedback) + 1}"

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        stripped = text.strip()
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _usage(usage: Any) -> dict[str, int]:
        values = usage.model_dump() if hasattr(usage, "model_dump") else vars(usage)
        return {key: value for key, value in values.items() if isinstance(value, int)}
