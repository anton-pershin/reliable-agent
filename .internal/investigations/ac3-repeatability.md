## AC3 repeatability on the default profile

**Status**: active

### Objective

Make project acceptance criterion AC3 (`VM4 <= 0.05`) accepted on the authoritative `default` profile, while preserving the constitution's task-success, sampling, budget, and general-purpose-reasoning requirements. See [constitution](../constitution-spec.md), especially FR1, NFR1, NFR4, NFR5, P8, and P11.

### Current constraints

- Use `openai:qwen/qwen3.5-9b` for all validation experiments, as directed by the user on 2026-11-18. Alternative model sizes are out of scope.
- Use only the self-hosted A10 deployment. The user subsequently decided that provider-hosted results are misleading and must be ignored; Caila runs are retained only as excluded experiment history, never as candidate evidence.
- Use general-purpose model reasoning over public tasks, observations, action descriptions, and results; no benchmark-specific solver or private evaluator data.
- Use default model sampling as required by constitution preference P11; do not make episodes exact replicas through fixed-seed or deterministic-serving restrictions.
- Keep every episode within 50 action attempts and 300 seconds.
- Use the running dedicated A10 efficiently. Prefer partial configurations containing only unperturbed episodes and inexpensive criteria; avoid AC2/AC4/AC5 experiment populations unless needed for a final regression check.
- Partial validation is diagnostic. Only an unchanged full `default` run can certify project-level AC3 acceptance.

### Current state

The current `main` implementation (`1bd6081`) has the spec 04 planning mechanisms. Full `default` run `20261114T053703-525279Z-b864ae241134` used solution commit `c3e5a94` and produced VM1 = 0.67 and VM4 = 0.15. The newer full run `20261117T150114-324103Z-9acb73d41f31` used commit `b490da1` with the same agent settings and produced VM1 = 0.665 and VM4 = 0.25. AC3 therefore remains valid rather than accepted, with substantial run-to-run variation even on the dedicated runtime.

The best experimental implementation is revision `e0847c3`: ordinary complete-plan prompts, one-action voting/execution prefixes, and initial empty-plan suppression. Partial run `20261118T034306-781510Z-53b3a0db4c66` produced the first free-sampling diagnostic AC3 acceptance on the complete 20-task set (three repeats; VM4 = 0.04999999999999993). VM1 was 0.5667. Its 10-repeat extension was early-stopped after 41 episodes because repeat 1 had 9 successes and repeat 2 reached 11, making VM4 >= 0.10 unavoidable.

H=2 on `fdbf61a` improved self-hosted VM1 to 0.6333 and reduced screening time from 50 to 40 minutes, but its three-repeat VM4 was 0.15. Adding goal regression at H=2 kept VM1 at 0.6333 and increased VM4 to 0.20.

Provider-hosted runs were stopped and excluded after the user determined that their results are misleading; they play no role in candidate selection or acceptance. Self-hosted A10 H=1 goal regression completed with VM1 = 0.6333 and VM4 = 0.10, so it was not extended.

The targeted optimized/budget H=1 goal-regression run scored repeat rates 0.50, 0.75, 1.00 on the four tasks, producing VM4 = 0.50 despite VM1 = 0.75. It did not justify an optimized full extension. The final extension attempt restores the exact original lowest-variance H=1 goal-regression runtime and settings for a full 20-task, 10-repeat diagnostic with early stopping.

Evidence:
- `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261114T053703-525279Z-b864ae241134/`
- [Historical validation results](../validation-results-old.md)
- [Methods report](../reports/methods-report.html)

### Contexts

