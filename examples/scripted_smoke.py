"""Run the JSON Lines runner with scripted decisions and no model provider."""

from __future__ import annotations

import asyncio
import io
import json

from reliable_agent import (
    ActionDecision,
    ActionRequest,
    AgentConfig,
    DecisionEngine,
    EventLogger,
    FinalDecision,
)
from reliable_agent.protocol import JsonLinesToolExecutor, JsonLinesTransport
from reliable_agent.runner import TaskRunner

TASK = {
    "protocol_version": 1,
    "type": "task",
    "episode_id": "smoke-episode",
    "task": {
        "id": "smoke-task",
        "instructions": "Inspect the catalog and stop",
        "input": "public smoke input",
        "tools": [
            {
                "name": "get_action_catalog",
                "description": "List actions",
                "arguments_schema": {"type": "object", "additionalProperties": False},
            }
        ],
    },
}
OBSERVATION = {
    "protocol_version": 1,
    "type": "observation",
    "call_id": "smoke-episode-call-1",
    "results": [{"status": "ok", "observation": {"actions": []}, "error": None}],
}


class ScriptedModel:
    async def decide(self, state, remaining_seconds):
        if not state.attempts:
            return ActionDecision(actions=[ActionRequest(name="get_action_catalog", arguments={})])
        return FinalDecision(
            completed=True,
            answer="Smoke run complete",
            confidence=0.99,
            likely_incorrect=False,
            reason="The public catalog observation was received",
        )


async def main() -> None:
    reader = io.StringIO(json.dumps(TASK) + "\n" + json.dumps(OBSERVATION) + "\n")
    transport = JsonLinesTransport(reader=reader)
    config = AgentConfig(model="scripted")
    logger = EventLogger("smoke-episode", config)
    engine = DecisionEngine(ScriptedModel(), logger)
    runner = TaskRunner(engine, JsonLinesToolExecutor(transport))
    _, task = transport.read_task()
    decision = await runner.run(task)
    transport.write_final(decision)


if __name__ == "__main__":
    asyncio.run(main())
