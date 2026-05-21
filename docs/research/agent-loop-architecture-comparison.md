# Agent Loop Architecture Comparison

Research into how five popular open-source agent harnesses structure their agent loops.

---

## 1. OpenHands (formerly OpenDevin)

**Stack**: Python, async  
**Repo**: `github.com/OpenHands/OpenHands`  
**Core path**: `openhands/controller/` (moved to separate SDK repo: `github.com/OpenHands/software-agent-sdk`)

### Architecture

OpenHands uses a **controller-agent** pattern with a clean separation between orchestration and agent logic.

**Key naming:**
- `AgentController` — the main orchestrator (state machine)
- `Agent` (abstract) — pluggable agent strategies (CodeActAgent, BrowsingAgent, etc.)
- `Action` — outputs from the agent (e.g., `CmdRunAction`, `FileEditAction`, `BrowseURLAction`)
- `Observation` — results from the environment (e.g., `CmdOutputObservation`, `FileReadObservation`)
- `State` / `StatePlan` — conversation state snapshots

**Call chain:**
```
AgentController.step()
  → agent.step(state) → Action
  → runtime.execute(Action) → Observation
  → state.update(Observation)
  → loop back if not FINISHED
```

### Loop structure

The `AgentController` manages the main loop. It is **event-driven** — the controller receives user messages, calls `agent.step(state)`, gets back an `Action`, dispatches it to a `Runtime` (Docker sandbox, local process, etc.), receives an `Observation`, and appends it to the `State`.

The controller tracks:
- Max iterations (configurable)
- Budget (token/cost limits)
- User confirmation gates for dangerous actions

### Tool dispatch

Tools are **not** dispatched as function calls to the LLM. Instead:
1. The LLM outputs structured `Action` objects (via prompt engineering or tool calling)
2. The controller validates and routes the action to the appropriate `Runtime` method
3. Each `Action` type maps to a runtime method: `run_command()`, `edit_file()`, `browse()`, etc.

The `Action` types form a **discriminated union**: `CmdRunAction`, `FileEditAction`, `FileReadAction`, `BrowseURLAction`, `MessageAction`, etc.

### Sub-agents

OpenHands supports sub-agents via **delegation**. A `CodeActAgent` can delegate to a `BrowsingAgent` by emitting a `DelegateAction`. The controller spawns the sub-agent, runs it in a nested loop, and returns the result.

### Separation of concerns

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| Orchestration | `AgentController` | Loop control, state management, action dispatch |
| Agent logic | `Agent` subclasses | LLM interaction, prompt construction, action selection |
| Execution | `Runtime` | Execute actions (bash, file ops, browser) |
| State | `State` / `Event` | Message history, conversation metadata |

---

## 2. Aider

**Stack**: Python, synchronous  
**Repo**: `github.com/Aider-AI/aider`  
**Core path**: `aider/coders/base_coder.py` (~2000 LOC)

### Architecture

Aider is the **simplest** architecture here — a single `Coder` class that owns the entire loop. No separate controller, no action/observation types. The LLM output is parsed as text (not structured function calls).

**Key naming:**
- `Coder` (base class) — the entire agent loop
- `EditBlockCoder`, `WholeFileCoder`, `ArchitectCoder` — edit format strategies
- `Commands` — user-facing slash commands
- `ChatSummary` — context window management via summarization
- `RepoMap` — repository-level context (tree-sitter based)

**Call chain:**
```
Coder.run()
  → Coder.get_input() → user_message
  → Coder.run_one(user_message)
    → Coder.send_message(inp)
      → Coder.format_messages() → ChatChunks
      → litellm.completion() → streamed response
      → Coder.send() → yields chunks
      → (edit parsing happens in subclass .get_edits())
    → Coder.reflected_message loop (up to max_reflections=3)
  → auto_lint, auto_test, auto_commit
```

### Loop structure

Aider has a **two-level loop**:
1. **Outer loop** (`run()`): reads user input, processes commands, calls `run_one()`
2. **Inner loop** (`run_one()`): sends message to LLM, applies edits, then enters a **reflection loop** — if lint/test fails or the edit was malformed, it feeds the error back to the LLM (up to 3 reflections)