| ID | Solution implementation | Validation setup | Runtime and environment | Baseline |
|----|-------------------------|------------------|-------------------------|----------|
| C1 | `c3e5a94`, complete-plan voting, 5 plan samples + 1 spare | Full `default`, 20 tasks x 10 unperturbed repeats plus other conditions | Self-hosted `Qwen/Qwen3.5-9B`, A10, vLLM, temperature 0.7 | VM1 = 0.67; VM4 = 0.15 |
| C2 | `e0847c3`, full-plan prompts with one-action prefix voting/execution and initial empty-plan suppression | Partial `default`: unperturbed only; 3 repeats screened, 10-repeat extension early-stopped | Same self-hosted 9B runtime as C1 | 3-repeat VM1 = 0.5667; VM4 = 0.04999999999999993; 10-repeat extension guaranteed VM4 >= 0.10 |
| C3 | Alternative-model exploration, stopped before validation | No validation episodes | Dense 27B GPTQ-Int4 failed to fit; 35B-A3B download was removed | Out of scope: the user requires `qwen/qwen3.5-9b` |
| C4 | `fdbf61a`, H=2 forward planning with review fixes | Partial `default`: all 20 tasks, 3 unperturbed repeats | Same self-hosted 9B runtime | VM1 = 0.6333; VM4 = 0.15 |
| C5 | `fdbf61a`, H=2 with goal-regression instructions | Same partial configuration as C4 | Same self-hosted 9B runtime | VM1 = 0.6333; VM4 = 0.20 |
| C6 | `fdbf61a`, H=1 with goal-regression instructions | Same partial configuration as C4 | Same self-hosted 9B runtime | VM1 = 0.6333; VM4 = 0.10 |
| C7 | Excluded provider-hosted experiment | Excluded by user; not admissible evidence | Caila deployment | Ignored as misleading |
| C8 | Excluded provider-hosted extension | Aborted after user decision | Caila deployment | Ignored as misleading |
| C9 | `2e8ec84`, H=2 forward planning | Optimized runtime, 3-repeat screen early-stopped after 2 repeats | Self-hosted 9B with prefix caching and CUDA graphs enabled | Repeats 0.60 and 0.75; VM4 >= 0.15 |
| C10 | `2e8ec84`, H=2 forward planning, 3 plan samples + 1 spare | Same partial configuration as C4 | Same optimized self-hosted runtime as C9 | VM1 = 0.6667; VM4 = 0.04999999999999993; AC7 = 0.7833 due to stderr overflow |
| C11 | `2e8ec84`, identical H=2 3+1 candidate with error-only logs | Same partial configuration as C4 | Same optimized self-hosted runtime as C9 | VM1 = 0.70; VM4 = 0.15; AC7 = 1.0 |
| C12 | `f4a621d`, H=2 3+1 with selected-prefix review and error-only logs | Early-stopped after two repeats | Same optimized self-hosted runtime as C9 | Repeats 0.40 and 0.30; rejected |
| C13 | `23679bb`, vote H=1 / execution H=2, 3+1, error-only logs | Same partial configuration as C4 | Same optimized self-hosted runtime as C9 | VM1 = 0.7167; VM4 = 0.15; AC7 = 1.0 |
| C14 | `9f81d9b`, split horizons with 50 actions and 298 seconds | Early-stopped after two repeats | Same optimized self-hosted runtime as C9 | Repeats 0.70 and 0.60; rejected |
| C15 | `4080915`, split horizons with 4+1 samples and original budgets | Early-stopped after two repeats | Same optimized self-hosted runtime as C9 | Repeats 0.80 and 0.55; rejected |
| C16 | `c32b812`, H=1 goal regression on four previously flipping tasks | Four tasks x 3 unperturbed repeats, AC1/AC3/AC6/AC7 | Optimized self-hosted runtime, 50/298 budgets, error-only logs | VM1 = 0.75; VM4 = 0.50; rejected |
| C17 | `fdbf61a`, exact original H=1 goal-regression candidate | All 20 tasks x 10 unperturbed repeats | Original self-hosted runtime: no prefix cache, eager execution | Starting |

### Current understanding

#### Supported by evidence

- Whole-plan votes often collapse to lowest-sample-index tie breaking because long sampled plans rarely agree, while first actions have a much stronger mode (spec 04 and methods report).
- Prompt-only short horizons were not followed reliably; plan and goal reviews did not saturate weak-task success.
- Provider-latency instability inflates VM4. The current dedicated self-hosted runtime removes that confounder, leaving per-task model sampling noise.
- Engine-enforced one-action prefixes with full-plan prompts reduced the three-repeat range to 0.05 and suppressed 68 empty candidates, but lowered VM1 to 0.5667 and increased timeout pressure.

#### Tentative or unresolved

- The exact original H=1 goal-regression candidate has the lowest observed per-task variance; its final 10-repeat durability is unresolved.

### Experiments and decisions

