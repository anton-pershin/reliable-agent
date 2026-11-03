"""Run one reliable-agent episode over JSON Lines."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence

import pydantic_ai

from .config import config_from_overrides
from .engine import DecisionEngine
from .errors import ProtocolError
from .model import PydanticAIModelClient
from .observability import EventLogger
from .protocol import JsonLinesToolExecutor, JsonLinesTransport
from .runner import TaskRunner


async def run_json_episode(config, transport: JsonLinesTransport) -> None:
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
    transport.write_final(decision)


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
                    "error_message": str(exc),
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
                    "error_message": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
