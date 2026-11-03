"""Pydantic AI model access and public prompt construction."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import TypeAdapter
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.exceptions import ModelRequestRejectedError
from pydantic_ai.messages import RetryFeedbackPart, RetryPromptPart, ToolReturnPart
from pydantic_ai.models import Model

from .config import validate_config
from .contracts import Decision, ModelMetadata, TaskState
from .errors import ModelRequestError
from .observability import EventLogger

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
_DECISION_ADAPTER = TypeAdapter(Decision)


class DecisionModel(Protocol):
    async def decide(self, state: TaskState, remaining_seconds: float) -> Decision:
        pass


class PydanticAIModelClient:
    def __init__(self, logger: EventLogger, model: Model | str | None = None) -> None:
        self.logger = logger
        self.config = logger.config
        self.model = model or self.config.model
        validate_config(self.config)

    async def decide(self, state: TaskState, remaining_seconds: float) -> Decision:
        if self.config.output_mode == "text":
            return await self._decide_text(state, remaining_seconds)
        try:
            return await self._decide_tool(state, remaining_seconds)
        except ModelRequestRejectedError as exc:
            if self.config.output_mode != "auto":
                raise ModelRequestError(f"Tool output was rejected: {exc}") from exc
            self.logger.log(
                "text_fallback",
                reason="Provider rejected the tool-output contract",
                error_type=type(exc).__name__,
            )
            return await self._decide_text(state, remaining_seconds)

    async def _decide_tool(self, state: TaskState, remaining_seconds: float) -> Decision:
        prompt = self._prompt(state)
        operation_id = self._operation_id(state)
        self.logger.log(
            "model_request",
            operation_id=operation_id,
            output_mode="tool",
            requested_model=self.config.model,
            prompt=prompt,
            generation_settings=self._generation_settings(),
        )
        try:
            agent = Agent(
                self.model,
                output_type=Decision,
                instructions=_BASELINE_INSTRUCTIONS,
                model_settings=self._model_settings(),
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
        self._log_result(result, operation_id, "tool")
        return result.output

    async def _decide_text(self, state: TaskState, remaining_seconds: float) -> Decision:
        base_prompt = self._prompt(state) + "\nReturn only one JSON object matching this schema:\n"
        schema = json.dumps(_DECISION_ADAPTER.json_schema(), ensure_ascii=False)
        feedback = ""
        operation_id = self._operation_id(state)
        for attempt in range(self.config.max_decision_retries + 1):
            prompt = base_prompt + schema + feedback
            self.logger.log(
                "model_request",
                operation_id=f"{operation_id}-text-{attempt + 1}",
                output_mode="text",
                requested_model=self.config.model,
                prompt=prompt,
                generation_settings=self._generation_settings(),
            )
            try:
                agent = Agent(
                    self.model,
                    output_type=str,
                    instructions=_BASELINE_INSTRUCTIONS,
                    model_settings=self._model_settings(tool_choice="none"),
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
                decision = _DECISION_ADAPTER.validate_python(
                    json.loads(self._strip_markdown_fence(text))
                )
            except (ValueError, TypeError, RecursionError) as exc:
                feedback = (
                    f"\nThe previous response was not valid for the decision schema: {exc}\n"
                    "Return only corrected JSON without Markdown or commentary."
                )
                self.logger.log(
                    "model_repair",
                    operation_id=operation_id,
                    repair_type="text_json_validation",
                    validation_feedback=str(exc),
                    attempt=attempt + 1,
                )
                continue
            self._log_result(result, operation_id, "text")
            return decision
        raise ModelRequestError("Text output did not satisfy the decision schema")

    def _prompt(self, state: TaskState) -> str:
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
                "format": "Return ActionDecision or FinalDecision only",
            },
            ensure_ascii=False,
            default=str,
        )

    def _log_result(self, result, operation_id: str, output_mode: str) -> None:
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

    def _model_settings(self, **overrides) -> ModelSettings:
        values = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "seed": self.config.random_seed,
            **overrides,
        }
        return ModelSettings(**values)

    def _generation_settings(self) -> dict[str, Any]:
        return {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_output_tokens,
            "random_seed": self.config.random_seed,
            "output_mode": self.config.output_mode,
        }

    def _operation_id(self, state: TaskState) -> str:
        return f"model-{len(state.attempts) + len(state.validation_feedback) + 1}"

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
