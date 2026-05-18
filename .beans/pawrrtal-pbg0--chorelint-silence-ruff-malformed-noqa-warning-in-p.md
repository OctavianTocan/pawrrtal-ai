---
# pawrrtal-pbg0
title: 'chore(lint): silence ruff malformed-noqa warning in python_exec.py:349'
status: todo
type: task
priority: low
created_at: 2026-05-18T06:57:57Z
updated_at: 2026-05-18T06:57:57Z
---

`just check` emits:

```
warning: Invalid `# noqa` directive on app/core/tools/python_exec.py:349: expected code to consist of uppercase letters followed by digits only (e.g. `F401`)
```

The line is an explanatory comment about the `# noqa: S102` directive on the next line; ruff treats the literal token inside the explanation as a malformed directive. Rephrase the comment so ruff stops parsing it.

- [ ] Rewrite the comment on python_exec.py:349 (drop the literal `# noqa:` token, or escape it) so `just check` is clean.

Discovered while pushing the idle-pool fix (bean: pawrrtal-znfr).
