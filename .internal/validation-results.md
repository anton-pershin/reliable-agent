## Validation results

### Spec 02: Text JSON fallback

**Commit**: `b409ca553d16c087502011f1e7b9228f74cf6e23`

**Validation scope**: `full`

**Model**: `openai:alibaba-qwen2-5-coder-7b-instruct-awq`

**Output mode**: `auto`

**Model timeout**: 180 seconds

**Overall result**: `invalid`. All 42 episodes completed. Most metrics were computed, but AC5 is `invalid` because the model did not reach the required unstack fault-injection point in every failure scenario. The complete HTTP response is stored in `.internal/validation-results-full.json`.

#### AC1

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | rejected | 0.40 | >= 0.95 | None |

#### AC2

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | accepted | 0.8214285714285714 | >= 0.50 | None |

#### AC3

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4/repeated_run_overall_success_rate_range | computed | accepted | 0.00 | <= 0.05 | None |

#### AC4

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/prompt_variant_overall_success_rate_loss/concise | computed | accepted | 0.00 | <= 0.05 | None |
| VM5/prompt_variant_overall_success_rate_loss/formal | computed | accepted | 0.00 | <= 0.05 | None |
| VM6/prompt_variant_overall_success_rate_range | computed | accepted | 0.00 | <= 0.05 | None |

#### AC5

**Status**: `invalid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | computed | rejected | 0.25 | <= 0.05 | None |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/unstack_failure |
| VM8/transient_failure_overall_success_rate_range | failed_to_compute | None | None | <= 0.05 | Required fault exposure was not observed for every episode in failure/unstack_failure |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9/maximum_action_attempts | computed | accepted | 22 | <= 50 | None |

#### AC7

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10/timely_final_response_rate | computed | accepted | 1.00 | >= 0.95 | None |
