## Terminology

### General

| Term | Definition |
|------|------------|
| Task | An objective supplied to the agent, together with instructions and available information. |
| Episode | One attempt by the agent to complete a task, from task receipt to its final response or termination. |
| Completion declaration | An explicit statement by the agent that it has completed the task. It does not establish that the task was successful. |
| Task success | Satisfaction of the task's correctness conditions, determined independently of the agent's claim of completion. |
| Task success rate | The proportion of evaluated task episodes that are successful. |
| Baseline evaluation conditions | The reference task inputs, prompts, model configuration, and execution conditions used for comparison. |
| Evaluation run | Execution of a specified set of task episodes under a specified evaluation configuration. |
| Consistency | Stability of task success rates across repeated evaluation runs under unchanged conditions. |
| Prompt robustness | Stability of task success rates when prompts change without changes to their intended meaning. |
| Resilience | Preservation of task success rates despite transient tool or environment failures. |
| Error awareness | The agent's ability to identify its own unsuccessful results, assessed against independently determined task outcomes. |
| Confidence | The agent's reported degree of belief that its answer is correct. It is not an independently verified probability. |
| Likely incorrect flag | The agent's boolean assessment, returned as `likely_incorrect`, that its answer is likely incorrect. |
| Action attempt | An attempt to perform an operation in an execution environment, including an attempt that fails or repeats an earlier operation. |
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

### Model and tool access

| Term | Definition |
|------|------------|
| Model client | The component that provides configurable access to model providers through Pydantic AI. |
| Model provider | An external service or system that performs model inference. |
| Tool | An operation exposed to the agent through a description and an execution interface. |
| Tool execution interface | The component that connects requested actions to an execution environment and returns observations or failures. |
| Execution environment | The external system in which requested operations are performed. |
| Tool binding | Configuration that connects a tool exposed to the agent to its execution mechanism. |
