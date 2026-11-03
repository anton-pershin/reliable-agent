## Validation results

### Spec 01: Baseline reliable agent

**Commit**: `2013a9d21f86c4fa59d0b3977a1d4a5ec50f1877`

**Validation scope**: `full`

**Solution overrides**: `--model openai:gpt-6-luna --model-timeout 180`

**Overall result**: `valid`. Forty-one of 42 episodes succeeded. Every required metric was computed and no acceptance criterion has status `invalid`. The complete HTTP response is stored in `.internal/validation-results-full.json`.

#### AC1

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1/unperturbed_overall_success_rate | computed | accepted | 1.00 | >= 0.95 | None |

#### AC2

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2/error_flag_precision | computed | accepted | 1.00 | >= 0.80 | None |
| VM3/error_flag_recall | computed | rejected | 0.00 | >= 0.50 | None |

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

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/transient_failure_overall_success_rate_loss/pick_up_failure | computed | rejected | 0.125 | <= 0.05 | None |
| VM7/transient_failure_overall_success_rate_loss/unstack_failure | computed | accepted | 0.00 | <= 0.05 | None |
| VM8/transient_failure_overall_success_rate_range | computed | accepted | 0.00 | <= 0.05 | None |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9/maximum_action_attempts | computed | accepted | 19 | <= 50 | None |

#### AC7

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10/timely_final_response_rate | computed | accepted | 1.00 | >= 0.95 | None |
