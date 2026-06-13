# AI Providers: Architecture, Resolution, & Design Rationale

This directory contains the AI provider implementations for Pawrrtal. The provider layer abstracts third-party LLM SDKs (Google GenAI, Anthropic Claude, xAI, LiteLLM) under a unified streaming protocol, allowing the core agent loop to remain provider-agnostic.

---

## 1. Architectural Philosophy

The provider system is designed around three main pillars:
* **Interface Uniformity**: All providers implement the `AILLM` protocol defined in [base.py](base.py), which enforces a single async generator method `stream(...)` returning a sequence of unified `StreamEvent` dictionaries.
* **Configuration Decoupling**: Provider classes are kept configuration-agnostic and trivially testable. They do not read `app.infrastructure.config.settings` directly. Instead, the provider factory matches hosts, resolves credentials, constructs provider-specific config objects, and injects them.
* **Workspace Isolation**: When a chat starts, the factory accepts a `workspace_root` path. This path is used to resolve workspace-specific API key overrides from local env files and isolates execution directories.

---

## 2. Anatomy of a Model ID

A model identifier in Pawrrtal is a parsed, structured object. The parsing mechanics reside entirely in [model_id.py](model_id.py).

### A. The Wire Format: `[host:]vendor/model`
Model IDs are represented as strings. The prefix `host:` is optional on input, but internally resolved.
* **`host`**: Where the model runs / which API client serves it (defined in the `Host` enum). Examples: `claude-code-pty`, `google-ai`, `litellm`, `opencode-go`, `xai`.
* **`vendor`**: Who built the model (defined in the `Vendor` enum). Examples: `anthropic`, `google`, `openai`, `xai`, `zai`, `moonshot`.
* **`model`**: The raw string name of the specific model. Examples: `claude-sonnet-4-6`, `gemini-3-flash-preview`, `gpt-4o`.

### B. Canonical Host Mapping
To avoid requiring verbose `host:` prefixes everywhere, [model_id.py](model_id.py) maintains a `CANONICAL_HOST` mapping:

```python
CANONICAL_HOST: dict[Vendor, Host] = {
    Vendor.anthropic: Host.claude_code_pty,
    Vendor.google: Host.google_ai,
    Vendor.openai: Host.litellm,
    Vendor.xai: Host.xai,
    Vendor.zai: Host.opencode_go,
    Vendor.moonshot: Host.opencode_go,
}
```

When a bare model ID like `"google/gemini-3-flash-preview"` is parsed:
1. `parse_model_id` extracts `google` as the vendor.
2. It looks up `Vendor.google` in `CANONICAL_HOST` and maps it to `Host.google_ai`.
3. It returns a fully-qualified `ParsedModelId` representing `"google-ai:google/gemini-3-flash-preview"`.

---

## 3. The Model Catalog

The model catalog in [catalog/](catalog/) is the single source of truth for the models that Pawrrtal supports.

### A. Catalog Structure
Every model is registered as a `ModelEntry` dataclass carrying:
* Core identity: `host`, `vendor`, and `model`.
* UI metadata: `display_name`, `short_name`, and `description`.
* Pricing rates: `cost_per_mtok_in_usd` and `cost_per_mtok_out_usd`.

### B. Request Revalidation with ETag
To allow client applications (like the frontend) to query and cache the catalog efficiently, the catalog computes a stable 16-character SHA-256 hash of its contents (`CATALOG_ETAG`). This is returned as an `ETag` header, allowing the frontend to skip redownloading catalog metadata if it hasn't changed.

---

## 4. The Resolver Factory (`resolve_llm`)

The factory in [factory.py](factory.py) parses model IDs and instantiates the correct concrete `AILLM` class.

### Resolution Pipeline

```
  +-------------------------+
  |  resolve_llm(model_id)  |
  +------------+------------+
               |
               v
  Is it already ParsedModelId?
         /           \
       Yes            No
       /                \
      v                  v
[parsed = model_id]   [parsed = parse_model_id(raw)]
      |                  |
      +--------+---------+
               |
               v
  Lookup provider class in HOST_TO_PROVIDER
  (e.g., Host.google_ai -> GeminiLLM)
               |
               v
  Isolate and construct concrete provider instance:
  - Inject workspace_root
  - Extract credentials from settings
  - Construct custom configuration objects
               |
               v
  Return concrete AILLM instance (ready to stream)
```

---

## 5. Design Rationale: Strings vs. Code Constants

A common question is why Pawrrtal uses hardcoded, wire-format strings (`[host:]vendor/model`) instead of exposing Python constants or helper classes (e.g., `Providers.Gemini.FLASH` or `Models.CLAUDE_SONNET`).

This is a deliberate architectural decision driven by three factors:

### A. Dynamic Model Catalogs
The list of available models is highly dynamic. New models are released frequently, and older models are deprecated. If model references were hardcoded as code constants:
* Every upstream change or model deprecation would require code changes, compiling, and redeploying.
* In contrast, string-based identifiers allow models to be added, modified, or removed purely by updating the data structure in [catalog/](catalog/) (or eventually loading the catalog from a database or config file dynamically).

### B. Serialization & Cross-Stack Boundaries
Model selections must travel across network boundaries and database tables:
* Users choose a model in the frontend (JSON payload).
* The selected model is saved in the database (e.g., `model_id` string column on the `conversations` table).
* The API router receives a JSON string.
* Storing and transporting a simple string representation is trivial and robust. If the backend relied on python constants, we would constantly need to serialize and deserialize between strings and python symbols. By standardizing on `host:vendor/model` as the canonical string representation everywhere, the database, API, logs, frontend, and backend all speak the exact same language.

### C. Gateway and Third-Party Flexibility
For gateway hosts like `Host.litellm` or `Host.opencode-go`, the backend acts as a pass-through client.
* For example, the `opencode-go` provider queries a hosted gateway that serves open-weight models.
* By using string-based identifiers, we can support new models exposed by these gateways without updating any python structures or writing new provider classes. We simply add a new string mapping to [catalog/](catalog/).

### D. Safety at the Boundary
To prevent developers or users from messing up the string-based model IDs, validation is enforced strictly at the outermost boundary:
* Pydantic schemas validate input strings against `MODEL_CATALOG` entries.
* `parse_model_id` raises `InvalidModelId` if the structure is incorrect.
* `resolve_llm` raises `UnknownModelId` if the model is not found in the catalog.
* This ensures that any typo in a model ID string is caught instantly and rejected with a clean `422 Unprocessable Entity` HTTP response before execution begins.
