## Qwen3.5-9B validation results, blocksworld_hard profile, run 2 (spec 04)

### Spec 04: Repeatable planning

**Commit**: `391b9eef0e138e6021d2866222ca3ada69cab87b`

**Run ID**: `20261111T003024-637428Z-79e7142b5f51`

**Validation scope**: `full`

**Validation implementation**: `agent-validation` service at `http://127.0.0.1:8678`, profile `blocksworld_hard` (sha256 `8a26b371d66cd9ef5e731704feed63da71f48cf258db5386d06c5272106af244`)

**Model**: `openai:qwen/qwen3.5-9b`

**Solution overrides**: `--model openai:qwen/qwen3.5-9b --temperature 0.7 --model-timeout 90 --sample-retries 2 --plan-max-output-tokens 3000 --no-plan-review`

**Evidence directory**: `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261111T003024-637428Z-79e7142b5f51/`

**Overall result**: `valid`. All 890 episodes completed in 974 minutes with no infrastructure failures. There were 357 successful episodes and 533 unsuccessful episodes; 532 were flagged as likely incorrect. Per-repeat unperturbed success rates were 0.75, 0.50, 0.20, 0.35, 0.45, 0.80, 0.70, 0.05, 0.15, 0.45.

**Root-cause analysis**: The unperturbed success rate tracks provider latency, not agent behavior. Repeat 1 ran in a fast window (plan-round p50 27s, zero timeouts) and scored 0.75; repeats 6-7 scored 0.80 and 0.70 in a later fast window; repeats 3, 8, and 9 landed in provider slow windows (plan-round p50 60-150s, accumulating timeouts) and scored 0.05-0.20. The ten repeats span ~13 hours of wall-clock, so VM4 measures provider stability across the day. The same effect produced the baseline run's repeats 7-9 dip (0.30-0.35). The spec 04 improvements raised the fast-window ceiling from 0.70 to 0.80 and removed all token-cap sample deaths (662 in the baseline run, 0 here).

| Criterion | Status | Detail |
|-----------|--------|--------|
| AC1 | valid | VM1 = 0.44 < 0.95 |
| AC2 | accepted | VM2 = 1.00, VM3 = 0.998 |
| AC3 | valid | VM4 = 0.75 > 0.05 (provider latency windows) |
| AC4 | valid | VM5 concise = 0.055, VM5 formal = 0.06, VM6 = 0.06 (marginally rejected) |
| AC5 | invalid | fault exposure not observed in every failure episode |
| AC6 | accepted | VM9 = 34 <= 50 |
| AC7 | accepted | VM10 = 1.00 |

The complete HTTP response is stored in `.internal/validation-results-blocksworld-hard-full-run2.json`.

## Qwen3.5-9B validation results, blocksworld_hard profile, run 1 (baseline)

### Spec 03: Consistent planning

**Commit**: `9036c1505c34d81b1c63cb25c6da2ef07ca5695b`

**Run ID**: `20261109T031132-994501Z-f22e7aa722f7`

**Validation scope**: `full`

**Validation implementation**: `agent-validation` service at `http://127.0.0.1:8678`, profile `blocksworld_hard` (sha256 `8a26b371d66cd9ef5e731704feed63da71f48cf258db5386d06c5272106af244`)

**Model**: `openai:qwen/qwen3.5-9b`

**Output mode**: `auto`

**Temperature**: 0.7

**Random seeds**: 1 through 10, selected by repeat number. Plan samples and verification samples use deterministic derived sub-seeds, recorded in the episode logs.

**Model timeout**: 180 seconds. **Verification sample timeout**: 90 seconds.

**Episode concurrency**: 4

**Evidence directory**: `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261109T031132-994501Z-f22e7aa722f7/`

**Overall result**: `valid`. All 890 episodes completed in 828 minutes. There were 491 successful episodes and 399 unsuccessful episodes; 397 episodes were flagged as likely incorrect. One episode (`prompt/concise`, task `rebuild_06`) ended with the solution exiting with status 0 before a final response; no other infrastructure, authentication, or metric-computation failures occurred. Four criteria are `accepted`; AC1, AC3, and AC4 are `valid`; AC5 is `invalid` because fault exposure was not observed in every failure episode, so the VM7 and VM8 instances failed to compute. The complete HTTP response is stored in `.internal/validation-results-blocksworld-hard-full.json`.

