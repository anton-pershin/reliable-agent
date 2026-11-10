from __future__ import annotations

import pytest
from conftest import config

from reliable_agent.config import ConfigurationError, config_from_overrides, validate_config
from reliable_agent.contracts import ActionBatch, FinalResponse


def test_defaults_and_public_configuration() -> None:
    agent_config = config(sensitive_values=["secret"])
    assert agent_config.max_action_attempts == 45
    assert agent_config.max_episode_seconds == 285
    assert agent_config.max_transient_retries == 2
    assert agent_config.plan_max_output_tokens == 0
    assert agent_config.sample_retries == 1
    assert "sensitive_values" not in agent_config.public_dict()
    validate_config(agent_config)


def test_sample_configuration_overrides_parse() -> None:
    agent_config = config_from_overrides(
        [
            "--model",
            "test",
            "--plan-max-output-tokens",
            "4000",
            "--sample-retries",
            "2",
            "--plan-spares",
            "2",
            "--no-plan-review",
        ]
    )
    assert agent_config.plan_max_output_tokens == 4000
    assert agent_config.sample_retries == 2
    assert agent_config.plan_spares == 2
    assert agent_config.plan_review_enabled is False
    with pytest.raises(ValueError):
        config(plan_max_output_tokens=-1)
    with pytest.raises(ValueError):
        config(sample_retries=6)
    with pytest.raises(ValueError):
        config(plan_spares=-1)


def test_override_parsing() -> None:
    agent_config = config_from_overrides(
        [
            "--model",
            "openai:test-model",
            "--output-mode",
            "text",
            "--max-actions",
            "40",
            "--episode-seconds",
            "250",
            "--transient-retries",
            "1",
            "--seed",
            "7",
            "--prompt-version",
            "test-v1",
            "--tool-binding",
            "pick_up=environment",
            "--sensitive-value",
            "secret",
        ]
    )
    assert agent_config.model == "openai:test-model"
    assert agent_config.output_mode == "text"
    assert agent_config.max_action_attempts == 40
    assert agent_config.max_episode_seconds == 250
    assert agent_config.max_transient_retries == 1
    assert agent_config.random_seed == 7
    assert agent_config.prompt_version == "test-v1"
    assert agent_config.tool_bindings == {"pick_up": "environment"}
    assert agent_config.sensitive_values == ["secret"]


def test_invalid_configuration_and_contracts(action) -> None:
    with pytest.raises(ConfigurationError):
        validate_config(config(model=None))
    with pytest.raises(ConfigurationError):
        validate_config(config(final_response_reserve_seconds=285))
    with pytest.raises(ValueError):
        FinalResponse(
            completed=True,
            answer="x",
            confidence=1.1,
            likely_incorrect=False,
            reason="invalid",
        )
    with pytest.raises(ValueError):
        ActionBatch(call_id="empty", actions=[])
    with pytest.raises(ValueError):
        config(max_action_attempts=51)
    with pytest.raises(SystemExit):
        config_from_overrides(["--model", "test", "--output-mode", "invalid"])
