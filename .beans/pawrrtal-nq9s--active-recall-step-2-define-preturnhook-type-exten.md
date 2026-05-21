---
# pawrrtal-nq9s
title: 'Active Recall step 2: define PreTurnHook type + extend Plugin dataclass'
status: completed
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:40Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-9iae
---

## Goal

Let any plugin say "run me **before** the main AI runs".

## File

`backend/app/core/plugins/types.py`

## 1. Add a small dataclass

```python
@dataclass(frozen=True)
class PreTurnHookContext:
    conversation_id: UUID
    user_id: UUID
    workspace_id: UUID
    workspace_root: Path
    question: str
    model_id: str | None
```

## 2. Add a type alias

```python
PreTurnHook = Callable[
    [PreTurnHookContext, AsyncSession],
    Coroutine[Any, Any, str | None],
]
```

A hook = async function. Gets context + db session. Returns either a short note or `None`.

## 3. Extend the `Plugin` dataclass

```python
pre_turn_hooks: tuple[PreTurnHook, ...] = field(default_factory=tuple)
```

## Compatibility

Existing plugins (e.g. `notion_plugin`) don't set `pre_turn_hooks` → must still work.

## Tests

If `backend/tests/core/plugins/test_types.py` exists, add a small test. Otherwise skip.
