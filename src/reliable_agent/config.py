"""Configuration overrides for the process and Python APIs."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from .contracts import AgentConfig


class ConfigurationError(ValueError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one reliable-agent JSON Lines episode")
    parser.add_argument("--model", default=os.environ.get("RELIABLE_AGENT_MODEL"))
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--prompt-version")
    parser.add_argument("--tool-binding", action="append", default=[], metavar="NAME=BINDING")
    parser.add_argument("--max-protocol-bytes", type=int)
    parser.add_argument("--sensitive-value", action="append", default=[])
    parser.add_argument("--max-actions", dest="max_action_attempts", type=int)
    parser.add_argument("--episode-seconds", dest="max_episode_seconds", type=float)
    parser.add_argument("--model-timeout", dest="model_timeout_seconds", type=float)
    parser.add_argument("--transient-retries", dest="max_transient_retries", type=int)
    parser.add_argument("--decision-retries", dest="max_decision_retries", type=int)
    parser.add_argument("--decision-rejections", dest="max_decision_rejections", type=int)
    parser.add_argument("--max-context-items", type=int)
    parser.add_argument(
        "--final-response-reserve", dest="final_response_reserve_seconds", type=float
    )
    parser.add_argument("--max-concurrency", type=int)
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "ERROR"])
    parser.add_argument("--seed", dest="random_seed", type=int)
    return parser


def config_from_overrides(arguments: Sequence[str] | None = None) -> AgentConfig:
    namespace = build_parser().parse_args(arguments)
    values = vars(namespace)
    model = values.pop("model")
    binding_values = values.pop("tool_binding")
    sensitive_values = values.pop("sensitive_value")
    bindings = {}
    for value in binding_values:
        name, separator, binding = value.partition("=")
        if not separator or not name or not binding:
            raise ConfigurationError("Tool bindings must use NAME=BINDING")
        bindings[name] = binding
    overrides = {key: value for key, value in values.items() if value is not None}
    config = AgentConfig(
        model=model,
        tool_bindings=bindings,
        sensitive_values=sensitive_values,
        **overrides,
    )
    validate_config(config)
    return config


def validate_config(config: AgentConfig) -> None:
    if not config.model:
        raise ConfigurationError(
            "Model is required. Use --model, RELIABLE_AGENT_MODEL, or AgentConfig(model=...)."
        )
    if config.final_response_reserve_seconds >= config.max_episode_seconds:
        raise ConfigurationError("Final-response reserve must be smaller than the episode budget")