The `send_message()` method is a **generator** that yields streamed response chunks. It handles retry logic for LLM API errors (exponential backoff).

### Tool dispatch

Aider has **no tool dispatch** in the traditional sense. The LLM outputs text containing edit blocks (e.g., `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`), which are parsed by the `EditBlockCoder` subclass.

- `EditBlockCoder.get_edits()` — parses SEARCH/REPLACE blocks from LLM output
- `EditBlockCoder.apply_edits()` — applies edits to files, with fuzzy matching
- Shell commands are detected as ````bash` blocks and offered for execution

### Sub-agents

Aider has a **dual-model sub-agent** pattern via `ArchitectCoder`:
1. **Architect model** — plans changes (which files, what to do)
2. **Editor model** — executes edits (a separate `Coder` instance with a different model)

This is implemented via `Coder.create(from_coder=self)` which clones the conversation state and switches the model/edit format.

### Separation of concerns

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| Loop + orchestration | `Coder` | Everything — loop, LLM calls, editing, git |
| Edit parsing | Subclass `.get_edits()` | Parse LLM output into file edits |
| Edit application | Subclass `.apply_edits()` | Apply edits to filesystem |
| Context management | `RepoMap`, `ChatSummary` | Repository context, history compaction |
| User interaction | `InputOutput` | Terminal I/O, user prompts |

---

## 3. Goose (by Block)

**Stack**: Rust, async (Tokio)  
**Repo**: `github.com/block/goose`  
**Core path**: `crates/goose/src/agents/`

### Architecture

Goose has the **most modular** architecture. It's built around an `Agent` struct with explicit separation between tool routing, permission checking, and extension management.

**Key naming:**
- `Agent` — the main struct (owns provider, extensions, permissions)
- `AgentEvent` — streamed events (`Message`, `McpNotification`, `HistoryReplaced`)
- `ExtensionManager` — manages MCP-based tool providers
- `ToolCallContext` — context for a single tool dispatch
- `ToolCallResult` — async result + notification stream
- `ToolConfirmationRouter` — routes user confirmations for tool calls
- `ToolInspectionManager` — chains inspectors (security, permission, repetition)
- `PromptManager` — system prompt construction
- `RetryManager` — retry logic for failed tool calls
- `SubagentRunParams` / `run_subagent_task()` — sub-agent execution

**Call chain:**
```
Agent.reply(user_message, session_config, cancel_token)
  → prepare_reply_context() → ReplyContext (conversation, tools, system_prompt)
  → loop (max_turns):
    → provider.complete(messages, tools) → Message with tool_calls
    → categorize_tools() → frontend vs backend tool requests
    → tool_inspection_manager.inspect() → inspection results
    → handle_approved_and_denied_tools() → dispatch approved tools
    → handle_approval_tool_requests() → stream user confirmations
    → dispatch_tool_call() → ExtensionManager.dispatch_tool_call()
    → collect tool results → append to conversation
    → check if compaction needed → compact_messages()
  → yield AgentEvent::Message for each step
```

### Loop structure

The `reply()` method returns a `BoxStream<'_, Result<AgentEvent>>` — an async stream of events. The loop runs inside this stream:

1. Build system prompt + tools
2. Call LLM provider
3. Parse tool calls from response
4. Route each tool call through:
   - Hook system (pre-tool hooks can deny)
   - Security inspector (adversary detection)
   - Permission inspector (user approval)
   - Extension manager (actual execution)
5. Append results to conversation
6. Check for compaction (context window management)
7. Loop until max_turns or final output

### Tool dispatch

Goose uses **MCP (Model Context Protocol)** as its tool layer:
- Tools come from `ExtensionManager` which manages MCP server connections
- Each extension is a separate process (stdio MCP server)
- Tool names are prefixed: `developer__shell`, `developer__read_file`, etc.
- `dispatch_tool_call()` routes by name prefix to the correct MCP client
- Frontend tools are handled separately (browser-side execution)

