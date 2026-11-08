## Qwen3.5-9B validation results

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
