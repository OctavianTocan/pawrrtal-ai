# Backend vendor trees

Reference and dependency sources for the Python backend and the planned Effect TypeScript backend.

| Path | What it is | Use in Pawrrtal |
|------|------------|-----------------|
| `effect-smol/` | **Effect v4** ([Effect-TS/effect-smol](https://github.com/Effect-TS/effect-smol)), git submodule on `main` | **Source of truth** for new Effect TS code. API docs and walkthroughs live under `effect-smol/ai-docs/`. Pawrrtal wires packages via `file:` deps in `backend-ts/`. |
| `effect/` | Effect **v3** copy (`effect@3.21.2`), not a submodule | Do **not** use for v4 work. Historical / local reference only. |
| `comcom/` | Adaptive Thinking monorepo (Effect **v3** + layout patterns) | **Folder layout** reference (`packages/api-core`, `apps/api`). Do not copy v3 `@effect/platform` imports into Pawrrtal v4 code. |
| `codex/` | OpenAI Codex CLI submodule | Agent tooling, unrelated to Effect. |

## Pinning `effect-smol`

After updating the submodule:

```bash
cd backend/vendor/effect-smol && git fetch origin main && git checkout origin/main
cd ../../.. && git add backend/vendor/effect-smol
```

Record the pinned commit in `backend-ts/README.md` when you bump the vendor tree.

## Canonical v4 HTTP walkthrough

`backend/vendor/effect-smol/ai-docs/src/51_http-server/10_basics.ts` — `HttpApiBuilder`, `HttpRouter.serve`, `NodeHttpServer`.
