# Agent Loop: Architecture, Lifecycle, & Provider Guide

This directory houses the provider-agnostic agent execution engine for Pawrrtal. The architecture is inspired by the Pi-agent core system, separating LLM provider mechanics from tool execution, safety boundaries, and user permission flows.

---

## 1. Architectural Philosophy

The core philosophy of the loop is **strict separation of concerns**:
* **Provider Agnosticism**: The execution loop does not import or know about specific model SDKs (Google GenAI, Anthropic Claude, xAI, LiteLLM). Instead, it delegates LLM interaction to a provider-supplied async iterator closure called a `StreamFn`.
* **Centralized Tool Execution**: The loop is the single, authoritative executor of tools. It manages parameter validation, wraps execution in observability spans, and checks user permission callbacks.
* **Deterministic Safety Boundaries**: Loop counts, total elapsed wall-clock execution time, consecutive API errors, and consecutive tool execution errors are capped at the loop boundary, preventing runaway token usage and infinite execution loops.

---

## 2. The AI Provider System & StreamFn Bridges

AI models in Pawrrtal implement the `AILLM` protocol defined in [base.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/providers/base.py). The connection between this high-level protocol and the execution engine is bridged through the `StreamFn` signature.

### A. The `StreamFn` Seam
The agent loop abstracts model execution using the `StreamFn` contract defined in [types.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/types.py):
```python
StreamFn = Callable[
    [list[AgentMessage], list[AgentTool]],
    AsyncIterator[LLMEvent]
]
```
The execution engine is responsible for executing tools and keeping history. It calls the `StreamFn` on each turn, passing the accumulated history (as processed by `convert_to_llm`) and the tool definitions, and then consumes the stream of `LLMEvent` dicts emitted by the model.

### B. Per-Turn Fresh Closure Pattern
Providers do not reuse a single static function for model calls. Instead, when `stream()` is called, they build a fresh closure per turn via factories like `make_gemini_stream_fn`:
1. **Dynamic Prompt Capture**: The workspace system prompt (composed from `SOUL.md`, `AGENTS.md`, and skills) is captured in the closure's scope and bound to the request config on each call.
2. **Workspace API Key Isolation**: The closure resolves credentials (e.g. per-workspace `GEMINI_API_KEY` via `resolve_api_key`) and constructs a fresh client instance, keeping the provider thread-safe and isolated.

### C. Disabling Automatic Function Calling
By default, LLM SDKs try to automatically run function calls they emit and return the result. In Pawrrtal, we explicitly disable this (e.g. `automatic_function_calling=False` on Gemini).
* Disabling this forces the model to emit a raw JSON function call block.
* The provider yields this block as a `LLMToolCallEvent`.
* The `run_model_tool_loop` captures the event, executes the tool, and feeds the `ToolResultMessage` back to the model in the next turn.

