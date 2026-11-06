## Qwen3.5-9B validation results

### Spec 02: Text JSON fallback

**Commit**: `b409ca553d16c087502011f1e7b9228f74cf6e23`

**Run ID**: `20261105T144402-615553Z-c536cfe700cf`

**Validation scope**: `full`

**Model**: `openai:qwen/qwen3.5-9b`

**Output mode**: `auto`

**Temperature**: 0.7

**Random seeds**: 1 through 10, selected by repeat number

**Model timeout**: 180 seconds

**Episode concurrency**: 4

**Evidence directory**: `/tmp/opencode/validation-artifacts-qwen3-5-9b-full/20261105T144402-615553Z-c536cfe700cf/`

**Overall result**: `invalid`. All 890 episodes completed in 474 minutes. There were 724 successful episodes, 166 unsuccessful episodes, and 89 episodes flagged as likely incorrect. No infrastructure or authentication failures occurred. AC5 is `invalid` because the model did not reach the required pick-up and unstack fault-injection points in every failure scenario. The complete HTTP response is stored in `.internal/validation-results-full.json`.

#### AC1

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | rejected | 0.82 | >= 0.95 | None |

#### AC2

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | accepted | 0.536144578313253 | >= 0.50 | None |

#### AC3

**Status**: `valid`

The unperturbed success rates for repeats 1 through 10 were 0.95, 0.85, 0.80, 0.65, 0.85, 0.90, 0.75, 0.80, 0.80, and 0.85.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4/repeated_run_overall_success_rate_range | computed | rejected | 0.29999999999999993 | <= 0.05 | None |

#### AC4

**Status**: `valid`

The negative formal-variant VM5 value represents a 0.055 success-rate gain.

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/prompt_variant_overall_success_rate_loss/concise | computed | accepted | 0.0 | <= 0.05 | None |
| VM5/prompt_variant_overall_success_rate_loss/formal | computed | accepted | -0.05500000000000005 | <= 0.05 | None |
| VM6/prompt_variant_overall_success_rate_range | computed | rejected | 0.05500000000000005 | <= 0.05 | None |

#### AC5

**Status**: `invalid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/pick_up_failure |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/unstack_failure |
| VM8/transient_failure_overall_success_rate_range | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/pick_up_failure |

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
