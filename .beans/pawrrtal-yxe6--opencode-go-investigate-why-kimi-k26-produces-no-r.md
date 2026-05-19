---
# pawrrtal-yxe6
title: 'OpenCode Go: investigate why Kimi K2.6 produces no response on Telegram'
status: todo
type: bug
priority: high
created_at: 2026-05-19T12:36:00Z
updated_at: 2026-05-19T12:37:56Z
---

User reports tapping Kimi K2.6 in /model and sending a message produces nothing. Likely cause: OPENCODE_API_KEY unset in env (config default ''), provider sends 'missing' key, gateway 401s, error is caught and yielded as text — but the legacy text-delivery bug (pawrrtal-s0w4) may swallow the error too. Verify with runtime logs.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/350

## Related

- Blocked-by-symptom: `pawrrtal-s0w4` (#346). The provider's error string may not surface until that legacy text bug is fixed.