### D. Opaque State Propagation (`provider_state`)
Some model providers require proprietary state to resume multi-turn conversations safely (for example, Gemini-3 / Vertex requires replaying the raw `model_content` parts and `thought_signature` bytes from the model's function-calling response, otherwise the next tool result request is rejected).

To support this without breaking provider-agnosticism, the loop acts as an **opaque courier**:
* The provider packs this metadata into the `provider_state` dictionary on the terminal `done` event (`LLMDoneEvent`).
* The loop copies `provider_state` directly into the `AssistantMessage` appended to the history.
* In the next turn, the provider extracts the state from the history to format the payload for the model API. The loop never inspects, modifies, or understands this state.

### E. Provider Bridging Comparison
The two primary provider integrations handle history, tools, and credentials differently:

| Feature | Gemini Provider ([gemini_provider.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/providers/gemini_provider.py)) | Claude Provider ([claude_provider.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/providers/claude_provider.py)) |
| :--- | :--- | :--- |
| **Loop Integration** | Directly invokes `run_model_tool_loop(...)` passing a `make_gemini_stream_fn` closure. | Orchestrates a CLI/SDK subprocess and streams its raw JSON events directly. |
| **Tool Translation** | Maps `AgentTool` parameters directly to Gemini's `FunctionDeclaration` list. | Maps `AgentTool` instances to a local, in-process MCP server that the Claude subprocess queries. |
| **History Continuity** | Relies on the chat-history list passed into `contents` on each API call. | Uses native Claude transcript continuity via `resume=str(conversation_id)`. |
| **Credentials** | Resolves per-workspace keys via `resolve_api_key` for the Client. | Forwards OAuth tokens via `ClaudeAgentOptions.env` to the subprocess. |

---

## 3. Key Data Types

All data structures are defined in [backend/app/core/run_model_tool_loop/types.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/types.py).

### A. `AgentContext`
The state container initialized by the caller. Holds the conversation system configuration.
```python
@dataclass
class AgentContext:
    system_prompt: str             # Base instructions for the model
    messages: list[AgentMessage]   # Conversation history accumulated so far
    tools: list[AgentTool]        # List of tool definitions available to the agent
```

### B. `AgentLoopConfig`
Configures hooks and options for the loop execution.
```python
@dataclass
class AgentLoopConfig:
    convert_to_llm: Callable[[list[AgentMessage]], list[AgentMessage]]
    transform_context: TransformContextFn | None = None
    should_stop_after_turn: ShouldStopFn | None = None
    safety: AgentSafetyConfig = field(default_factory=AgentSafetyConfig)
```
> [!NOTE]
> * `convert_to_llm`: Pre-processes messages before they are handed to the provider (e.g. filtering out UI-specific messages).
> * `transform_context`: An optional async function to trim/summarize history before each LLM call (e.g. for context windows).
> * `safety`: Holds limit configurations (max turns, wall-clock timeout).

### C. `AgentMessage`
Unified message wrapper format. It can be one of:
* `UserMessage`: User-authored inputs (`role: "user"`).
* `AssistantMessage`: Text content and tool calls emitted by the model (`role: "assistant"`).
* `ToolResultMessage`: Results returned from tool executions (`role: "toolResult"`).

---

## 4. Execution Flow and Lifecycle

The agent loop works as an event-driven generator. Below is the step-by-step lifecycle:

```
             +---------------------------+
             |  Caller calls run_model_tool_loop  |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             |    Evaluate Safety Caps   | <-------------------------+
             +-------------+-------------+                           |
                           |                                         |
                 Are caps exceeded?                                  |
                /                  \                                 |
              Yes                  No                                |
              /                      \                               |
             v                        v                              |
   +------------------+     +-------------------+                    |
   | Yield Terminated |     | Prepare messages  |                    |
   |   Event & Exit   |     | via convert_to_llm|                    |
   +------------------+     +---------+---------+                    |
                                      |                              |
                                      v                              |
                            +-------------------+                    |
                            | Call Provider API |                    |
                            |  (run stream_fn)  |                    |
                            +---------+---------+                    |
                                      |                              |
                                      v                              |
                            +-------------------+                    |
                            |   Consume Stream  |                    |
                            |  Yield text_delta |                    |
                            +---------+---------+                    |
                                      |                              |
                              Did LLM request                        |
                              any tool calls?                        |
                             /               \                       |
                           Yes                No                     |
                           /                    \                    |
                          v                      v                   |
              +---------------------+  +--------------------+        |
              | Check permissions & |  |  Append Assistant  |        |
              | execute each tool   |  | Message to History |        |
              +----------+----------+  +---------+----------+        |
                         |                       |                   |
                         v                       v                   |
              +---------------------+  +--------------------+        |
              | Append tool results |  |   Yield AgentEnd   |        |
              |   to messages       |  |    Event & Exit    |        |
              +----------+----------+  +--------------------+        |
                         |                                           |
                         +-------------------------------------------+
```

### Yielded Events
Callers can listen for specific event types yielded by the loop generator:
* `agent_start`: The loop has started execution.
* `turn_start`: Emitted before the LLM begins streaming its turn.
* `text_delta`: Tokens (content text) yielded by the provider.
* `thinking_delta`: Reasoning / chain-of-thought tokens (emitted in a separate lane).
* `tool_call_start`: Sent when the loop starts dispatching a tool call.
* `tool_call_end`: Sent after a tool call is parsed, announcing arguments and UI labels.
* `tool_result`: Yielded once a tool returns its result string (or raises an error/is blocked by permissions).
* `turn_end`: Signal that a single completion turn (model generation + all associated tool execution results) has finished.
* `agent_end`: The normal terminal event. Contains the updated message list.
* `agent_terminated`: Safety cap trigger (e.g. runaway tool calls). Contains the termination reason.

---

## 5. In-Depth Multi-Stage Examples

The following stages demonstrate how to define a custom tool, configure safety, wire up a permission gate, resolve a provider, and run the agent execution loop.

### Stage 1: Define a Custom Tool
Pawrrtal tools are instances of the `AgentTool` dataclass. They define metadata, a JSON Schema parameter validation dictionary, and an async execution callback.

```python
import httpx
from app.agents.types import AgentTool

async def get_weather_report(tool_call_id: str, *, location: str) -> str:
    """Async execution callback for the weather tool."""
    try:
        async with httpx.AsyncClient() as client:
            # Simulated geo-weather fetch
            response = await client.get(
                f"https://api.open-meteo.com/v1/forecast",
                params={"latitude": 37.77, "longitude": -122.41, "current_weather": True}
            )
            if response.status_code == 200:
                data = response.json()
                temp = data["current_weather"]["temperature"]
                return f"The current temperature in {location} is {temp}°C."
            return f"Error: Received status {response.status_code} from weather API."
    except Exception as e:
        return f"Failed to execute weather lookup: {str(e)}"

# Instantiate the AgentTool
weather_tool = AgentTool(
    name="get_weather",
    description="Fetch the current temperature for a city name.",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City and country/state, e.g. London, UK or San Francisco, CA"
            }
        },
        "required": ["location"],
    },
    execute=get_weather_report
)

tools_catalog = [weather_tool]
```

### Stage 2: Setup Permission Checks and Safety Caps
Next, configure safety caps (like maximum tool-loop iterations and wall-clock timeout) and construct an async permission gate.

```python
from app.agents.types import AgentLoopConfig, AgentSafetyConfig

# 1. Configure the safety limit boundaries
safety_config = AgentSafetyConfig(
    max_iterations=5,                  # Prevent tool-use loops longer than 5 iterations
    max_wall_clock_seconds=30.0,       # Capped turn execution time
    max_consecutive_llm_errors=3,      # Terminate if API is down
    max_consecutive_tool_errors=2      # Terminate if model retries broken args
)

# 2. Assemble the loop config
loop_config = AgentLoopConfig(
    convert_to_llm=lambda msgs: msgs,   # Identity converter (no modification)
    safety=safety_config
)
```

### Stage 3: Resolve the Provider and build the StreamFn
Resolve the model string via `resolve_llm`. This returns a wrapper class matching the `AILLM` protocol, whose `stream()` method provides our target execution loop callback.

```python
from pathlib import Path
from app.providers.factory import resolve_llm

# Resolve a specific model; works out-of-the-box with workspace configs
provider = resolve_llm(
    model_id="google_ai:gemini-2.5-flash",
    workspace_root=Path("/Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI")
)

# Pull the streaming function bridge.
# The provider wraps make_gemini_stream_fn internally and handles
# client credentials, system instructions, and tool declaration mapping.
stream_fn = provider.stream
```

### Stage 4: Initialize the Context and Execute the Loop
Assemble the base configuration, conversation history, and start the generator.

```python
from app.agents.model_tool_loop import run_model_tool_loop
from app.agents.types import AgentContext, UserMessage

# 1. Define the system instructions and initial history
context = AgentContext(
    system_prompt="You are a helpful local concierge. Use tools when asked.",
    messages=[],  # Accumulator for previous turns
    tools=tools_catalog
)

# 2. Frame the user request
user_prompt = UserMessage(role="user", content="What is the weather in San Francisco?")

# 3. Launch the execution generator
# We pass the new prompt alongside the context and config
loop_generator = run_model_tool_loop(
    prompts=[user_prompt],
    context=context,
    config=loop_config,
    stream_fn=provider.stream  # Resolves StreamFn calls dynamically
)
```

### Stage 5: Consume the generated Events and handle output/errors
Iterate through the yielded events to stream tokens to the user, announce tool executions, and capture final histories.

```python
import sys

async def execute_agent():
    async for event in loop_generator:
        event_type = event["type"]

        if event_type == "agent_start":
            print(">>> Agent Execution Started")

        elif event_type == "text_delta":
            # Stream tokens directly to stdout as they arrive
            sys.stdout.write(event["text"])
            sys.stdout.flush()

        elif event_type == "thinking_delta":
            # Stream reasoning/thinking blocks in a separate style
            sys.stdout.write(f"\033[90m{event['text']}\033[0m")
            sys.stdout.flush()

        elif event_type == "tool_call_start":
            print(f"\n[Invoking: {event['name']} ({event['tool_call_id']})]...")

        elif event_type == "tool_result":
            status = "FAILED" if event["is_error"] else "SUCCESS"
            print(f"[Tool Result: {status}] -> {event['content']}")

        elif event_type == "agent_terminated":
            print(f"\n!!! Execution Aborted: {event['reason']}")
            print(f"Message: {event['message']}")

        elif event_type == "agent_end":
            print("\n>>> Agent Turn Completed.")
            # Retrieve the full, updated message history
            final_messages = event["messages"]
            print(f"Total history length: {len(final_messages)} messages.")

# To execute the flow:
# asyncio.run(execute_agent())
```

---

## 6. Modules in this Package

* **[loop.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/loop.py)**: The central controller and executor. Manages turns, schedules tool calls, runs permissions checks, handles retry policies, and executes safety caps.
* **[types.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/types.py)**: The type definitions and contracts for context, configs, events, and message envelopes.
* **[safety_factory.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/safety_factory.py)**: A helper module to extract and build `AgentSafetyConfig` limits from settings or workspace overrides.
* **[display.py](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/run_model_tool_loop/display.py)**: Handles mapping internal tool parameters to human-readable labels and descriptions for user-facing streams.
