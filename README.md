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

`auto` tries Pydantic AI structured-tool output first and falls back to validated JSON text when the provider rejects the tool contract. `tool` disables fallback, while `text` always uses JSON text. For example, the following model works through the text fallback:

```bash
python -m reliable_agent \
  --model openai:alibaba-qwen2-5-coder-7b-instruct-awq \
  --output-mode auto
```

Text responses are validated with the same `Decision` schema as tool responses. Markdown fences and repair events are logged.

## Consistent planning

By default, the agent plans before it acts. It fires several concurrent candidate-plan samples plus configurable spares, keeps the fastest completions, and asks the model to review each candidate's step-by-step validity. Candidates that break at some action are truncated to their valid prefix; the vote selects among the surviving plans and prefixes. The runner executes the selected plan in order. Action failures, plan exhaustion without completion, and rejected or unavailable completion verifications start a new plan round from the current task state, up to the re-planning limit. Plans that already failed in the episode are excluded from later votes while fresh candidates remain. When a plan that claimed completion finishes, concurrent verification samples check the task goal against the latest observation; only a satisfied verdict produces a completion declaration. If planning is unavailable or disabled with `--no-planning`, the engine uses per-step decisions. Plan votes, reviews, truncations, selected plans, re-planning causes, and verification results are logged with their episode identifiers.

With `--plan-horizon N`, the planner returns at most N actions per candidate plus a `reaches_goal` flag instead of one complete plan. A plan exhausted without `reaches_goal` starts a new plan round immediately, without verification. Shorter plans agree with each other more often, which sharpens the majority vote on noisy models.

`--plan-execution-horizon N` enforces a prefix without changing those plan instructions. The engine can therefore sample ordinary complete plans, truncate every candidate to its first N actions before voting, execute only the winning prefix, and plan again from the resulting observation. This avoids relying on the model to comply with a short-plan prompt. Before the first observation, valid actionable candidates suppress empty completion claims; an empty-only round can still verify an initially satisfied objective. Candidates with the same normalized prefix must unanimously claim completion before the selected prefix can enter completion verification. The default execution horizon is 0, which preserves complete-plan execution.

`--plan-vote-horizon V` makes voting compare only the first V actions without truncating the returned representative. For example, `--plan-vote-horizon 1 --plan-execution-horizon 2` votes on first actions but executes two actions from the winning candidate. Completion unanimity uses the same vote prefix. The default is 0.

`--selected-plan-review` adds one validity review after the vote and before execution. Unlike `--plan-review`, which reviews every full candidate concurrently, this reviews only the selected short prefix. An invalid first action causes re-planning without environment execution; an invalid later action truncates the prefix to its valid part. Review failures leave the selected prefix unchanged. The default is off.

`--planning-strategy goal_regression` optionally asks the planner to derive required actions backward from goal predicates and conflicts before checking the forward plan. The default `forward` strategy keeps the established complete-plan instructions.

`--transition-tabu` remembers public state/action pairs and excludes candidates whose first action repeats an observed transition from the same state. If every candidate repeats, the engine requests a fresh plan without executing an action. Transient-failure retries are exempt. The default is off.

`--verification-consensus` waits for all `--verification-samples N` independent verdicts and accepts completion only with a strict majority of the configured sample count. Missing responses and split votes cannot establish completion; negative verdicts contribute missing/conflicting-predicate feedback. Without this flag, the legacy fastest-verdict behavior remains.

