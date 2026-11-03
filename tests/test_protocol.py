from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from reliable_agent.contracts import ActionBatch
from reliable_agent.errors import ProtocolError
from reliable_agent.protocol import JsonLinesToolExecutor, JsonLinesTransport

ROOT = Path(__file__).resolve().parents[1]


def task_message() -> str:
    return json.dumps(
        {
            "protocol_version": 1,
            "type": "task",
            "episode_id": "subprocess-episode",
            "task": {
                "id": "task-one",
                "instructions": "Complete the objective",
                "input": "public input",
                "tools": [
                    {
                        "name": "get_action_catalog",
                        "description": "List actions",
                        "arguments_schema": {"type": "object", "additionalProperties": False},
                    }
                ],
            },
        }
    )


def observation_message() -> str:
    return json.dumps(
        {
            "protocol_version": 1,
            "type": "observation",
            "call_id": "subprocess-episode-call-1",
            "results": [{"status": "ok", "observation": {"state": []}, "error": None}],
        }
    )


def test_transport_writes_actions_and_final(task, action, final_decision) -> None:
    output = io.StringIO()
    transport = JsonLinesTransport(writer=output)
    batch = ActionBatch(call_id="call-1", actions=[action])
    transport.write_actions(batch)
    transport.write_final(final_decision)
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert lines[0]["type"] == "actions"
    assert lines[0]["call_id"] == "call-1"
    assert lines[1] == {
        "protocol_version": 1,
        "type": "final",
        **final_decision.to_response().model_dump(),
    }


async def test_transport_reads_observation(action) -> None:
    reader = io.StringIO(observation_message() + "\n")
    writer = io.StringIO()
    transport = JsonLinesTransport(reader=reader, writer=writer)
    executor = JsonLinesToolExecutor(transport)
    observation = await executor.execute(
        ActionBatch(call_id="subprocess-episode-call-1", actions=[action])
    )
    assert observation.call_id == "subprocess-episode-call-1"
    assert observation.results[0].status == "ok"


def test_transport_rejects_invalid_version_and_large_input() -> None:
    invalid = json.loads(task_message())
    invalid["protocol_version"] = True
    with pytest.raises(ProtocolError):
        JsonLinesTransport(reader=io.StringIO(json.dumps(invalid) + "\n")).read_task()
    with pytest.raises(ProtocolError):
        JsonLinesTransport(reader=io.StringIO("{}\n"), max_message_bytes=1)._read()


def test_real_module_entrypoint_json_lines_contract() -> None:
    driver = r"""
from reliable_agent.contracts import ActionDecision, ActionRequest, FinalDecision
import reliable_agent.__main__ as entry

class ScriptedModel:
    def __init__(self, logger):
        pass
    async def decide(self, state, remaining_seconds):
        if not state.attempts:
            return ActionDecision(
                actions=[ActionRequest(name="get_action_catalog", arguments={})]
            )
        return FinalDecision(
            completed=True,
            answer="complete",
            confidence=0.9,
            likely_incorrect=False,
            reason="public observation",
        )

entry.PydanticAIModelClient = ScriptedModel
raise SystemExit(entry.main())
"""
    completed = subprocess.run(
        [sys.executable, "-c", driver, "--model", "test"],
        input=task_message() + "\n" + observation_message() + "\n",
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(lines) == 2
    assert lines[0]["type"] == "actions"
    assert lines[1]["type"] == "final"
    assert lines[1]["completed"] is True
    assert lines[1]["likely_incorrect"] is False
    logs = [json.loads(line) for line in completed.stderr.splitlines()]
    assert any(event["event"] == "model_request" for event in logs) is False
    assert any(event["event"] == "action_observation" for event in logs)


def test_module_help_and_missing_model_error() -> None:
    help_result = subprocess.run(
        [sys.executable, "-m", "reliable_agent", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--model" in help_result.stdout
    missing = subprocess.run(
        [sys.executable, "-m", "reliable_agent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert missing.returncode == 2
    assert not missing.stdout
