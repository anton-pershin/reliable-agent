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

**Overall result**: `valid`. All 840 episodes completed in 292 minutes. There were 716 successful episodes, 124 unsuccessful episodes, and 35 episodes flagged as likely incorrect. No infrastructure, authentication, or metric-computation failures occurred. Every criterion is `accepted` or `valid`; none is `invalid`. The complete HTTP response is stored in `.internal/validation-results-full.json`.

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