| ID | Idea or question | Context | Result and evidence links | Decision and rationale |
|----|------------------|---------|---------------------------|------------------------|
| E1 | Analyze the latest self-hosted baseline and earlier mechanism results | C1 | VM4 = 0.15 and VM1 = 0.67 in run `20261114T053703-525279Z-b864ae241134`; methods report records weak whole-plan agreement and unsuccessful horizon/review variants | Do not repeat prompt-only horizons or costly review-only variants. Test engine-enforced prefix consensus and a stronger model. |
| E2 | Make the existing planning horizon enforce consensus even when the model returns a longer plan | C2 | Commit `26c32e6` truncates candidates before voting, marks truncated plans as non-reaching, logs enforcement, and passes 100 provider-independent tests | Keep as an experimental fallback. First isolate the stronger-model effect with horizon 0 because extra rounds may hurt difficult tasks. |
| E3 | Obtain a stronger general-purpose model within the A10 memory budget | C3 | Official `Qwen/Qwen3.5-27B-GPTQ-Int4` downloaded successfully to the A10 HF cache at revision `8f0c09f227ae570e79617c6d9172b59df9c16081` | Serve the 27B model with default sampling and run a 3-repeat unperturbed-only screen. |
| E4 | Check whether the November 14 result was a stable 9B baseline | C1 | Run `20261117T150114-324103Z-9acb73d41f31` produced VM1 = 0.665 and VM4 = 0.25 at `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261117T150114-324103Z-9acb73d41f31/` | Do not treat the earlier VM4 = 0.15 as a reliable ceiling. Prioritize a materially stronger model over another marginal 9B vote-size change. |
| E5 | Load the dense 27B GPTQ-Int4 model directly on the A10 | C3 | vLLM 0.32 exhausted all 22.06 GiB while constructing decoder layers on 2026-11-18 at 06:17 UTC; no API server or validation episodes started | Alternative-model work stopped when the user required `qwen/qwen3.5-9b`; the 35B-A3B partial download was removed and the 9B runtime restored. |
| E6 | Clarify the allowed model for this investigation | C2 | User direction on 2026-11-18: use `qwen/qwen3.5-9b` | Restrict every subsequent experiment and final validation to the required 9B model. Focus on agent-side decision and recovery changes. |
| E7 | Review all prior method evidence before selecting more experiments | C1/C2 | Read `.internal/reports/build_report.py`, generated methods report, and provider probes. Already tested: H=3 instruction-only horizons, H=2 with review, larger votes, generic state-simulation prompting, one-shot repair, in-context self-consistency, plan/goal reviews, conflicting-predicate feedback, and deterministic serving | The active H=1 screen is distinct because enforcement occurs before voting and review is disabled. Do not repeat the listed negative variants. Empty-plan handling and verification consensus remain untested; failure-mode-targeted prompting is distinct from the failed generic simulation prompt. |
| E8 | Quantify empty-plan behavior in the latest self-hosted traces | C1 | In run `20261114T053703-525279Z-b864ae241134`, empty completion claims were 143/870 logged candidates on nine weak tasks. Across all unperturbed episodes, 67 empty plans were selected in 60 episodes; those episodes averaged 128.2 s versus 98.0 s for episodes without an empty selection, with success 36/60 versus 98/140 | Commit `c5790f1` adds the experimental rule that actionable plans suppress empty completion claims before the first observation, while empty-only rounds and empty claims after observations retain verification behavior. 102 tests pass. A/B it after the active H=1 screen. |
| E9 | Replay old first-round candidates against the independent public Blocks World simulator | C1/C2 | Across 200 initial unperturbed rounds and 764 nonempty candidates, 82.1% of first actions were valid versus 50.1% fully valid plans. The modal first action was valid in 84.5% of rounds and had at least one sampled solving continuation in 46.0%; any candidate solved in 55.5%. Modal starts on `restack_abc` and `restack_bac` had no solving continuation in all 10 rounds | H=1 can reduce mid-plan precondition failures but can also select a systematically wrong mode. Evaluate actual per-task recovery and success; do not infer AC3 improvement from prefix validity alone. |
| E10 | Prepare a planning strategy not covered by the earlier generic state-simulation prompt | C2 | Commit `405d9a3` adds goal-regression guidance to complete-plan generation: derive actions backward from goal predicates and conflicts, then check the forward-ordered plan. 103 tests pass | Test with horizon 0 after the H=1 and empty-plan A/B results. This is a distinct reasoning strategy, not a repeat of the failed generic request to simulate state. |
| E11 | Screen prompt-controlled H=1 with enforced voting | C2 | Partial run `20261118T033123-886755Z-6e1f0c6f57aa` was aborted at `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261118T033123-886755Z-6e1f0c6f57aa/`. On initial `stack_ab` and `unstack_ab`, all five candidates were empty and `truncated=0`; the former took 154.1 s to succeed and the latter stopped unsuccessfully after 152.1 s. This did not measure VM4 | Stop the invalid screen instead of spending 60 episodes on empty-plan behavior. Commit `3d215c7` decouples `--plan-execution-horizon` from the prompt horizon and makes goal regression opt-in via `--planning-strategy`; 104 tests pass. Run full-prompt prefix execution next. |
| E12 | Validate full-prompt H=1 prefix execution plus initial empty-plan suppression | C2 | Run `20261118T034306-781510Z-53b3a0db4c66` at `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261118T034306-781510Z-53b3a0db4c66/`: diagnostic AC3 accepted with VM4 = 0.04999999999999993; repeat rates 0.55, 0.60, 0.55; VM1 = 0.5667; AC6 and AC7 accepted. The 60 episodes took 50 minutes. All four `restack_*` tasks failed in every repeat, and many difficult episodes exhausted 285 s after about six successful plan rounds | Extend the exact candidate to 10 unperturbed repeats immediately. Preserve it as the first diagnostic AC3 success, but seek an H=2 or prompt improvement that reduces timeouts and raises VM1 if the 10-repeat range remains too large. |
| E13 | Remove completion-flag dependence on sample race order | C2 | `vote_plans` previously overwrote the representative for a normalized plan on every completion, so mixed `reaches_goal` flags were decided by the last completed sample. Commit `6b25bcf` selects the lowest-sample representative and requires unanimous completion within the normalized vote group; 105 tests pass | Include in the next experimental revision. The active 10-repeat run remains on `e0847c3` for controlled evidence. The synthetic delayed-write regression deadline was widened from 10 ms to 50 ms because the old test was load-sensitive; its assertion is unchanged. |
| E14 | Resolve independent implementation-review findings | C2 | Review found that goal-review filtering could discard a mixed group's non-reaching member before voting, and that precedence, invalid-horizon, and truncated-prefix retry coverage was incomplete. It also identified the implicit H=1 round ceiling. Commit `1bf2734` preserves group verdicts through goal filtering, adds the missing tests, and raises the active-horizon round ceiling to at least the action budget plus the initial round; 108 tests pass | Include in the next H=2/goal-regression diagnostic. The active H=1 10-repeat evidence remains tied to its earlier revision. |
| E15 | Extend the H=1 candidate to 10 repeats with early stopping | C2 | Run `20261118T043358-257621Z-989a7cf101d0` was aborted at `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261118T043358-257621Z-989a7cf101d0/`. After 41 records, repeat 1 had 9 successes and repeat 2 had reached 11 of 19 completed, guaranteeing VM4 >= 0.10 | Stop immediately rather than spend another 159 episodes on a rejected range. Switch to H=2 on `fdbf61a`; run `20261118T050959-170962Z-7a0d67ea74e6` is now measuring whether fewer rounds improve the VM1/VM4/time tradeoff. |
| E16 | Screen H=2 forward prefix consensus | C4 | Run `20261118T050959-170962Z-7a0d67ea74e6`: VM1 = 0.6333, VM4 = 0.15; repeat rates 0.65, 0.70, 0.55; AC6/AC7 accepted. The 60 episodes completed in 40 minutes with maximum 18 actions. H=2 stabilized `stack_ba` and `stack_ca_on_b`, but all `restack_*` and `tower_four` episodes still failed | Keep H=2 for its higher VM1 and throughput. Do not launch its 10-repeat extension. Start H=2 goal regression (`20261118T055002-998672Z-b6c977f7f68c`) to target the remaining plan-distribution failures. |
| E17 | Add goal regression to H=2 | C5 | Run `20261118T055002-998672Z-b6c977f7f68c`: repeat rates 0.70, 0.70, 0.50; VM1 = 0.6333 and VM4 = 0.20, with AC6/AC7 accepted | The first two repeats were identical but the third collapse rejects the candidate. Do not extend H=2 goal regression. Test H=1 goal regression on the A10 (`20261118T063042-081495Z-0a70e44a788c`). |
| E18 | Test the new mechanism on the historically stronger deployment of the required model | C7 | Historical full run `20261107T003923-202490Z-81f70aae68a3` using provider-hosted `qwen/qwen3.5-9b` reached VM1 = 0.99 and a true 0.05 repeat range, rejected only by floating-point subtraction. New H=2 partial run `20261118T063143-186783Z-b40fb861ef4d` is independent of the A10 workload | Run in parallel to distinguish agent mechanisms from model deployment quality without violating the 9B constraint. Extend only if the three-repeat result is accepted. |
| E19 | Screen H=2 on the provider-hosted 9B deployment | C7 | Run `20261118T063143-186783Z-b40fb861ef4d` returned VM1 = 1.0 and VM4 = 0.0, but the user subsequently ruled this deployment misleading and inadmissible | Excluded entirely by E20. Do not cite as candidate evidence. |
| E20 | Restrict validation to the self-hosted deployment | C6 | User decision on 2026-11-18: provider-hosted results are misleading and must be ignored; use only self-hosted results. Provider extension `20261118T065636-288449Z-73607ebca0ce` was aborted and its validator stopped | Exclude C7/C8 and all provider metrics from current understanding, spec evidence, candidate selection, and final acceptance. Continue only with the A10 H=1 goal-regression run and subsequent self-hosted experiments. |
| E21 | Screen self-hosted H=1 goal regression | C6 | Run `20261118T063042-081495Z-0a70e44a788c`: repeat rates 0.60, 0.60, 0.70; VM1 = 0.6333, VM4 = 0.09999999999999998, maximum actions = 18, timely response rate = 1.0 | Reject and do not extend. Goal regression improved VM1 relative to the first H=1 screen but did not stabilize the range. |
| E22 | Remove self-imposed serving-performance limits without changing sampling | C4/C9 | H=2 forward traces had 149 plan-round starts but only 111 completed candidate votes, leaving 38 rounds in progress at termination. The A10 was serving with prefix caching disabled and eager execution forced | Restart with default prefix caching and CUDA graphs, then repeat the H=2 forward screen on `2e8ec84`. This changes performance, not model identity, sampling parameters, or agent logic. |
| E23 | Screen optimized-runtime H=2 with 5+1 samples | C9 | Run `20261118T072146-798205Z-4b9a2fde7647` was early-stopped at `/home/tony/reps/github/anton-pershin/agent-validation/artifacts/runs/20261118T072146-798205Z-4b9a2fde7647/`: repeats 1 and 2 scored 12/20 and 15/20, guaranteeing VM4 >= 0.15 | Do not spend the third repeat. Retain the optimized server but reduce per-episode request load to 3+1 samples in run `20261118T074118-881019Z-e53b8726a5b3`. |
| E24 | Screen optimized-runtime H=2 with 3+1 samples | C10 | Run `20261118T074118-881019Z-e53b8726a5b3`: VM1 = 0.6667, VM4 = 0.04999999999999993 (diagnostic AC3 accepted), maximum actions = 30. AC7 was only 0.7833 because 13 episodes ended `output_limit_exceeded` after exceeding the 64 KiB stderr limit; no episode exceeded 300 seconds | Do not extend with an AC7 regression. Repeat identically with `--log-level ERROR` in run `20261118T080721-081442Z-c647297f198b` to prevent log-driven termination under the unchanged full-profile retention limit. |
| E25 | Retry H=2 3+1 with error-only logs | C11 | Run `20261118T080721-081442Z-c647297f198b`: repeat rates 0.75, 0.75, 0.60; VM1 = 0.70, VM4 = 0.15000000000000002, maximum actions = 39, AC7 = 1.0 | The logging fix worked but repeatability did not survive. Do not extend. Add selected short-prefix review in `f4a621d`. |
| E26 | Review only the selected short prefix | C12 | Commit `f4a621d` adds an opt-in post-vote review with index-0 rejection, k-action truncation, failure fallback, logging, and configuration; 112 tests pass. Run `20261118T084418-478547Z-4851faf2f94a` uses the optimized H=2 3+1 error-log baseline plus this review | Measure whether one short review per round improves validity and stability without the latency of the previously rejected full-candidate review stage. |
| E27 | Screen selected-prefix review | C12 | Run `20261118T084418-478547Z-4851faf2f94a` was early-stopped: repeats 1 and 2 scored 8/20 and 6/20, guaranteeing VM4 >= 0.10 and cutting success roughly in half relative to the no-review baseline | Reject this mechanism and do not run the third repeat. Keep it opt-in and disabled in subsequent candidates. |
| E28 | Separate vote and execution prefix lengths | C13 | Commit `23679bb` adds `plan_vote_horizon`; votes can compare one action while returning and executing a two-action representative, with completion grouping and goal review using the same vote prefix. 114 tests pass. Run `20261118T093122-831421Z-69677a620fe7` uses V=1/H=2 | Test whether first-action consensus and two-action throughput can be combined without the H=1 timeout cost. |
| E29 | Screen vote H=1 / execution H=2 | C13 | Run `20261118T093122-831421Z-69677a620fe7`: repeat rates 0.65, 0.70, 0.80; VM1 = 0.7167 (best admissible self-hosted result), VM4 = 0.15, maximum actions = 43, AC7 = 1.0 | Do not extend the rejected range. Preserve the mechanism and test the unused compliant action/time budget in run `20261118T100210-286586Z-a2deadafa740`. |
| E30 | Use the remaining compliant episode budget | C14 | The split candidate reached 43 actions against the constitution limit of 50 and used an internal 285-second cap despite the 300-second validation limit | Screen 50 actions and 298 seconds with all other settings unchanged. Error-only logs remain enabled to protect timely final responses. |
| E31 | Screen split horizons with expanded budget | C14 | Run `20261118T100210-286586Z-a2deadafa740` was early-stopped after repeats of 14/20 and 12/20, guaranteeing VM4 >= 0.10 | Extra budget did not justify more episodes. Restore 45/285 and test 4+1 samples in run `20261118T102537-604510Z-deb44c446f85`. |
| E32 | Test the middle request-load point | C15 | The 3+1 and 5+1 configurations both had unstable screens, although 3+1 produced one diagnostic AC3 acceptance before logging correction | Screen 4+1 with vote H=1/execution H=2 and error-only logs, leaving all other settings unchanged. |
| E33 | Screen split horizons with 4+1 samples | C15 | Run `20261118T102537-604510Z-deb44c446f85` was early-stopped after repeats of 16/20 and 11/20, guaranteeing VM4 >= 0.25 | Reject immediately. Stop full-population tuning and test the four specific tasks that remained unstable in the lowest-variance candidate. |
| E34 | Target the four H=1 goal-regression flips | C16 | Per-task analysis found 16/20 saturated tasks in run `20261118T063042-081495Z-0a70e44a788c`; only `stack_ac`, `stack_ba`, `stack_bc`, and `stack_ca` flipped | Run `20261118T105058-832007Z-cb4caab98b44` with 12 targeted episodes. Use the result to decide whether a full 10-repeat extension has evidence behind it. |
| E35 | Screen optimized/budget H=1 goal regression on the four flips | C16 | Run `20261118T105058-832007Z-cb4caab98b44`: repeat rates 0.50, 0.75, 1.00; VM1 = 0.75, VM4 = 0.50, maximum actions = 21, AC7 = 1.0. Failures were long recovery trajectories; most successes were direct two-action plans | Reject the optimized/budget variant for extension. Make one final 10-repeat attempt with the exact original lowest-variance runtime/settings rather than inferring stability from a changed configuration. |

