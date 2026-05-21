---
# pawrrtal-dhqm
title: Add provider conformance test suite + Telegram channel snapshot tests
status: todo
type: feature
priority: high
created_at: 2026-05-19T12:36:06Z
updated_at: 2026-05-19T12:45:53Z
---

Prevent silent provider regressions (xAI thinking, legacy text drop) by adding: (1) parametrized ScriptedStreamFn conformance tests covering pure-text/thinking-only/tool/multi-block/error scenarios per provider; (2) Telegram channel snapshot tests asserting the bot call sequence end-to-end; (3) catalog smoke test that every entry instantiates. CI gate on backend/app/core/providers/** and backend/app/channels/**.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/352


## Concrete plan (researched 2026-05-19)

Researched established patterns across LangChain (\`langchain-tests\`), Vercel AI SDK (\`simulateReadableStream\` / \`MockLanguageModelV3\`), OpenAI Agents SDK, OpenLLMetry, and OTel \`InMemorySpanExporter\`. The verdict: pawrrtal already has the right seam (\`ScriptedStreamFn\` in \`backend/tests/agent_harness.py\`) — what's missing is **layered tests on top of it** at the channel and observability tiers.

### Layer 1 — Canonical scripts fixture library (~1 day, highest leverage)

Extend \`backend/tests/agent_harness.py\` with named scripts covering every shape that has bitten us:

- \`text_only_turn(text)\` — already exists as \`text_turn\`.
- \`thinking_then_text_turn(thinking, text)\` — already exists.
- \`per_token_thinking_turn(words)\` — NEW. Yields one \`LLMThinkingDeltaEvent\` per word. Reproduces the xAI vertical-text bug (pawrrtal-o0wq).
- \`multi_thinking_block_turn(blocks)\` — NEW. Yields several \`LLMThinkingDeltaEvent\`s with no separator. Reproduces the Gemini block-separation bug (pawrrtal-pxnb).
- \`tool_call_then_text_turn(...)\` — compose existing \`tool_call_turn\` + \`text_turn\`. Reproduces the legacy-text bug (pawrrtal-s0w4).
- \`auth_error_as_text_turn(message)\` — NEW. Yields \`LLMTextDeltaEvent(text='Provider error: ...')\` + \`LLMDoneEvent\`. Reproduces the OpenCode Go silent-failure shape (pawrrtal-yxe6).

### Layer 2 — Channel snapshot tests (~½ day)

New file: \`backend/tests/test_telegram_channel_snapshot.py\`. Use a \`FakeBot\` that records every \`send_message\` / \`edit_message_text\` / \`delete_message\` call (text, message_id, kwargs). Drive \`TelegramChannel.deliver\` end-to-end with curated scripts. Assert the bot call sequence with **literal \`assert calls == [...]\`** (inline, in the test source — not a separate snapshot file). Per the research, inline assertions force regressions into the PR diff where reviewers can't rubber-stamp them.

One test per canonical script, one parametrized over \`telegram_use_draft_streaming \\in {True, False}\`. The legacy-only-first-word bug (pawrrtal-s0w4) is caught the moment the \`tool_call_then_text\` script runs against the legacy path — its last \`send_message\` call would carry only the first chunk.

### Layer 3 — OTel observability conformance (~½ day)

Mirror OpenLLMetry's conftest pattern (https://github.com/traceloop/openllmetry):

\`\`\`python
@pytest.fixture(scope='function')
def span_exporter():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace import TracerProvider
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # bind to app.core.telemetry's provider for the duration of the test
    yield exporter
\`\`\`

One parametrized test asserting "observability sees N \`gen_ai.thinking.delta\` events regardless of \`(channel, verbose_level)\`". Catches pawrrtal-l3fi (Workshop OTel gating) directly.

### Layer 4 — Provider conformance class (~1 day, after Layer 1)

Apply LangChain's \`ChatModelIntegrationTests\` pattern (https://python.langchain.com/api_reference/standard_tests/integration_tests/langchain_tests.integration_tests.chat_models.ChatModelIntegrationTests.html). New file: \`backend/tests/conformance/test_provider_conformance.py\`.

\`\`\`python
class ProviderConformanceTests(ABC):
    @abstractmethod
    def make_provider(self, model_id: str) -> AILLM: ...
    @abstractmethod
    def default_model(self) -> str: ...

    async def test_pure_text(self): ...
    async def test_thinking_then_text(self): ...
    async def test_tool_call_then_text(self): ...
    async def test_per_token_thinking(self): ...  # catches xAI bug across providers
    async def test_multi_thinking_block(self): ...  # catches Gemini bug across providers
    async def test_auth_error_as_text(self): ...

class TestAnthropicConformance(ProviderConformanceTests): ...
class TestGeminiConformance(ProviderConformanceTests): ...
class TestXaiConformance(ProviderConformanceTests): ...
class TestOpenCodeGoConformance(ProviderConformanceTests): ...
\`\`\`

### Layer 5 — Catalog smoke (~1 hour)

In \`backend/tests/test_catalog.py\` (already exists), add: every \`ModelEntry\` instantiates its provider without error, and the list of model slugs matches an inline-snapshot. Catches pawrrtal-x9ci (missing Gemini Pro) and pawrrtal-xljg (only-two OpenCode Go) the moment someone removes an entry.

### CI gate

Run all five layers on every PR touching:
- \`backend/app/core/providers/**\`
- \`backend/app/channels/**\`
- \`backend/app/core/agent_loop/**\`
- \`backend/app/core/chat_aggregator.py\`
- \`backend/app/core/observability/**\`

### Explicitly deferred

- **Hypothesis (property-based testing)**: input space is small, bugs are about specific sequences. A canonical script catches each one with a better error message.
- **VCR / recorded cassettes**: scripted streams cover all six bugs in scope. VCR adds wire-fidelity but pays a "re-record on API change" tax. Optional: one cassette per provider as a one-shot calibration.
- **syrupy** (separate snapshot files): use \`inline-snapshot\` instead, so diffs land in the PR.

### Total scope

~2.5 days. Catches all six concurrent bug categories from the 2026-05-19 investigation session.

### Bug → layer map

| Bug | Bean | Caught by |
|---|---|---|
| Legacy text path swallows post-block deltas | pawrrtal-s0w4 | Layer 2 (channel snapshot, \`tool_call_then_text\` script, \`draft_streaming=False\`) |
| xAI vertical thinking | pawrrtal-o0wq | Layer 2 (channel snapshot, \`per_token_thinking\` script) |
| Workshop OTel gating | pawrrtal-l3fi | Layer 3 (InMemorySpanExporter conformance) |
| Gemini blocks unseparated | pawrrtal-pxnb | Layer 4 (cross-provider conformance, \`multi_thinking_block\` script) |
| OpenCode Go silent fail | pawrrtal-yxe6 | Layer 2 + Layer 4 (auth_error script) |
| Catalog drops/gaps | pawrrtal-x9ci, pawrrtal-xljg | Layer 5 (catalog snapshot) |
