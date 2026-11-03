## Validation results

### Spec 01: Baseline reliable agent

**Commit**: `4cf9db2bb5844236cb55ab69e08b2b9b78ec98b9`

**Validation scope**: `full`

**Solution overrides**: `--model openai:gpt-6-luna --model-timeout 180`

**Overall result**: `valid`. Every required metric was computed. No acceptance criterion has status `invalid`. The complete HTTP response is stored in `.internal/validation-results-full.json`.

#### AC1

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM1 | computed | rejected | 0.90 | >= 0.95 | None |

#### AC2

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM2 | computed | accepted | 1.00 | >= 0.80 | None |
| VM3 | computed | accepted | 1.00 | >= 0.50 | None |

#### AC3

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM4 | computed | rejected | 0.20 | <= 0.05 | None |

#### AC4

**Status**: `valid`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM5/concise | computed | accepted | 0.00 | <= 0.05 | None |
| VM5/formal | computed | accepted | 0.00 | <= 0.05 | None |
| VM6 | computed | rejected | 0.10 | <= 0.05 | None |

#### AC5

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM7/pick_up_failure | computed | accepted | 0.00 | <= 0.05 | None |
| VM7/unstack_failure | computed | accepted | 0.00 | <= 0.05 | None |
| VM8 | computed | accepted | 0.00 | <= 0.05 | None |

#### AC6

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM9 | computed | accepted | 21 | <= 50 | None |

#### AC7

**Status**: `accepted`

| Validation metric | Computation status | Acceptance status | Computed value | Expected value or threshold | Error message |
|-------------------|--------------------|-------------------|----------------|-----------------------------|---------------|
| VM10 | computed | accepted | 1.00 | >= 0.95 | None |
