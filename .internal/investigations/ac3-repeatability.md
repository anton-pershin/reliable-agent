## AC3 repeatability on the default profile

**Status**: active

### Objective

Make project acceptance criterion AC3 (`VM4 <= 0.05`) accepted on the authoritative `default` profile, while preserving the constitution's task-success, sampling, budget, and general-purpose-reasoning requirements. See [constitution](../constitution-spec.md), especially FR1, NFR1, NFR4, NFR5, P8, and P11.

### Current constraints

- Use general-purpose model reasoning over public tasks, observations, action descriptions, and results; no benchmark-specific solver or private evaluator data.
- Use default model sampling as required by constitution preference P11; do not make episodes exact replicas through fixed-seed or deterministic-serving restrictions.
- Keep every episode within 50 action attempts and 300 seconds.
- Use the running dedicated A10 efficiently. Prefer partial configurations containing only unperturbed episodes and inexpensive criteria; avoid AC2/AC4/AC5 experiment populations unless needed for a final regression check.
- Partial validation is diagnostic. Only an unchanged full `default` run can certify project-level AC3 acceptance.

### Current state

The current `main` implementation (`1bd6081`) has the spec 04 planning mechanisms. The latest self-hosted full `default` run, `20261114T053703-525279Z-b864ae241134`, used solution commit `c3e5a94` and produced VM1 = 0.67 and VM4 = 0.15; AC3 remains valid rather than accepted. Per-repeat unperturbed success rates ranged from 0.60 to 0.75. Earlier full default evidence on a different model reached VM1 = 0.99 and a nominal 0.05 repeat range, showing that near-saturated per-task success can stabilize AC3.

Evidence:
- `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261114T053703-525279Z-b864ae241134/`
- [Historical validation results](../validation-results-old.md)
- [Methods report](../reports/methods-report.html)

### Contexts

| ID | Solution implementation | Validation setup | Runtime and environment | Baseline |
|----|-------------------------|------------------|-------------------------|----------|
| C1 | `c3e5a94`, complete-plan voting, 5 plan samples + 1 spare | Full `default`, 20 tasks x 10 unperturbed repeats plus other conditions | Self-hosted `Qwen/Qwen3.5-9B`, A10, vLLM, temperature 0.7 | VM1 = 0.67; VM4 = 0.15 |
| C2 | Experimental engine-enforced prefix consensus | Partial `default`: unperturbed only; initially 3 repeats for screening, then 10 repeats for promising candidates | Same self-hosted 9B runtime as C1 | To be measured |
| C3 | Best available agent implementation | Same diagnostic validation setup as C2 | Self-hosted `Qwen/Qwen3.5-27B-GPTQ-Int4`, A10, default sampling | To be measured |

### Current understanding

#### Supported by evidence

- Whole-plan votes often collapse to lowest-sample-index tie breaking because long sampled plans rarely agree, while first actions have a much stronger mode (spec 04 and methods report).
- Prompt-only short horizons were not followed reliably; plan and goal reviews did not saturate weak-task success.
- Provider-latency instability inflates VM4. The current dedicated self-hosted runtime removes that confounder, leaving per-task model sampling noise.
- Exact per-task success probabilities near 0 or 1 reduce repeat-range variance; a materially stronger model is therefore a legitimate general-purpose candidate.

#### Tentative or unresolved

- Engine-enforced voting and execution over short plan prefixes may realize the first-action consensus that prompt-only horizons failed to capture, but its success and time cost are unmeasured.
- A quantized 27B model may fit the A10 and improve both success and repeatability; throughput and actual validation performance are unmeasured.

### Experiments and decisions

| ID | Idea or question | Context | Result and evidence links | Decision and rationale |
|----|------------------|---------|---------------------------|------------------------|
| E1 | Analyze the latest self-hosted baseline and earlier mechanism results | C1 | VM4 = 0.15 and VM1 = 0.67 in run `20261114T053703-525279Z-b864ae241134`; methods report records weak whole-plan agreement and unsuccessful horizon/review variants | Do not repeat prompt-only horizons or costly review-only variants. Test engine-enforced prefix consensus and a stronger model. |

### Next candidates

- [ ] Implement and test configurable prefix voting/execution, then run a 3-repeat unperturbed-only partial screen on the 9B model.
- [ ] Download and serve the official 27B GPTQ-Int4 checkpoint; measure latency and run the same diagnostic screen.
- [ ] Run 10-repeat unperturbed-only AC1/AC3 validation for the strongest screening candidate.
- [ ] Confirm the selected revision with full `default` validation if time allows; do not use partial acceptance as certification.

### Linked specs

- [Spec 04: Repeatable planning](../specs/04-repeatable-planning-general-spec.md) — existing baseline and prior negative results; a follow-up implementation spec will be linked after candidate selection.
