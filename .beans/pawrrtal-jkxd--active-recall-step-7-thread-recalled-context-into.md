---
# pawrrtal-jkxd
title: 'Active Recall step 7: thread recalled context into the system prompt'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:49Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-ikqt
---

## Goal

Make the system prompt actually include the recalled note.

## File

`backend/app/channels/_turn_runtime_context.py` → function `system_prompt_for_turn`

## 1. Add an optional kwarg

```python
def system_prompt_for_turn(
    workspace_root,
    *,
    model_id,
    tools,
    extra_context: str | None = None,
):
    ...
```

## 2. When `extra_context` is provided

Append this block **after** the existing workspace + runtime sections:

```
<recalled_context>
{extra_context}
</recalled_context>
```

(Two blank lines before the opening tag.)

## 3. Compatibility

Old signature must still work — `extra_context` defaults to `None`.

## 4. Update caller

Step 6's `turn_runner` should pass the assembled recalled-text string here.

## 5. Snapshot test

If there's a prompt-rendering snapshot test in `backend/tests/channels/`, run it. Update the snapshot only if the change is intentional (it is, here).
