"""Reusable baseline agent with structured Pydantic AI decisions."""

__version__ = "0.1.0"

from .contracts import (
    ActionBatch,
    ActionDecision,
    ActionRequest,
    ActionResult,
    AgentConfig,
    FinalDecision,
    FinalResponse,
    Observation,
    Task,
    ToolDescription,
)
from .engine import DecisionEngine
from .model import PydanticAIModelClient
from .observability import EventLogger
from .runner import TaskRunner, run_concurrently

__all__ = [
    "ActionBatch",
    "ActionDecision",
    "ActionRequest",
    "ActionResult",
    "AgentConfig",
    "DecisionEngine",
    "EventLogger",
    "FinalDecision",
    "FinalResponse",
    "Observation",
    "PydanticAIModelClient",
    "Task",
    "TaskRunner",
    "ToolDescription",
    "run_concurrently",
]
