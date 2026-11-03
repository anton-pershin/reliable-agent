"""Versioned JSON Lines interaction bridge and tool executor."""

from __future__ import annotations

import asyncio
import io
import json
import os
import select
import sys
import threading
import time
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
        self._pending_writes: set[threading.Event] = set()
        self._io_lock = threading.Lock()

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

    def has_pending_writes(self) -> bool:
        with self._io_lock:
            return any(not event.is_set() for event in self._pending_writes)

    async def execute_write(self, batch: ActionBatch) -> None:
        event = threading.Event()
        with self._io_lock:
            self._pending_writes.add(event)
        await _run_blocking(self.write_actions, batch, done_event=event)

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
            message = json.loads(line, parse_constant=_reject_json_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ProtocolError("Input is not valid JSON") from exc
        if not isinstance(message, dict):
            raise ProtocolError("Protocol message must be a JSON object")
        return message

    def _write(self, message: dict[str, Any]) -> None:
        try:
            encoded = json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n"
        except ValueError as exc:
            raise ProtocolError("Output contains a non-JSON numeric value") from exc
        if len(encoded.encode("utf-8")) > self.max_message_bytes:
            raise ProtocolError("Output message exceeds the configured byte limit")
        self.writer.write(encoded)
        self.writer.flush()


class JsonLinesToolExecutor:
    def __init__(self, transport: JsonLinesTransport) -> None:
        self.transport = transport

    async def execute(self, batch: ActionBatch) -> Observation:
        await self.transport.execute_write(batch)
        return await _run_blocking(self.transport.read_observation)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


async def _run_blocking(function, *args, done_event: threading.Event | None = None):
    """Run blocking stream I/O in a daemon thread so timeouts can yield control."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def run() -> None:
        try:
            result = function(*args)
        except Exception as exc:
            captured_error = exc

            def set_error(error=captured_error) -> None:
                if not future.cancelled():
                    future.set_exception(error)

            try:
                loop.call_soon_threadsafe(set_error)
            except RuntimeError:
                pass
        else:

            def set_result() -> None:
                if not future.cancelled():
                    future.set_result(result)

            try:
                loop.call_soon_threadsafe(set_result)
            except RuntimeError:
                pass
        finally:
            if done_event is not None:
                done_event.set()

    threading.Thread(target=run, daemon=True).start()
    return await future


async def write_final_with_deadline(
    transport: JsonLinesTransport,
    decision: FinalDecision,
    deadline: float,
) -> bool:
    """Deliver final atomically, or emit nothing when safe delivery is unavailable."""
    if transport.has_pending_writes():
        return False
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    message = {
        "protocol_version": 1,
        "type": "final",
        **decision.to_response().model_dump(),
    }
    try:
        encoded = (json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except ValueError as exc:
        raise ProtocolError("Final response contains a non-JSON numeric value") from exc
    if isinstance(transport.writer, io.StringIO):
        transport.writer.write(encoded.decode("utf-8"))
        transport.writer.flush()
        return True
    try:
        descriptor = transport.writer.fileno()
    except (AttributeError, OSError):
        return False
    atomic_limit = getattr(os, "PIPE_BUF", 4096)
    if len(encoded) > atomic_limit:
        return False
    os.set_blocking(descriptor, False)
    _, writable, _ = select.select([], [descriptor], [], remaining)
    if not writable:
        return False
    written = os.write(descriptor, encoded)
    return written == len(encoded)