`--free-sampling` omits the provider `seed` parameter from every request, including plan samples and retries. It therefore uses the serving engine's ordinary stochastic sampling rather than the legacy fixed seed. The new AC3 candidate uses this mode to comply with constitution preference P11.

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
| `--output-mode MODE` | `auto` | `auto`, `tool`, or `text` output and fallback behavior |
| `--temperature N` | `0.0` | Generation temperature |
| `--max-output-tokens N` | `8000` | Output-token limit |
| `--prompt-version VERSION` | `consistent-planning-v1` | Prompt version recorded in logs |
| `--planning-strategy MODE` | `forward` | `forward` or `goal_regression` complete-plan reasoning |
| `--transition-tabu / --no-transition-tabu` | off | Suppress actions already observed from the same public state |
| `--verification-consensus / --no-verification-consensus` | off | Require a strict independent-verifier majority for completion |
| `--free-sampling / --no-free-sampling` | off | Omit provider seeds from model requests |
| `--planning / --no-planning` | on | Plan-vote-execute decision flow |
| `--plan-samples N` | `3` | Candidate plans per vote |
| `--plan-spares N` | `1` | Extra plan samples per vote; only the fastest completions count |
| `--plan-max-output-tokens N` | `0` | Per-sample plan output cap; `0` uses the global limit |
| `--plan-horizon N` | `0` | Maximum actions requested per candidate; `0` requires a complete plan |
| `--plan-execution-horizon N` | `0` | Prefix length enforced before voting/execution, independent of plan instructions |
| `--plan-vote-horizon N` | `0` | Prefix compared by voting without truncating the returned representative |
| `--plan-review / --no-plan-review` | on | Validity review of candidate plans with prefix truncation |
| `--selected-plan-review / --no-selected-plan-review` | off | One post-vote validity review of the selected short prefix |
| `--sample-retries N` | `1` | Retries per plan or verification sample after a transient failure |
| `--verification-samples N` | `2` | Fastest-verdict race size, or independent consensus size with `--verification-consensus` |
| `--max-replans N` | `12` | Re-planning rounds per episode after the first plan |
| `--completion-verification / --no-completion-verification` | on | Goal verification before completion declarations |
| `--verification-timeout N` | `90` | Verification sample timeout |
| `--max-actions N` | `45` | Emitted environment-action budget, maximum 50 |
| `--episode-seconds N` | `285` | End-to-end episode budget, maximum 300 |
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

The `default` registered profile is authoritative for project acceptance; `blocksworld_hard` is supplementary. With the validation service running, set its base URL and the exact solution commit:

```bash
BASE=http://127.0.0.1:8000
COMMIT=FULL_COMMIT_HASH
```

### Full validation

`POST /validate` uses the active registered profile unchanged and does not accept inline configuration:

```bash
curl -sS -X POST "$BASE/validate" \
  -H 'Content-Type: application/json' \
  -d '{
    "repo": "https://github.com/anton-pershin/reliable-agent.git",
    "commit": "'"$COMMIT"'",
    "solution_overrides": "--model openai:gpt-5-mini"
  }'
```

### Configuration discovery and partial validation

Retrieve the complete normalized configuration and its JSON Schema:

```bash
curl -sS "$BASE/profiles/default/configuration" > /tmp/reliable-agent-default-discovery.json
```

The response contains `profile`, `configuration`, and `schema`. Edit the complete `configuration` value, then submit it as `configuration` to `/validate_partial`. For example, the following standard-library Python snippet creates a valid payload with one repeat per planned condition; modify the configuration as needed before writing the payload:

```bash
python - <<'PY'
import json
import os
from pathlib import Path

with open("/tmp/reliable-agent-default-discovery.json", encoding="utf-8") as stream:
    document = json.load(stream)
configuration = document["configuration"]
configuration["full"]["repeats"] = 1
payload = {
    "repo": "https://github.com/anton-pershin/reliable-agent.git",
    "commit": os.environ["COMMIT"],
    "solution_overrides": "--model openai:gpt-5-mini",
    "profile": "default",
    "configuration": configuration,
}
Path("/tmp/reliable-agent-partial-payload.json").write_text(
    json.dumps(payload), encoding="utf-8"
)
PY
curl -sS -X POST "$BASE/validate_partial" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/reliable-agent-partial-payload.json
```

A partial request must submit the complete modified configuration, not a patch. The optional `profile` selects its registered base and defaults to the service's active profile. Partial configurations may change any setting and need not be smaller or faster than full validation. Partial results are diagnostic only and cannot certify acceptance, even when all reported criteria are accepted.

### Results and run history

Successful results contain `run_id`, `artifacts_location`, the registered base `profile`, `validation_scope`, and the in-scope criteria. Errors raised after run creation contain the same run identity. For a completed run, the complete response is stored at `<artifacts_location>/result.json`; `<artifacts_location>/run.json` records a terminal status of `completed`, `failed`, or `aborted`.

Only a completed full result from the unchanged `default` profile with every criterion accepted certifies an accepted implementation. Append every completed, failed, or aborted full run to `.internal/validation-results.md`, including its run ID, related spec, solution commit, run status, and returned `artifacts_location`. Never replace an earlier entry or add partial runs. Results produced before the run-aware contract are retained in `.internal/validation-results-old.md`.
