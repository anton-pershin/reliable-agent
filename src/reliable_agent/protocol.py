"""Versioned JSON Lines interaction bridge and tool executor."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .contracts import ActionBatch, FinalDecision, Observation, Task
from .errors import ProtocolError


class JsonLinesTransport:
    def __init__(
        self,
        reader: TextIO | None = None,
        writer: TextIO | None = None,
        max_message_bytes: int = 1_000_000,
    ) -> None:
        self.reader = reader or sys.stdin
        self.writer = writer or sys.stdout
        self.max_message_bytes = max_message_bytes

    def read_task(self) -> tuple[str, Task]:
        message = self._read()
        self._validate_envelope(message, "task")
        episode_id = message.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise ProtocolError("Task message requires a nonempty episode_id")
        try:
            task = Task.model_validate(message.get("task"))
        except ValueError as exc:
            raise ProtocolError(f"Invalid task data: {exc}") from exc
        return episode_id, task

    def write_actions(self, batch: ActionBatch) -> None:
        self._write(
            {
                "protocol_version": 1,
                "type": "actions",
                "call_id": batch.call_id,
                "actions": [action.model_dump() for action in batch.actions],
            }
        )

    def read_observation(self) -> Observation:
        message = self._read()
        self._validate_envelope(message, "observation")
        try:
            return Observation.model_validate(
                {
                    "call_id": message.get("call_id"),
                    "results": message.get("results"),
                }
            )
        except ValueError as exc:
            raise ProtocolError(f"Invalid observation: {exc}") from exc

    def write_final(self, decision: FinalDecision) -> None:
        self._write(
            {
                "protocol_version": 1,
                "type": "final",
                **decision.to_response().model_dump(),
            }
        )

    def _validate_envelope(self, message: dict[str, Any], expected_type: str) -> None:
        version = message.get("protocol_version")
        if type(version) is not int or version != 1:
            raise ProtocolError("Message requires integer protocol_version 1")
        if message.get("type") != expected_type:
            raise ProtocolError(f"Expected message type {expected_type}")

    def _read(self) -> dict[str, Any]:
        line = self.reader.readline(self.max_message_bytes + 1)
        if not line:
            raise ProtocolError("No input message is available")
        if len(line.encode("utf-8")) > self.max_message_bytes:
            raise ProtocolError("Input message exceeds the configured byte limit")
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ProtocolError("Input is not valid JSON") from exc
        if not isinstance(message, dict):
            raise ProtocolError("Protocol message must be a JSON object")
        return message

    def _write(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False) + "\n"
        if len(encoded.encode("utf-8")) > self.max_message_bytes:
            raise ProtocolError("Output message exceeds the configured byte limit")
        self.writer.write(encoded)
        self.writer.flush()


class JsonLinesToolExecutor:
    def __init__(self, transport: JsonLinesTransport) -> None:
        self.transport = transport

    async def execute(self, batch: ActionBatch) -> Observation:
        self.transport.write_actions(batch)
        return self.transport.read_observation()
