---
name: returns-for-pawrrtal
description: Guardrail for dry-python/returns in pawrrtal. Use when an agent proposes Maybe, Result, IOResult, FutureResult, railway-oriented error handling, or adding the returns dependency.
paths:
  - "backend/**/*.py"
  - "backend/pyproject.toml"
---

# returns for pawrrtal

`dry-python/returns` is **not part of this backend**. The backend
restructure explicitly removed the dependency and chose idiomatic
Python error handling instead.

## Rule

Do not add `returns`, `Maybe`, `Result`, `IOResult`, or
`FutureResult` to Pawrrtal code. Do not pin `returns` in
`backend/pyproject.toml`, enable the returns mypy plugin, or wrap
provider/chat/router contracts in railway containers.

Use the local patterns instead:

| Need | Use |
|---|---|
| Route failures | `HTTPException` at the route boundary |
| Provider/runtime failures | Narrow exception classes plus clear SSE/error events |
| Optional database rows | `T | None` with explicit guard clauses |
| Validation | Pydantic models, typed helpers, and explicit exceptions |
| Async multi-step flows | Small helpers with `try`/`except` at the orchestration boundary |

## Review checklist

- Reject new `from returns...` imports.
- Reject `Result[T, E]`, `Maybe[T]`, `IOResult[...]`, and
  `FutureResult[...]` signatures.
- Reject mypy plugin entries for `returns.contrib.mypy.returns_plugin`.
- If a proposal says "pilot returns", redirect it to a separate design
  discussion before code changes.

The previous pilot notes are archived in git history; they are not an
active implementation plan.
