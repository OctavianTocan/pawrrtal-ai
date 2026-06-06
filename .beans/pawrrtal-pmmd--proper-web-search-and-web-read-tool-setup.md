---
# pawrrtal-pmmd
title: Build a proper provider-agnostic web search + web-read tool setup
status: todo
type: feature
priority: medium
created_at: 2026-06-03T18:02:00Z
updated_at: 2026-06-03T18:02:00Z
tags:
  - tools
  - web-search
  - agent
  - architecture
---

## Goal

Turn web access from "one hard-coded Exa search tool" into a small,
provider-agnostic **web research capability**: the agent can search the
web AND deep-read a specific URL, the search backend is swappable
(Exa / Tavily / Brave / SearXNG), and the user can see/feel when web
search is available instead of the tool silently not existing.

**Non-goal:** we are NOT building a headless browser, a crawler, or a
JS-rendering engine. Lean on Exa + user-configured MCP servers for
anything heavier. Keep this tiny.

## Why now

Today web access is a single capability-gated tool and nothing else:

- `backend/app/tools/exa_search.py` — the only network path to the web.
- `backend/app/tools/exa_search_agent.py` — the `AgentTool` wrapper.
- `backend/app/agents/tools.py:152` — gates the tool on `EXA_API_KEY`
  resolving (workspace override → global settings).

Gaps a "proper setup" should close:

1. **No web-read tool.** The agent can search and get highlights, but
   cannot say "open result #2 and read the whole thing" as a first-class
   action. `include_full_text` exists on search, but there is no
   standalone "fetch this URL and give me the readable text" tool.
2. **Exa is hard-wired.** There is no seam to swap in Tavily / Brave /
   SearXNG the way `backend/app/providers/` lets us swap LLMs. One vendor
   = one point of failure + one bill.
3. **Invisible availability.** With no key, the tool simply isn't in the
   list — the user gets no signal that "web search exists but needs a
   key." Compare the loader/empty-state convention in `DESIGN.md`.

## Files

Touch (mirror the existing tool-factory + capability-gate pattern — do
NOT reach into providers; see
`.claude/rules/architecture/no-tools-in-providers.md`):

| Path | Change |
| --- | --- |
| `backend/app/tools/web_search.py` (new) | Provider-agnostic search core: `WebSearchProvider` protocol + `exa` impl moved/renamed from `exa_search.py` |
| `backend/app/tools/web_read.py` (new) | `web_read(url)` core — fetch + extract readable text (Exa `/contents` first; plain `httpx` + `markitdown` fallback) |
| `backend/app/tools/web_search_agent.py` (new) | `make_web_search_tool()` — replaces `exa_search_agent.py`, selects provider from settings/env |
| `backend/app/tools/web_read_agent.py` (new) | `make_web_read_tool()` `AgentTool` wrapper |
| `backend/app/agents/tools.py` | Compose the new tools behind the same capability gate; keep stable ordering |
| `backend/app/infrastructure/keys.py` | Add new provider keys to `OVERRIDABLE_KEYS` + `_SETTINGS_ATTR_MAP` (e.g. `TAVILY_API_KEY`, `BRAVE_API_KEY`, `SEARXNG_URL`) |
| `backend/app/infrastructure/config.py` | Add the matching `Settings` fields + a `web_search_provider` selector |
| `frontend/features/settings/.../WorkspacesSection.tsx` | Show new keys; show "web search: off until a key is set" affordance |
| `frontend/.../use-workspace-env.ts` | Extend `WORKSPACE_ENV_KEY_IDS` to match the backend allowlist |
| `DESIGN.md` + `frontend/content/docs/handbook/...` | Document the capability + the "unavailable until configured" UX |

## How it works

