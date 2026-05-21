---
# pawrrtal-l3fi
title: 'Workshop OTel: thinking events filtered out before observability hook runs'
status: todo
type: bug
priority: high
created_at: 2026-05-19T12:35:50Z
updated_at: 2026-05-19T12:37:51Z
---

turn_runner._guarded_stream applies _should_deliver_event before event_hooks fire. Telegram default verbose_level=1 drops 'thinking' events at chat_aggregator.should_emit_event, so workshop_event_hook never receives them and LLM spans in Raindrop Workshop have no gen_ai.thinking.delta events.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/347

## Evidence

- Filter site: `backend/app/channels/turn_runner.py:273-281`
- Hook fan-out (only reached when filter passes): same file, line 278
- Filter logic: `backend/app/core/chat_aggregator.py:66-86` (drops 'thinking' for verbose < 2)
- Telegram default: `backend/app/core/config.py:302` (telegram_verbose_default=1)
- Observability surface (would have received the event): `backend/app/core/observability/workshop.py:279-280` + `_recorders.py:96`
