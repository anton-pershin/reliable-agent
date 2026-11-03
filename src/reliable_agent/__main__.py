"""Run one reliable-agent episode over JSON Lines."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Sequence

import pydantic_ai

from .config import config_from_overrides
from .engine import DecisionEngine
from .errors import ProtocolError
from .model import PydanticAIModelClient
from .observability import EventLogger, configured_secrets, redact_text
from .protocol import JsonLinesToolExecutor, JsonLinesTransport, write_final_with_deadline
from .runner import TaskRunner


async def run_json_episode(config, transport: JsonLinesTransport) -> None:
    deadline = time.monotonic() + config.max_episode_seconds
    episode_id, task = transport.read_task()
    logger = EventLogger(episode_id, config)
    engine = DecisionEngine(PydanticAIModelClient(logger), logger)
    runner = TaskRunner(engine, JsonLinesToolExecutor(transport))
    try:
        decision = await runner.run(task)
    except Exception as exc:
        logger.log(
            "termination",
            level="ERROR",
            termination_reason="internal_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    try:
        delivered = await write_final_with_deadline(transport, decision, deadline)
    except TimeoutError:
        delivered = False
    if not delivered:
        logger.log(
            "final_delivery_skipped",
            level="ERROR",
            termination_reason="final_delivery_deadline_or_pending_io",
        )


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        config = config_from_overrides(arguments)
    except (ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(str(exc), file=sys.stderr)
        return 2
    pydantic_ai.BANNER_ENABLED = False
    transport = JsonLinesTransport(max_message_bytes=config.max_protocol_bytes)
    try:
        asyncio.run(run_json_episode(config, transport))
        return 0
    except (ProtocolError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "event": "protocol_error",
                    "level": "ERROR",
                    "error_type": type(exc).__name__,
                    "error_message": redact_text(str(exc), configured_secrets(config)),
                }
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "internal_error",
                    "level": "ERROR",
                    "error_type": type(exc).__name__,
                    "error_message": redact_text(str(exc), configured_secrets(config)),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
