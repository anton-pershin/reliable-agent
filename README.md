# Reliable agent

Reliable agent is a reusable baseline agent built around Pydantic AI. It uses structured action and final decisions, keeps task state local to an episode, and supports external tool execution through one asynchronous interface. The reusable engine has no benchmark or validation-service dependency.

## Install

Python 3.11 or later is required.

```bash
python3 -m venv /path/to/venvs/reliable-agent
/path/to/venvs/reliable-agent/bin/python -m pip install -e '.[dev]'
```

## Model configuration

Set the model with `--model`, `RELIABLE_AGENT_MODEL`, or `AgentConfig(model=...)`. Provider credentials come from the provider's ordinary environment variables, such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

Examples:

```bash
export RELIABLE_AGENT_MODEL=openai:gpt-5-mini
export RELIABLE_AGENT_MODEL=anthropic:claude-sonnet-4-5
```

Do not put credentials in `solution_overrides` or task input. Effective configuration never contains `sensitive_values`.

## JSON Lines execution

The process entry point is:

```bash
python -m reliable_agent --model openai:gpt-5-mini [other overrides]
```

Standard input and output carry one JSON object per line. Standard output contains protocol messages only. Standard error contains structured logs. One process handles one episode.

A run starts with a `task` message. The agent returns `actions`, accepts an `observation`, and finishes with `final`. See [the interface contract](docs/interface.md) for exact message shapes.

## Overrides

| Override | Default | Purpose |
|----------|---------|---------|
| `--model NAME` | `RELIABLE_AGENT_MODEL` or none | Provider and model identifier |
| `--temperature N` | `0.0` | Generation temperature |
| `--max-output-tokens N` | `2000` | Output-token limit |
| `--prompt-version VERSION` | `baseline-v1` | Prompt version recorded in logs |
| `--max-actions N` | `45` | Emitted environment-action budget, maximum 50 |
| `--episode-seconds N` | `270` | End-to-end episode budget, maximum 300 |
| `--model-timeout N` | `60` | Model request timeout |
| `--transient-retries N` | `2` | Identical retries per action after transient failure |
| `--decision-retries N` | `2` | Pydantic AI structured-output retries |
| `--decision-rejections N` | `2` | Rejected decisions before controlled stop |
| `--max-context-items N` | `40` | Retained action attempts in model context |
| `--final-response-reserve N` | `30` | Reserved final-response time |
| `--max-concurrency N` | `4` | Concurrency for `run_concurrently` |
| `--max-protocol-bytes N` | `1000000` | JSON Lines message limit |
| `--log-level LEVEL` | `INFO` | `DEBUG`, `INFO`, or `ERROR` |
| `--seed N` | `0` | Recorded random seed |
| `--tool-binding NAME=BINDING` | empty | Public tool-binding metadata; repeat as needed |
| `--sensitive-value VALUE` | empty | Additional value to redact; repeat as needed |

The final-response reserve must be smaller than the episode budget. The Python API exposes the same settings through `AgentConfig`.

## Python API

```python
from reliable_agent import (
    ActionBatch,
    AgentConfig,
    DecisionEngine,
    EventLogger,
    Observation,
    PydanticAIModelClient,
    Task,
    TaskRunner,
    ToolDescription,
)


class Environment:
    async def execute(self, batch: ActionBatch) -> Observation:
        # Execute actions and return one result per action.
        ...


config = AgentConfig(model="openai:gpt-5-mini")
logger = EventLogger("episode-1", config)
engine = DecisionEngine(PydanticAIModelClient(logger), logger)
runner = TaskRunner(engine, Environment())
task = Task(id="task-1", instructions="Complete the objective", input="public input", tools=[])
decision = await runner.run(task)
```

Use `run_concurrently` for independent runners and tasks. Decision state and effective configuration are not stored in mutable globals.

## Failure behavior and logs

A transient tool failure causes an identical retry without another model request. After the configured limit, the model receives the failure and chooses a new decision. Provider errors, invalid decisions, tool errors, and budget exhaustion produce a controlled final response with `completed=false` and `likely_incorrect=true` when a response is still possible.

Logs are JSON events with episode, operation, and attempt identifiers, event order, timestamps, durations, configuration and dependency versions, model metadata, actions, observations, retries, truncation, and termination. Credentials and configured sensitive values are redacted. Private model reasoning is not retained.

## Tests and smoke run

```bash
/path/to/venvs/reliable-agent/bin/pytest
/path/to/venvs/reliable-agent/bin/ruff check .
/path/to/venvs/reliable-agent/bin/python examples/scripted_smoke.py
```

The test suite and smoke run need no model provider.

## HTTP validation

With the validation service running, send the exact repository and commit:

```bash
curl -sS -X POST http://127.0.0.1:8000/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "repo": "https://github.com/anton-pershin/reliable-agent.git",
    "commit": "FULL_COMMIT_HASH",
    "solution_overrides": "--model openai:gpt-5-mini"
  }'
```

Use `/validate_partial` for faster diagnostic runs. Only a full response with every criterion accepted certifies acceptance.
