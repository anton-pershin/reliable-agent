# JSON Lines interface

## Transport

Run `python -m reliable_agent [solution_overrides]`. Standard input and output contain one JSON object per line. Logs use standard error. Every message has integer `protocol_version: 1` and a `type`.

## Task

The first input message contains public task data:

```json
{
  "protocol_version": 1,
  "type": "task",
  "episode_id": "opaque-id",
  "task": {
    "id": "task-id",
    "instructions": "public instructions",
    "input": "public task input",
    "tools": [
      {
        "name": "tool-name",
        "description": "public description",
        "arguments_schema": {"type": "object"}
      }
    ]
  }
}
```

The agent does not receive private scores, reference plans, or goal-achieved signals.

## Actions

An action decision produces a nonempty batch with a unique string `call_id`:

```json
{
  "protocol_version": 1,
  "type": "actions",
  "call_id": "episode-call-1",
  "actions": [
    {"name": "tool-name", "arguments": {}}
  ]
}
```

Each batch member is an environment action attempt. Catalog requests, failed actions, rejected actions, and retries count. The runner keeps one action call outstanding.

## Observation

The calling system returns one result for each action:

```json
{
  "protocol_version": 1,
  "type": "observation",
  "call_id": "episode-call-1",
  "results": [
    {
      "status": "ok",
      "observation": {"state": ["public predicate"]},
      "error": null
    }
  ]
}
```

`status` is `ok`, `error`, or `rejected`. Errors have `type` and `message`. A transient failure has type `transient_failure` and can cause an identical retry. Result count and call identifier must match the action batch.

## Final

The final message contains the self-assessment:

```json
{
  "protocol_version": 1,
  "type": "final",
  "completed": true,
  "answer": "The public objective is complete.",
  "confidence": 0.9,
  "likely_incorrect": false,
  "reason": "Public observations establish completion."
}
```

`completed` is the explicit completion declaration. It does not prove task success. `confidence` is between 0 and 1. `likely_incorrect` is a strict boolean based on public execution evidence. A controlled stop uses `completed=false` and normally `likely_incorrect=true`.
