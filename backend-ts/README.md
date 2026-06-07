# Pawrrtal backend (Effect TypeScript)

Strangler companion to the Python FastAPI app on port `8000`. This workspace uses **Effect v4** from the vendored [`effect-smol`](../backend/vendor/effect-smol) tree (not npm `effect@3`).

## Layout

| Package | Role |
|---------|------|
| `packages/api-core` | Shared API schemas, `HttpApi` groups, domain errors (no Node I/O) |
| `apps/api` | Node HTTP server, SQL, auth middleware, route handlers |

Pattern mirrors `backend/vendor/comcom` (`@comcom/api-core` + `@apps/api`) but targets Effect v4 imports (`effect/unstable/httpapi`, `@effect/platform-node`, etc.).

Definitions and file conventions: **[CONVENTIONS.md](./CONVENTIONS.md)** (start there when adding a module).

## Vendor pin

| Field | Value |
|-------|--------|
| Submodule | `backend/vendor/effect-smol` |
| Branch | `main` |
| Pinned commit | `1fdd9aee` (update this line when bumping the submodule) |
| Package version | `4.0.0-beta.74` (see `packages/effect/package.json` in the submodule; npm deps use the same version) |

Runtime dependencies install from npm at the same version as the submodule (`4.0.0-beta.74`). The vendor tree is for reading implementations and `ai-docs` walkthroughs — not linked with `file:` (effect-smol uses internal `workspace:^` and does not install cleanly as a path dependency under Bun).

## Install

From the repo root (recommended — also initializes `backend/vendor/effect-smol`):

```bash
git submodule update --init backend/vendor/effect-smol
just install
just check
just typecheck
```

`just install` runs `bun install` at the root and in `backend-ts/`. Lint, format, and structural gates use the same repo-wide commands as the frontend (`just check`, `just lint-fix`, `just format`). TypeScript checking is part of `just typecheck` alongside Python mypy.

## Dev ports

| Service | Port |
|---------|------|
| Python FastAPI | `8000` (`DEV_BACKEND_PORT` in `scripts/dev-ports.ts`) |
| Effect TS API (planned) | `8001` (`DEV_BACKEND_TS_PORT`) |

Python stays canonical until route parity and tests pass on the TS stack.