**Permission model:**
```
ToolCall → HookManager (deny?) → SecurityInspector → EgressInspector → AdversaryInspector → PermissionInspector → Execute
```

### Sub-agents

Goose has explicit sub-agent support via `subagent_handler.rs`:
- `run_subagent_task(params: SubagentRunParams)` — spawns a new `Agent` with scoped config
- Sub-agents get their own: provider, extensions, system prompt, session
- The parent receives results via `on_message` callback
- Sub-agents have a `max_turns` budget
- A `FinalOutputTool` enforces structured output from the sub-agent
- Results are extracted from the final message or `final_output_tool`

### Separation of concerns

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| Orchestration | `Agent.reply()` | Main loop, stream events |
| LLM interaction | `Provider` trait | Model API calls |
| Tool registry | `ExtensionManager` | MCP server management |
| Tool dispatch | `Agent.dispatch_tool_call()` | Route to MCP client |
| Permission | `ToolInspectionManager` + `ToolConfirmationRouter` | Security, approval flow |
| Context | `PromptManager`, `compact_messages()` | System prompt, context window |
| Sub-agents | `subagent_handler` | Nested agent execution |

---

## 4. SWE-Agent

**Stack**: Python, async  
**Repo**: `github.com/SWE-agent/SWE-agent`  
**Core path**: `sweagent/agent/agents.py`

### Architecture

SWE-Agent has a **config-driven** architecture with a clean agent-environment interface. Agents are defined by YAML configs that specify templates, tools, and models.

**Key naming:**
- `AbstractAgent` — base class
- `DefaultAgent` — standard action/observation loop
- `RetryAgent` — meta-agent that runs multiple attempts with review
- `ToolHandler` — tool parsing and execution
- `SWEEnv` — environment abstraction (bash shell via SWE-ReX)
- `StepOutput` — single step result (thought, action, observation, done)
- `HistoryProcessor` — message history transformers
- `TemplateConfig` — Jinja2-based prompt templates
- `AbstractAgentHook` — lifecycle hooks

**Call chain:**
```
DefaultAgent.run(env, problem_statement)
  → setup() → install tools, format templates, add demonstrations
  → loop:
    → forward_with_handling(history)
      → forward(history)
        → model.query(history) → output
        → tools.parse_actions(output) → (thought, action)
        → handle_action(step) → env.communicate(action) → observation
        → handle_submission(step) → check for submit command
      → (error handling with requery up to max_requeries)
    → add_step_to_history(step)
    → save_trajectory()
  → return AgentRunResult
```

### Loop structure

The `DefaultAgent` has a **three-level error handling loop**:
1. **Main loop** (`run()`): `while not step_output.done`
2. **Forward with handling** (`forward_with_handling()`): catches format errors, blocked actions, bash syntax errors — requeries the model with error templates (up to `max_requeries=3`)
3. **Forward** (`forward()`): the actual LLM call + action execution

Error recovery is sophisticated:
- `FormatError` → requery with format error template
- `_BlockedActionError` → requery with blocklist error template
- `BashIncorrectSyntaxError` → requery with shell check template
- `CommandTimeoutError` → autosubmit or retry
- `ContextWindowExceededError` → autosubmit

### Tool dispatch

SWE-Agent uses a **text-based command interface** (not function calling):
- The LLM outputs text containing bash commands
- `ToolHandler` parses the output to extract the action
- Actions are executed via `SWEEnv.communicate()` which sends commands to a bash shell
- `ToolHandler` also manages: command blocklists, multiline input handling, state tracking (git diff, file listing)

The `parse_function` determines parsing strategy:
- `ThoughtActionParser` — separates thought from action
- `ActionOnlyParser` — action-only (for human mode)

### Sub-agents

SWE-Agent has a **retry agent** (`RetryAgent`) which is a meta-agent:
- Runs `DefaultAgent` instances in sequence
- After each attempt, a **reviewer** (separate LLM call) evaluates the submission
- `ScoreRetryLoop` — scores each attempt, retries if score is low
- `ChooserRetryLoop` — uses a chooser model to pick the best attempt
- Environment is hard-reset between attempts
- Budget is tracked across attempts