1. **Search core** exposes a tiny protocol so the vendor is swappable:

   ```python
   class WebSearchProvider(Protocol):
       async def search(
           self, query: str, *, num_results: int, include_full_text: bool
       ) -> WebSearchResult: ...
   ```

   Exa is the first (and default) implementation — keep its current
   "highlights-only, type=auto, num_results=5" agent-tuned defaults.

2. **Provider selection** is a single setting (`web_search_provider`,
   default `"exa"`) plus the resolved key. Resolution reuses
   `resolve_api_key(workspace_root, KEY)` exactly as today — workspace
   override → global settings → none.

3. **web_read** is a separate `AgentTool`: given a URL, return clean
   markdown text. Prefer Exa `/contents` when an Exa key is present
   (already paid for, neural cleanup); otherwise `httpx.get` + the
   existing `markitdown` converter. Cap output bytes like the search
   tool caps `num_results`.

4. **Capability gate** stays in `build_agent_tools`: the search tool is
   appended iff *some* search provider resolves a key; `web_read` is
   appended iff search is available OR an Exa key is present. No key →
   tools absent (current behavior preserved).

5. **Graceful failure** unchanged: cores catch transport/HTTP errors and
   return a structured `error` string so the LLM apologizes instead of
   crashing the turn (see `exa_search.py` for the pattern to copy).

## Steps

1. Move the Exa network core into `web_search.py` behind the
   `WebSearchProvider` protocol; keep `exa_search()` working (re-export
   for back-compat so tests/imports don't break in one commit).
2. Add a second provider impl (pick **Tavily** or **SearXNG** — SearXNG
   is self-hostable + free, good for the BYO-key ethos). Gate it on its
   own key/URL.
3. Add `web_read.py` core + `make_web_read_tool()` wrapper.
4. Add the provider selector + new keys to `config.py`, `keys.py`
   (`OVERRIDABLE_KEYS` **and** `_SETTINGS_ATTR_MAP`), and the frontend
   `WORKSPACE_ENV_KEY_IDS` (these three must stay in sync — the PUT
   endpoint 400s on unknown keys).
5. Rewire `build_agent_tools` to compose `web_search` + `web_read`
   behind the gate, preserving stable tool order.
6. Frontend: render the new keys in Settings → Workspaces and add the
   "web search is off until you add a key" affordance (loader/empty-state
   per `DESIGN.md`, not a silent absence).
7. Tests (same commit): capability gating per provider, provider
   selection, `web_read` happy-path + error-path, keys-allowlist sync.
   Use `ScriptedStreamFn` for any agent-loop behavior assertions per
   `.claude/rules/testing/agent-loop-testing-philosophy.md`.
8. Update `DESIGN.md` + handbook doc. Run `just check`,
   `bun run typecheck`, and scoped `pytest`/`vitest` before pushing.

## Rules

- **Off by default.** Every provider is capability-gated on a key. No
  key configured anywhere → zero web tools in the list (today's
  behavior, preserved). The operator/partner opts in by setting a key.
- **No tools in providers.** Tool factories live in
  `backend/app/tools/`; composition lives in `backend/app/agents/tools.py`.
  Never import tool modules from `backend/app/providers/`.
- **Three-way key sync invariant.** `OVERRIDABLE_KEYS` (backend) +
  `_SETTINGS_ATTR_MAP` (backend) + `WORKSPACE_ENV_KEY_IDS` (frontend)
  must list the same keys. Drift = 400s on save.
- **Keep it tiny.** No crawler, no headless browser, no JS rendering.
  If a use case needs that, it goes through a user-configured external
  MCP server, not core.
- **Always cite.** The search/read tool descriptions must keep telling
  the model to cite result URLs.

## Related

- Current Exa wiring: `backend/app/tools/exa_search.py`,
  `exa_search_agent.py`, `backend/app/agents/tools.py:152`.
- Key resolution: `backend/app/infrastructure/keys.py`.
- External MCP extension path (the "heavier web" escape hatch):
  `build_external_mcp_tools` in `backend/app/tools/now.py`.
