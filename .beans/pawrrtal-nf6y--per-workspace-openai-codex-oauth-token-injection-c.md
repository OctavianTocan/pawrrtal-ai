---
# pawrrtal-nf6y
title: Per-workspace OPENAI_CODEX_OAUTH_TOKEN injection (currently logged, never applied)
status: todo
type: feature
priority: normal
created_at: 2026-05-27T13:24:32Z
updated_at: 2026-05-27T13:24:54Z
blocked_by:
    - pawrrtal-pu63
---

Deferred from pawrrtal-pu63 / pawrrtal-ujo8.

backend/app/core/providers/openai_codex/provider.py:106-111 currently:
    if cfg_dict.get('_openai_codex_override_token'):
        logger.info('openai_codex: workspace override token present for model=%s (full per-workspace auth injection coming in a follow-up)', self._model_id)

It only LOGS that an override exists; the token is never used to launch the spawned Codex app-server with a different identity. backend/app/core/providers/openai_codex/auth.py:97-156 build_app_server_config also has a placeholder comment about 'arrange for the app-server process to see that identity instead of (or in addition to) the user's global login'.

Result: workspace-scoped Codex identities silently fall back to ~/.codex/auth.json. Multi-tenant or multi-account workflows are broken.

## Todos
- [ ] Design: temp CODEX_HOME directory with synthesized auth.json per turn, vs. login_api_key on the AsyncCodex client
- [ ] Implement chosen mechanism in provider._ensure_codex
- [ ] Ensure temp dir is cleaned up after the AsyncCodex client closes (resource hygiene)
- [ ] Tests for override token resolution and isolation between workspaces
- [ ] Document the precedence (env > workspace .env > ~/.codex/auth.json)