This is **not** a nested concurrent sub-agent, but a **sequential retry with review**.

### Separation of concerns

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| Orchestration | `DefaultAgent.run()` | Main loop, trajectory tracking |
| LLM interaction | `AbstractModel` subclasses | Model API calls |
| Action parsing | `ToolHandler` + parsers | Extract actions from LLM output |
| Execution | `SWEEnv` | Bash command execution |
| Error handling | `forward_with_handling()` | Requery on format errors |
| Review | `RetryAgent` + `RetryLoop` | Multi-attempt with scoring |
| History | `HistoryProcessor` chain | Message filtering/transformation |

---

## 5. Pydantic AI

**Stack**: Python, async  
**Repo**: `github.com/pydantic/pydantic-ai`  
**Core path**: `pydantic_ai_slim/pydantic_ai/`

### Architecture

Pydantic AI takes a fundamentally different approach — it's a **type-safe agent framework** built on Pydantic models. The agent loop is driven by a graph-based execution engine.

**Key naming:**
- `Agent` — the user-facing class (generic over deps type and result type)
- `_agent_graph.py` (105KB!) — the core graph execution engine
- `_output.py` — output processing and tool call handling
- `_parts_manager.py` — message parts management
- `RunContext` — execution context (deps, model, messages)
- `ToolDefinition` / `ToolPrepareFunc` — tool registration
- `messages.py` — structured message types (ModelRequest, ModelResponse, ToolCallPart, etc.)
- `result.py` — result types (RunResult, StreamedRunResult)
- `Graph` / `Node` / `End` — graph execution primitives

**Call chain:**
```
Agent.run(user_prompt, deps)
  → _agent_graph.run_graph()
    → build initial graph state (messages, tools, system prompts)
    → loop:
      → model.request(messages, tools) → ModelResponse
      → process_response(response):
        → if tool_calls: execute tools → append results → loop
        → if final output: validate against result_type → End
    → return RunResult
```

### Loop structure

The graph engine in `_agent_graph.py` is a **general-purpose state machine**:
1. Build the initial state: system prompts, message history, tool definitions
2. Call the model
3. Process the response:
   - If the response contains **tool calls**: execute each tool, append results as tool responses, loop
   - If the response contains a **final output**: validate it against the declared result type, end
4. The loop continues until a valid final output is produced or max turns is hit

The `Agent` class is generic: `Agent[D, R]` where `D` is the dependency type and `R` is the result type. Tools are registered as decorated functions with type-annotated parameters.

### Tool dispatch

Pydantic AI uses **function-calling tool dispatch** with type safety:
- Tools are registered via `@agent.tool` or `@agent.tool_plain` decorators
- Function signatures are introspected to generate JSON schemas
- The LLM calls tools by name; the framework validates arguments against the function signature
- Tool results are serialized and appended to the conversation

Key difference from others: **tools are Python functions with full type annotations**. The framework handles:
- Argument validation (via Pydantic)
- Return value serialization
- Dependency injection (via `RunContext`)

### Sub-agents

Pydantic AI supports **agent delegation** — one agent can call another agent as a tool:
- `Agent` instances can be registered as tools on other agents
- When the parent agent calls the sub-agent tool, it runs the full sub-agent loop
- Results are serialized back as tool responses

It also supports:
- **Durable execution** (`durable_exec/`) — agent runs that can be paused/resumed
- **A2A protocol** (`_a2a.py`) — agent-to-agent communication
- **MCP integration** (`mcp.py`, 110KB) — tools from MCP servers

### Separation of concerns

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| Graph engine | `_agent_graph.py` | State machine, loop control |
| Agent definition | `Agent` class | Tool registration, deps, result type |
| LLM interaction | `Model` protocol | Provider abstraction |
| Tool execution | `_output.py` | Call tools, validate results |
| Messages | `messages.py` | Structured message types |
| Result | `result.py` | Output validation, streaming |

---

## Cross-Cutting Comparison

### Agent Loop Pattern

