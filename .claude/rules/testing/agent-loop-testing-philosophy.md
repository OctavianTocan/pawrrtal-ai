---
name: agent-loop-testing-philosophy
paths: ["backend/**/*.py", "backend/tests/**"]
---

# Test the Agent Loop via ScriptedStreamFn, Not by Patching the Loop

The agent loop, safety layer, and all StreamFn-based code must be tested with
**scripted-trajectory tests** — not by patching away the loop internals.

## The `ScriptedStreamFn` pattern (mandatory for harness behavior tests)

Instead of mocking `run_model_tool_loop`, `AgentContext`, or `AgentLoopConfig` directly,
author deterministic LLM decision sequences and run them through the **real**
harness. Only the `StreamFn` seam is replaced. Every other component —
safety, tool execution, message accumulation — runs as it does in production.

```python
from tests.agent_loop_harness import (
    ScriptedStreamFn,
    echo_tool,
    error_turn,
    run_scenario,
    text_turn,
    tool_call_turn,
)

# Author a realistic multi-turn script.
script = ScriptedStreamFn([
    tool_call_turn("search", {"query": "python async"}),
    text_turn("Here is what I found."),
])

events = await run_scenario(script, tools=[search_tool])  # pass script, not script.turns
assert script.call_count == 2              # two LLM calls were made

# ⚠️  Footgun: passing script.turns (a list) instead of script creates a new
# ScriptedStreamFn internally, so script.call_count always stays 0.
# Always pass the ScriptedStreamFn object itself to run_scenario.
assert any(e["type"] == "tool_result" for e in events)
```

The shared primitives live in `backend/tests/agent_loop_harness.py`.

## Rules

1. **Never patch `run_model_tool_loop` away in a harness behavior test.** Patching the
   loop out means you're testing nothing — the safety layer, tool dispatch, and
   context accumulation are all skipped.

   ```python
   # ❌ WRONG — patches the loop, tests nothing real
   with patch("app.core.providers.gemini_provider.run_model_tool_loop", side_effect=fake):
       ...

   # ✅ RIGHT — injects script at StreamFn seam, real loop runs
   monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([...]))
   ```

2. **Use `ScriptedStreamFn` for any test of safety limits, tool dispatch, or
   context accumulation.** Simple unit tests of a single function (e.g. a tool's
   `execute()`) may still use `AsyncMock` or direct calls.

3. **`FakeProvider` is acceptable for HTTP-layer tests that only check routing,
   status codes, model persistence, and SSE framing** — not for tests that make
   assertions about the agent loop's behavior.

4. **Use `script.call_count` as a hard assertion** after `run_scenario` or any
   test using `ScriptedStreamFn`. If the safety layer fires at iteration N,
   `call_count` must equal N. A test that only checks for an `agent_terminated`
   event in the output without checking `call_count` is weak.

   **Footgun**: always pass the `ScriptedStreamFn` object to `run_scenario`, not
   `script.turns` — passing `.turns` (a list) causes `run_scenario` to create a
   new `ScriptedStreamFn` internally, leaving the original `script.call_count`
   permanently at 0.

5. **Tests that verify safety config must use a realistic cap** (e.g.
   `max_iterations=3` with a 10-turn runaway script), not `max_iterations=0`
   (never happens in production and bypasses the LLM entirely).

6. **Scenario tests belong in `test_agent_loop_scenarios.py`.** Safety-specific
   limit tests belong in `test_agent_loop_safety.py`. Provider-specific
   translation tests (AgentEvent → StreamEvent) belong in
   `test_gemini_stream_fn.py` / `test_claude_provider.py`.

7. **New harness primitives go in `agent_loop_harness.py`**, not inline in test files.
   If you need a new turn shape, tool, or runner helper, add it to the shared
   module so other test files can reuse it.

## When `FakeProvider` is still appropriate

| Test concern                                              | Use                  |
| --------------------------------------------------------- | -------------------- |
| HTTP status codes (404, 412)                              | `FakeProvider`       |
| SSE framing / `[DONE]` sentinel                           | `FakeProvider`       |
| Model ID persistence on conversation                      | `FakeProvider`       |
| Provider exception → error SSE frame                      | inline `FailingProvider` |
| Tool call dispatch / tool result in context               | `ScriptedStreamFn`   |
| Safety limits (max_iterations, wall-clock, error budgets) | `ScriptedStreamFn`   |
| `agent_terminated` event surfaces in HTTP response        | `ScriptedStreamFn`   |
| History accumulation across turns                         | `ScriptedStreamFn`   |
| Provider translates AgentEvent → StreamEvent              | `ScriptedStreamFn`   |

## Verify

"Am I patching `run_model_tool_loop` directly? If yes, switch to `ScriptedStreamFn` at
the `_stream_fn` seam. Did I assert `script.call_count`? Did I pass the
`ScriptedStreamFn` object (not `script.turns`) to `run_scenario`?"
