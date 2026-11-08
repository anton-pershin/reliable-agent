## Terminology

### General

| Term | Definition |
|------|------------|
| Task | An objective supplied to the agent, together with instructions and available information. |
| Episode | One attempt by the agent to complete a task, from task receipt to its final response or termination. |
| Completion declaration | An explicit statement by the agent that it has completed the task. It does not establish that the task was successful. |
| Task success | Satisfaction of the task's correctness conditions, determined independently of the agent's claim of completion. |
| Task success rate | For one fixed task and one evaluation condition, `N_success / N`, where `N` is the number of planned repeated episodes for that task and condition, and `N_success` is the number of those episodes that succeed. Unsuccessful attempts, including crashes and timeouts, remain in the denominator; episodes from different tasks are not combined. |
| Overall success rate | For one evaluation condition, the arithmetic mean of the task success rates across the benchmark task set. Each task has equal weight, regardless of its episode count. |
| Unperturbed evaluation conditions | The original task inputs and prompts, with the configured model and execution settings and without deliberately injected failures. |
| Evaluation run | Execution of a specified set of task episodes under a specified evaluation configuration. |
| Consistency | Stability of overall success rates across repeated evaluation runs under unchanged conditions. |
| Prompt robustness | Limited loss and range of overall success rates across the original prompt and meaning-preserving prompt variants. |
| Resilience | Limited loss and range of overall success rates across unperturbed execution and transient tool or environment failure scenarios. |
| Error awareness | The agent's ability to identify its own unsuccessful results, assessed against independently determined task outcomes. |
| Confidence | The agent's reported degree of belief that its answer is correct. It is not an independently verified probability. |
| Likely incorrect flag | The agent's boolean assessment, returned as `likely_incorrect`, that its answer is likely incorrect. |
| Action attempt | One requested operation in an execution environment, including an action-catalog request, a failed or rejected action, or a repeated action. Each action in a batch is one action attempt. |
| End-to-end time | Elapsed time from task receipt to the final response, including self-assessment. |

### Integration interfaces

| Term | Definition |
|------|------------|
| Calling system | An external system that requests decisions or complete task execution from the agent. |
| Interaction bridge | A component that translates between the calling system's interaction format and the decision engine's contracts. |
| Task runner | A component that controls complete task execution by requesting decisions and executing actions until completion or termination. |
| Interaction protocol | The rules and formats for exchanging tasks, observations, action requests, and responses. |

### Agent decision logic

| Term | Definition |
|------|------------|
| Stateful decision engine | The reusable component that maintains task state and produces the next action, response, or completion declaration with self-assessment. |
| Task state | Information retained by the agent across interactions within an episode. |
| Observation | Information supplied to the agent by the calling system or execution environment. |
| Self-assessment | The answer's confidence, likely incorrect flag, and short reason supplied by the agent before private evaluation results are revealed. |
| Action decision | A structured model output containing a nonempty list of action requests for the runner. |
| Final decision | A structured model output containing the completion declaration, answer, confidence, `likely_incorrect` flag, and short reason. |
| Final-response reserve | Time reserved at the end of the episode budget for a controlled final response without another model request. |
| Candidate plan | An ordered list of action requests proposed by the model to satisfy the task objective from the current task state. |
| Plan vote | Deterministic selection of one candidate plan from several model samples by a majority rule over normalized action sequences. |
| Completion verification | A dedicated model request that checks the task goal against the latest public observations before a completion declaration. |
| Re-planning | A request for a new candidate plan from the current task state after an action failure, plan exhaustion, or a rejected completion verification. |
| Reactive fallback | The switch from plan-based decisions to per-step decisions for the rest of an episode, used when no valid candidate plan is available. |
| Reactive mode | The episode state after a reactive fallback: the engine asks the model for the next decision after every observation instead of executing a selected plan. |

### Model and tool access

| Term | Definition |
|------|------------|
| Model client | The component that provides configurable access to model providers through Pydantic AI. |
| Model provider | An external service or system that performs model inference. |
| Tool | An operation exposed to the agent through a description and an execution interface. |
| Tool execution interface | The component that connects requested actions to an execution environment and returns observations or failures. |
| Execution environment | The external system in which requested operations are performed. |
| Tool binding | Configuration that connects a tool exposed to the agent to its execution mechanism. |