The `blocksworld_hard` profile is substantially harder than `default`: its 20 tasks have optimal plan lengths of 8, 10, or 12 movement actions (mean 10). The unperturbed success rate dropped from 0.99 on `default` to 0.535 on `blocksworld_hard`, and repeat-to-repeat variance grew accordingly.

#### AC1

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | rejected | 0.5349999999999999 | >= 0.95 | None |

#### AC2

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | accepted | 0.9949874686716792 | >= 0.50 | None |

#### AC3

**Status**: `valid`

The unperturbed success rates for repeats 1 through 10 were 0.60, 0.55, 0.70, 0.60, 0.60, 0.70, 0.30, 0.35, 0.35, and 0.60.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4/repeated_run_overall_success_rate_range | computed | rejected | 0.39999999999999997 | <= 0.05 | None |

#### AC4

**Status**: `valid`

The negative VM5 value for the formal variant represents a success-rate gain of 0.03.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/prompt_variant_overall_success_rate_loss/concise | computed | accepted | 0.02499999999999991 | <= 0.05 | None |
| VM5/prompt_variant_overall_success_rate_loss/formal | computed | accepted | -0.030000000000000138 | <= 0.05 | None |
| VM6/prompt_variant_overall_success_rate_range | computed | rejected | 0.05500000000000005 | <= 0.05 | None |

#### AC5

**Status**: `invalid`

Required fault exposure was not observed for every failure episode: 191 of 200 `pick_up_failure` episodes and 88 of 90 `unstack_failure` episodes were exposed. In the remaining episodes the agent finished before attempting the fault-injected action, so the VM7 and VM8 instances could not be computed.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/pick_up_failure |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/unstack_failure |
| VM8/transient_failure_overall_success_rate_range | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/pick_up_failure |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9/maximum_action_attempts | computed | accepted | 38 | <= 50 | None |

#### AC7

**Status**: `accepted`

The single late final response corresponds to the `prompt/concise` episode on task `rebuild_06` where the solution exited with status 0 before a final response.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10/timely_final_response_rate | computed | accepted | 0.998876404494382 | >= 0.95 | None |

## Qwen3.5-9B validation results (superseded `default` profile)

### Spec 03: Consistent planning

**Commit**: `827cef8620662226a9471293f7ba88b513c7dd47`

**Run ID**: `20261107T003923-202490Z-81f70aae68a3`

**Validation scope**: `full`

**Validation implementation**: `agent-validation` service at `http://127.0.0.1:8587`, profile `default` (sha256 `b3fa4165855b575685ab107f3658573472055838a639f3fb923cf86d163c5bf0`)

**Model**: `openai:qwen/qwen3.5-9b`

**Output mode**: `auto`

**Temperature**: 0.7

**Random seeds**: 1 through 10, selected by repeat number. Plan samples and verification samples use deterministic derived sub-seeds, recorded in the episode logs.

**Model timeout**: 180 seconds. **Verification sample timeout**: 90 seconds.

**Episode concurrency**: 4

**Evidence directory**: `/tmp/opencode/validation-artifacts-8587/20261107T003923-202490Z-81f70aae68a3/`

**Overall result**: `valid`. All 840 episodes completed in 367 minutes. There were 824 successful episodes and 16 unsuccessful episodes; all 16 unsuccessful episodes were flagged as likely incorrect. No infrastructure, authentication, or metric-computation failures occurred. Six criteria are `accepted`; AC3 is `valid`. The complete HTTP response is stored in `.internal/validation-results-full.json`.

Repeatability evidence: an earlier full run of commit `0c922f423b1e6ef635c967a7c98d04c7f3336fad` (run `20261106T202805-402096Z-716024d96c50`) gave VM1 = 0.985 and the same VM4 = 0.05 (float artifact), with AC5 `valid` at VM8 = 0.075.

#### AC1

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | accepted | 0.99 | >= 0.95 | None |

#### AC2

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | accepted | 1.00 | >= 0.50 | None |

#### AC3

**Status**: `valid`

