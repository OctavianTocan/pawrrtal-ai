---
description: Providers must stay tool-agnostic. Tool composition is the chat router's job.
paths: ["backend/app/providers/**", "backend/app/chat/router.py"]
---

# Architecture: No Tools In Providers

The agent-loop architecture is provider-neutral. Providers translate
the cross-provider `AgentTool` shape (defined in
`backend/app/agents/types.py`) into their SDK's tool format
— but they **never reach into specific tool factories**.

## Rule

Files under `backend/app/providers/` **MAY NOT** import from
`backend/app/tools/*`.

Tool composition (which tools the agent gets this turn) lives in the
**chat router** (`backend/app/chat/router.py`). Adding a new tool means
appending to the list in the router, never touching a provider.

## Why

1. **Capability ≠ provider.** "Web search" is something the
   application offers. Whether the model behind today's request is
   Gemini, Claude, or OpenAI shouldn't change which tools exist.
2. **Permission gating breaks otherwise.** Once we add per-agent /
   per-user tool allowlists, the gate has to live above the
   providers — otherwise every provider re-implements the gate and
   they drift.
3. **Drop guarantees disappear.** If a provider silently appends
   tools, the chat router's view of "what's available" is wrong —
   and tests, logs, and audit trails based on the router's list lie.
4. **New providers copy the smell.** Once one provider has
   `if settings.X: tools.append(...)`, every new provider does too.
   Adding OpenAI or another model becomes "rewrite the whole tool
   list, but in OpenAI shape" instead of "implement `StreamFn`."

## What's allowed

- Provider-internal **bridges** that translate the abstract
  `AgentTool` shape: `providers/_*_tool_bridge.py`. These don't
  import concrete tool factories — they take a generic
  `list[AgentTool]` and produce the SDK's tool format. Example:
  `providers/_claude_tool_bridge.py` wraps every `AgentTool` in a
  `claude_agent_sdk.tool` decorator and assembles them into one
  in-process MCP server.
- Importing `app.agents.types.AgentTool` itself — the
  abstract dataclass, not a tool factory — is fine.

## Wrong (don't do this)

```python
# backend/app/providers/gemini/provider.py
from app.tools.exa_search_agent import make_exa_search_tool  # ❌

class GeminiLLM:
    async def stream(self, ..., tools=None, ...):
        effective_tools = list(tools or [])
        if settings.exa_api_key:
            effective_tools.append(make_exa_search_tool())  # ❌
        ...
```

## Right

```python
# backend/app/chat/router.py
from app.tools.workspace_files import make_workspace_tools
from app.tools.exa_search_agent import make_exa_search_tool

agent_tools: list[AgentTool] = []
agent_tools.extend(make_workspace_tools(root))
if settings.exa_api_key:
    agent_tools.append(make_exa_search_tool())

async for event in provider.stream(..., tools=agent_tools, ...):
    ...
```

```python
# backend/app/providers/gemini/provider.py
class GeminiLLM:
    async def stream(self, ..., tools=None, ...):
        # Pure passthrough — no tool composition here.
        context = AgentContext(..., tools=list(tools or []))
        ...
```

## Enforcement

`scripts/check-no-tools-in-providers.py` runs in the backend pytest
CI workflow before the test deps install. It uses Python's `ast`
module to walk each file under `backend/app/providers/` and
fails CI if any `import` or `from ... import` statement has a
module path that starts with `app.tools.`.

```sh
python3 scripts/check-no-tools-in-providers.py        # default
python3 scripts/check-no-tools-in-providers.py -v     # verbose
```

There is **no allowlist**. If you need to import a tool factory from
inside a provider, the right answer is almost always "you don't —
move the composition into the chat router." If a real exception
comes up, raise it in review and we'll discuss adding a narrow
exemption to the script (or, more likely, a missing abstraction in
the bridge layer).

## References

- `backend/app/agents/types.py` — `AgentTool` dataclass.
- `backend/app/providers/claude/tool_bridge.py` — example of
  a provider-internal bridge that's allowed.
- `backend/app/chat/router.py` — canonical example of the chat-router
  composition pattern.