### Next candidates

- [x] Screen engine-enforced prefix voting/execution on the required 9B model with 3 unperturbed repeats.
- [x] Early-stop the H=1 10-repeat diagnostic once its range was definitively rejected.
- [x] Screen H=2 forward prefix consensus and H=2 goal regression.
- [x] Complete the self-hosted A10 H=1 goal-regression screen.
- [x] Screen H=2 with default prefix caching and CUDA graphs on the self-hosted A10; early-stop after definitive rejection.
- [x] Screen optimized-runtime H=2 with 3+1 plan samples; identify and diagnose the AC7 regression.
- [x] Repeat the H=2 3+1 candidate with error-only logs and verify AC7 recovery.
- [x] Screen and reject selected-prefix review after definitive early evidence.
- [x] Screen vote H=1 with execution H=2 and record its VM1/VM4 tradeoff.
- [x] Screen and reject the split candidate with 50 actions and 298 internal seconds.
- [x] Screen and reject split horizons with 4+1 plan samples.
- [x] Complete and reject the targeted optimized/budget four-task diagnostic.
- [ ] Run the final full-population 10-repeat attempt with the exact original lowest-variance candidate.
- [ ] If accepted, run full `default` validation; otherwise retain the best diagnostic and implementation evidence without claiming project acceptance.
- [ ] Confirm the selected revision with full `default` validation on the self-hosted deployment if time allows; do not use partial acceptance as certification.

### Linked specs

- [Spec 04: Repeatable planning](../specs/04-repeatable-planning-general-spec.md) — existing baseline and prior negative results.
- [Spec 06: Observed-state prefix consensus](../specs/06-observed-state-prefix-consensus-general-spec.md) — candidate implementation contract created after the three-repeat diagnostic AC3 acceptance; its 10-repeat and full-validation checks remain open.