The unperturbed success rates for repeats 1 through 10 were 1.00, 1.00, 1.00, 0.95, 1.00, 1.00, 1.00, 0.95, 1.00, and 1.00. The true range is exactly 0.05, equal to the threshold; the recorded computed value is the IEEE754 subtraction artifact `1.00 - 0.95 = 0.050000000000000044`, which the strict `<= 0.05` comparison rejects.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4/repeated_run_overall_success_rate_range | computed | rejected | 0.050000000000000044 | <= 0.05 | None |

#### AC4

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/prompt_variant_overall_success_rate_loss/concise | computed | accepted | 0.030000000000000027 | <= 0.05 | None |
| VM5/prompt_variant_overall_success_rate_loss/formal | computed | accepted | 0.009999999999999898 | <= 0.05 | None |
| VM6/prompt_variant_overall_success_rate_range | computed | accepted | 0.030000000000000027 | <= 0.05 | None |

#### AC5

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | computed | accepted | 0.0 | <= 0.05 | None |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | computed | accepted | 0.0 | <= 0.05 | None |
| VM8/transient_failure_overall_success_rate_range | computed | accepted | 0.025000000000000022 | <= 0.05 | None |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9/maximum_action_attempts | computed | accepted | 28 | <= 50 | None |

#### AC7

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10/timely_final_response_rate | computed | accepted | 1.00 | >= 0.95 | None |

## Qwen3.5-9B final baseline validation results

### Spec 02: Text JSON fallback

**Commit**: `b409ca553d16c087502011f1e7b9228f74cf6e23`

**Run ID**: `20261106T045238-904273Z-2371b20fca30`

**Validation scope**: `full`

**Validation implementation**: `agent-validation` PR #8, commit `53a1617e726d97862119c987c8dc28de6fa0cbf8`

**Model**: `openai:qwen/qwen3.5-9b`

**Output mode**: `auto`

**Temperature**: 0.7

**Random seeds**: 1 through 10, selected by repeat number

**Model timeout**: 180 seconds

**Episode concurrency**: 4

**Evidence directory**: `/tmp/opencode/validation-artifacts-qwen3-5-9b-final-baseline/20261106T045238-904273Z-2371b20fca30/`

**Overall result**: `valid`. All 840 episodes completed in 292 minutes. There were 716 successful episodes, 124 unsuccessful episodes, and 35 episodes flagged as likely incorrect. No infrastructure, authentication, or metric-computation failures occurred. Every criterion is `accepted` or `valid`; none is `invalid`.

#### AC1

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | rejected | 0.8550000000000001 | >= 0.95 | None |

#### AC2

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | rejected | 0.28225806451612906 | >= 0.50 | None |

#### AC3

**Status**: `valid`

The unperturbed success rates for repeats 1 through 10 were 0.80, 0.85, 0.85, 0.80, 0.85, 0.85, 0.80, 0.95, 0.90, and 0.90.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4/repeated_run_overall_success_rate_range | computed | rejected | 0.1499999999999999 | <= 0.05 | None |

#### AC4

**Status**: `accepted`

The negative VM5 values represent success-rate gains of 0.045 for the concise variant and 0.025 for the formal variant.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/prompt_variant_overall_success_rate_loss/concise | computed | accepted | -0.04499999999999993 | <= 0.05 | None |
| VM5/prompt_variant_overall_success_rate_loss/formal | computed | accepted | -0.025000000000000022 | <= 0.05 | None |
| VM6/prompt_variant_overall_success_rate_range | computed | accepted | 0.04499999999999993 | <= 0.05 | None |

#### AC5

**Status**: `valid`

All VM7 and VM8 instances were computed. Successful and unsuccessful episodes without exposure were included in overall scenario success but were not counted as exposed-recovery evidence.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | computed | rejected | 0.05999999999999983 | <= 0.05 | None |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | computed | accepted | 0.0 | <= 0.05 | None |
| VM8/transient_failure_overall_success_rate_range | computed | rejected | 0.17500000000000004 | <= 0.05 | None |

| Failure scenario | Fault-exposure rate | Exposed-recovery success rate |
|------------------|--------------------|------------------------------|
| pick_up_failure | 146/150 = 0.9733333333333334 | 0.7655555555555557 |
| unstack_failure | 90/90 = 1.0 | 0.8444444444444444 |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9/maximum_action_attempts | computed | accepted | 45 | <= 50 | None |

#### AC7

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10/timely_final_response_rate | computed | accepted | 1.00 | >= 0.95 | None |
