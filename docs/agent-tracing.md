# Agent Trace & OTLP Setup

Tracing is **off by default**. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable it; unset it and everything is a no-op.

## What gets traced

Three span types cover the full agent loop:

| Span | Name | What it captures |
|------|------|------------------|
| **Turn** | `pawrrtal.turn` | Root span for one chat turn — conversation ID, user, surface, model, TTFT, total duration |
| **LLM** | `pawrrtal.llm.chat` | One per LLM call — full input/output messages, system prompt, token usage, cost, finish reason, streamed text/thinking deltas |
| **Tool** | `<tool_name>.tool` | One per tool execution — arguments, result, duration, error |

Auto-instrumented layers (always on when tracing is enabled):

- **FastAPI** — one span per HTTP request
- **SQLAlchemy** — one span per DB query
- **httpx** — one span per outbound call (LLM providers, OAuth, etc.)
- **Logging** — `trace_id` + `span_id` injected into every log line

## Local setup with an OTLP collector

Use a localhost OTLP collector with a live UI when you need to inspect agent tokens, tool calls, and turn boundaries in real time.

### 1. Install a collector

```bash
curl -fsSL https://raindrop.sh/install | bash
```

### 2. Configure environment

Add to `backend/.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:5899
OTEL_SERVICE_NAME=pawrrtal-backend
```

The backend sends OTLP JSON automatically — no `OTEL_EXPORTER_OTLP_PROTOCOL` needed.

### 3. Run

Start the backend normally (`just dev`). You should see `TELEMETRY_ENABLED` in the startup logs. Open the collector UI, then use the app. Traces appear live as you chat.

## Remote backends (Grafana, Honeycomb, etc.)

The same JSON exporter works with any OTLP/HTTP backend. Point the endpoint at the remote receiver:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-xxx.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64-encoded-credentials>
OTEL_SERVICE_NAME=pawrrtal-backend
```

Most backends accept OTLP JSON. If your backend requires protobuf specifically, you can override the exporter in `telemetry.py`.

## Architecture

```
Request → turn_span (root)
           └─ llm_span
                ├─ streaming events (text/thinking deltas → span events)
                ├─ usage/cost → span attributes
                └─ tool_span (one per tool call, nested under LLM span)
```

Key files:

- `backend/app/infrastructure/telemetry/__init__.py` — OTel bootstrap and auto-instrumentation
- `backend/app/infrastructure/observability/agent_trace.py` — span context managers and event hook
- `backend/app/infrastructure/observability/_schema.py` — attribute and event constants
- `backend/app/infrastructure/observability/_recorders.py` — buffers streamed data and flushes it to spans
- `backend/app/turns/pipeline/runner.py` — wires spans into the Turn Pipeline
- `backend/app/agents/model_tool_loop/tool_calls.py` — wraps tool calls in `tool_span()`
- `backend/tests/test_observability_agent_trace.py` — test suite for the span contract
