"""Pydantic AI model access and public prompt construction."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models import Model

from .config import validate_config
from .contracts import Decision, ModelMetadata, TaskState
from .errors import ModelRequestError
from .observability import EventLogger

_BASELINE_INSTRUCTIONS = """You solve tasks through public observations and tool results.
Choose either a nonempty batch of actions or a final response. Use only tools described in the task.
Do not assume an action succeeded when its result is missing, failed, rejected, or uncertain.
Declare completion only when the public evidence establishes that the task objective is satisfied.
For every final response, give a concise answer, calibrated confidence, a strict likely_incorrect
boolean, and a short evidence-based reason. Set likely_incorrect=true when the answer is uncertain,
incomplete, or based on failed or missing evidence. Never ask for private scores or reference plans.
"""


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
        prompt = self._prompt(state)
        operation_id = f"model-{len(state.attempts) + len(state.validation_feedback) + 1}"
        self.logger.log(
            "model_request",
            operation_id=operation_id,
            requested_model=self.config.model,
            prompt=prompt,
            generation_settings={
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_output_tokens,
                "random_seed": self.config.random_seed,
            },
        )
        try:
            agent = Agent(
                self.model,
                output_type=Decision,
                instructions=_BASELINE_INSTRUCTIONS,
                model_settings=ModelSettings(
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_output_tokens,
                ),
                retries=self.config.max_decision_retries,
            )
            result = await agent.run(
                prompt,
                timeout=min(self.config.model_timeout_seconds, remaining_seconds),
            )
        except Exception as exc:
            self.logger.log(
                "model_error",
                level="ERROR",
                operation_id=operation_id,
                requested_model=self.config.model,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise ModelRequestError(f"Model request failed: {type(exc).__name__}: {exc}") from exc
        response = result.response
        usage = self._usage(result.usage)
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
            usage=usage,
            finish_reason=finish_reason,
            unavailable=unavailable,
        )
        self.logger.log(
            "model_response",
            operation_id=operation_id,
            metadata=metadata.model_dump(),
            public_output=result.output.model_dump(),
            private_reasoning="not-retained",
        )
        return result.output

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
        return _json_dumps(
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
            }
        )

    @staticmethod
    def _usage(usage: Any) -> dict[str, int]:
        values = usage.model_dump() if hasattr(usage, "model_dump") else vars(usage)
        return {key: value for key, value in values.items() if isinstance(value, int)}


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
