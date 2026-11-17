## Full-validation history

Append one row for every completed, failed, or aborted full-validation run performed after the run-aware contract migration. Do not delete an earlier run or replace it with a different run. In "Run directory", store the path or URI returned as `artifacts_location`. For every completed run, all acceptance-criterion and validation-metric outcomes are available at `<run directory>/result.json`. Partial runs are diagnostic and do not belong in this history.

Runs performed under earlier validation contracts are preserved unchanged in [validation-results-old.md](validation-results-old.md).

| Run ID | Spec | Solution commit | Run status | Run directory |
|--------|------|-----------------|------------|---------------|