| Project | Pattern | Loop Owner | Loop Control |
|---------|---------|------------|-------------|
| OpenHands | Controller-Agent | `AgentController` | External state machine |
| Aider | Monolithic Coder | `Coder.run()` | Single class owns everything |
| Goose | Stream-based Agent | `Agent.reply()` → async stream | Internal with max_turns |
| SWE-Agent | Config-driven | `DefaultAgent.run()` | Template-based with error requery |
| Pydantic AI | Graph-based | `_agent_graph.py` | State machine with typed results |

### Tool Dispatch

| Project | Tool Interface | Dispatch Mechanism | Permission Model |
|---------|---------------|-------------------|-----------------|
| OpenHands | Action types (discriminated union) | Runtime method routing | Controller-level gates |
| Aider | Text parsing (SEARCH/REPLACE blocks) | Regex parsing in subclass | User confirmation for shell |
| Goose | MCP tool calls | ExtensionManager → MCP client | Inspector chain + user approval |
| SWE-Agent | Bash commands (text) | SWEEnv.communicate() | Command blocklist |
| Pydantic AI | Function calling (typed) | Framework validates & calls | None built-in |

### Sub-Agent Support

| Project | Sub-Agent Pattern | Implementation |
|---------|------------------|----------------|
| OpenHands | Delegation via `DelegateAction` | Controller spawns nested agent |
| Aider | Dual-model (architect → editor) | Clone Coder with different model |
| Goose | Explicit `SubagentRunParams` | New Agent with scoped config + callback |
| SWE-Agent | Sequential retry with review | RetryAgent wraps DefaultAgent attempts |
| Pydantic AI | Agent-as-tool | Register agent as callable tool |

### Key Naming Conventions

| Concept | OpenHands | Aider | Goose | SWE-Agent | Pydantic AI |
|---------|-----------|-------|-------|-----------|-------------|
| Main loop | `AgentController` | `Coder` | `Agent` | `DefaultAgent` | `Agent` + graph |
| LLM output | `Action` | edit blocks | `Message` + tool_calls | `(thought, action)` | `ModelResponse` |
| Tool result | `Observation` | N/A (text) | `ToolCallResult` | observation (str) | tool response |
| Single step | `step()` | `run_one()` | turn in stream | `step()` → `forward()` | graph iteration |
| State | `State` | `cur_messages` / `done_messages` | `Conversation` | `history` | graph state |
| Env | `Runtime` | filesystem + git | MCP extensions | `SWEEnv` | tools (functions) |

### Design Decisions Worth Noting

1. **OpenHands**: The cleanest separation — controller knows nothing about LLMs, agents know nothing about execution. Actions are strongly typed. This makes it easy to swap agents.

2. **Aider**: Deliberately monolithic. The `Coder` class is ~2000 LOC but it's simple — one file, one class, one loop. The complexity lives in edit parsing (fuzzy matching, whitespace handling). Reflection loop is the key innovation.

3. **Goose**: The most enterprise-grade. MCP as the tool protocol means tools come from separate processes. The inspector chain (security → egress → adversary → permission) is a pipeline pattern. Sub-agents are first-class with structured output enforcement.

4. **SWE-Agent**: The most research-oriented. Config-driven agents mean you can define new agent behaviors in YAML. The error requery pattern (feed errors back to the model with templates) is more robust than simple retry. The `RetryAgent` with scoring/choosing is unique.

5. **Pydantic AI**: The most type-safe. Generic agents (`Agent[DepsT, ResultT]`), typed tools, structured output validation. The graph engine is general-purpose and supports durability. Best for building multi-agent systems with strong typing.

### Relevance to Pawrrtal's Architecture

For Pawrrtal's Agno-based backend, the most relevant patterns are:

- **Goose's inspector chain** for tool permission (currently Pawrrtal has `backend/app/core/tools/` + `backend/app/core/providers/`)
- **SWE-Agent's error requery** pattern for robust tool failure handling
- **Pydantic AI's typed result** pattern for structured agent outputs
- **OpenHands' Action/Observation** separation for clean tool dispatch
- **Aider's reflection loop** for self-correcting edits
