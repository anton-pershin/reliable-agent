"""Structured, redacted JSON event logging to standard error."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any, TextIO

from . import __version__
from .contracts import AgentConfig

_SECRET_KEY = re.compile(
    r"(?:api[-_]?key|(?:access[-_]?|auth[-_]?)?token|password|secret|authorization)\b",
    re.I,
)
_SECRET_ASSIGNMENT = re.compile(
    r"((?:API[-_]?KEY|TOKEN|PASSWORD|SECRET|AUTHORIZATION)\s*[:=]\s*[\"']?)([^\"',\s}]+)",
    re.I,
)
_BEARER = re.compile(r"(Bearer\s+)[^\s]+", re.I)


def configured_secrets(config: AgentConfig) -> set[str]:
    return {
        value
        for value in (
            *config.sensitive_values,
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("ANTHROPIC_API_KEY", ""),
        )
        if value
    }


def redact_text(value: str, secrets: set[str]) -> str:
    redacted = _SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)
    redacted = _BEARER.sub(r"\1<redacted>", redacted)
    for secret in sorted(secrets, key=len, reverse=True):
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


class EventLogger:
    def __init__(
        self,
        episode_id: str,
        config: AgentConfig,
        stream: TextIO | None = None,
        clock=time.monotonic,
    ) -> None:
        self.episode_id = episode_id
        self.config = config
        self.stream = stream or sys.stderr
        self.clock = clock
        self.started = clock()
        self._sequence = 0
        self._lock = threading.Lock()
        self._secrets = configured_secrets(config)

    def log(self, event: str, **data: Any) -> None:
        level = data.pop("level", "INFO")
        if not self._enabled(level):
            return
        with self._lock:
            self._sequence += 1
            record = {
                "schema_version": 1,
                "event": event,
                "event_index": self._sequence,
                "episode_id": self.episode_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "elapsed_seconds": max(0.0, self.clock() - self.started),
                "level": level,
                **data,
            }
            safe = self._redact(record)
            self.stream.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")
            self.stream.flush()

    def log_configuration(self) -> None:
        dependencies = {}
        for package in ("reliable-agent", "pydantic", "pydantic-ai", "jsonschema"):
            try:
                dependencies[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                dependencies[package] = "not-installed"
        self.log(
            "configuration",
            config=self.config.public_dict(),
            implementation_version=__version__,
            dependency_versions=dependencies,
        )

    def _enabled(self, level: str) -> bool:
        ranks = {"DEBUG": 10, "INFO": 20, "ERROR": 40}
        return ranks[level] >= ranks[self.config.log_level]

    def _redact(self, value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                str(item_key): (
                    "<redacted>"
                    if _SECRET_KEY.search(str(item_key))
                    else self._redact(item_value, str(item_key))
                )
                for item_key, item_value in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact(item, key) for item in value]
        if isinstance(value, str):
            return redact_text(value, self._secrets)
        return value
