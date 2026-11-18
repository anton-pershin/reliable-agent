## Full-validation history

Append one row for every completed, failed, or aborted full-validation run performed after the run-aware contract migration. Do not delete an earlier run or replace it with a different run. In "Run directory", store the path or URI returned as `artifacts_location`. For every completed run, all acceptance-criterion and validation-metric outcomes are available at `<run directory>/result.json`. Partial runs are diagnostic and do not belong in this history.

Runs performed under earlier validation contracts are preserved unchanged in [validation-results-old.md](validation-results-old.md).

| Run ID | Spec | Solution commit | Run status | Run directory |
|--------|------|-----------------|------------|---------------|
| 20261117T055953-096107Z-35ebc2cac9b0 | [05](specs/05-sdd-validation-contract-migration-kiss-spec.md) | b490da19b8a919b9c8867c1b54efdf87fc5af958 | aborted | /home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261117T055953-096107Z-35ebc2cac9b0 |
| 20261117T150114-324103Z-9acb73d41f31 | [05](specs/05-sdd-validation-contract-migration-kiss-spec.md) | b490da19b8a919b9c8867c1b54efdf87fc5af958 | completed | /home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261117T150114-324103Z-9acb73d41f31 |
