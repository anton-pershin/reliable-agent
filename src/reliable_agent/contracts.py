"""Typed public contracts and per-episode state."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AgentConfig(ContractModel):
    model: str | None = None
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=2000, ge=1)
    prompt_version: str = "baseline-v1"
    max_action_attempts: int = Field(default=45, ge=1, le=50)
    max_episode_seconds: float = Field(default=270, gt=0, le=300)
    model_timeout_seconds: float = Field(default=60, gt=0)
    max_transient_retries: int = Field(default=2, ge=0, le=10)
    max_decision_retries: int = Field(default=2, ge=0, le=10)
    max_decision_rejections: int = Field(default=2, ge=1, le=10)
    max_context_items: int = Field(default=40, ge=1, le=1000)
    final_response_reserve_seconds: float = Field(default=30, ge=0)
    max_concurrency: int = Field(default=4, ge=1, le=64)
    max_protocol_bytes: int = Field(default=1_000_000, ge=1024)
    log_level: Literal["DEBUG", "INFO", "ERROR"] = "INFO"
    random_seed: int = 0
    tool_bindings: dict[str, str] = Field(default_factory=dict)
    sensitive_values: list[str] = Field(default_factory=list, repr=False)

    def public_dict(self) -> dict[str, Any]:
        values = self.model_dump()
        values.pop("sensitive_values", None)
        return values


class ToolDescription(ContractModel):
    name: str
    description: str
    arguments_schema: dict[str, Any] = Field(default_factory=dict)


class Task(ContractModel):
    id: str
    instructions: str
    input: str
    tools: list[ToolDescription] = Field(default_factory=list)


class ActionRequest(ContractModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ActionBatch(ContractModel):
    call_id: str
    actions: list[ActionRequest] = Field(min_length=1)


class ActionError(ContractModel):
    type: str
    message: str


class ActionResult(ContractModel):
    status: Literal["ok", "error", "rejected"]
    observation: dict[str, Any] = Field(default_factory=dict)
    error: ActionError | None = None


class Observation(ContractModel):
    call_id: str
    results: list[ActionResult]


class FinalResponse(ContractModel):
    completed: bool
    answer: str
    confidence: float = Field(ge=0, le=1)
    likely_incorrect: bool
    reason: str


class ActionDecision(ContractModel):
    kind: Literal["actions"] = "actions"
    actions: list[ActionRequest] = Field(min_length=1)


class FinalDecision(ContractModel):
    kind: Literal["final"] = "final"
    completed: bool
    answer: str
    confidence: float = Field(ge=0, le=1)
    likely_incorrect: bool
    reason: str

    def to_response(self) -> FinalResponse:
        return FinalResponse(**self.model_dump(exclude={"kind"}))


Decision = Annotated[ActionDecision | FinalDecision, Field(discriminator="kind")]


class ActionAttempt(ContractModel):
    call_id: str
    actions: list[ActionRequest]
    results: list[ActionResult] = Field(default_factory=list)
    retry_number: int = 0


class ModelMetadata(ContractModel):
    requested_model: str
    reported_model: str | None = None
    provider: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str | None = None
    unavailable: list[str] = Field(default_factory=list)


class TaskState(ContractModel):
    episode_id: str
    task: Task
    config: AgentConfig
    started_at_monotonic: float
    attempts: list[ActionAttempt] = Field(default_factory=list)
    rejected_decisions: int = 0
    validation_feedback: list[str] = Field(default_factory=list)
    transient_retries: dict[str, int] = Field(default_factory=dict)
    pending_retry_actions: list[ActionRequest] = Field(default_factory=list)
    termination_reason: str | None = None

    @property
    def action_attempts(self) -> int:
        return sum(len(attempt.actions) for attempt in self.attempts)

    def public_history(self) -> list[dict[str, Any]]:
        return [
            {
                "call_id": attempt.call_id,
                "actions": [action.model_dump() for action in attempt.actions],
                "results": [result.model_dump() for result in attempt.results],
                "retry_number": attempt.retry_number,
            }
            for attempt in self.attempts
        ]
