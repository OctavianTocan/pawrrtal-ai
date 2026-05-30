# Pawrrtal — Claude Code Guide

## Stack
- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui, Biome (linting + formatting), Bun
- **Backend**: Python, FastAPI, SQLAlchemy (async), Alembic migrations, Agno (AI sessions), FastAPI-Users
- **Monorepo**: top-level `justfile` for orchestration

## Commands
```bash
# Frontend
cd frontend && bun run dev        # dev server
cd frontend && bun run build      # production build
cd frontend && bun run check      # biome lint + format check
cd frontend && bun run format     # biome format (write)
cd frontend && bun run lint       # biome lint (write)

# Backend
cd backend && uv run uvicorn app.main:app --reload   # dev server
cd backend && uv run alembic upgrade head            # run migrations
cd backend && uv run alembic revision --autogenerate -m "desc"  # new migration

# Root
just dev     # starts both frontend + backend
```

## Code Style
- **TypeScript**: strict mode, explicit return types on all exports, TSDoc on all exported interfaces/props
- **React**: no default exports for non-page components (named exports only); extract pure functions outside components
- **Biome**: enforced — run `bun run check` before committing
- **Python**: type hints on all functions, docstrings on all classes and public functions

## Architecture
- Feature folders under `frontend/features/` own their container + view + hooks
- Presentational components go in `frontend/components/`
- API endpoints in `backend/app/api/` — one file per domain
- DB models in `backend/app/models.py`, schemas in `backend/app/schemas.py`
- Mutations always go through React Query (`@tanstack/react-query`)

## Backend restructure (in progress, branch `restructure/backend-domains`)

The backend is being restructured into a hybrid `domains/ + infrastructure/`
layout. Spec at `docs/superpowers/specs/2026-05-28-backend-restructure-design.md`,
plan at `docs/superpowers/plans/2026-05-28-backend-restructure.md`. Until the
restructure lands fully:

- New plumbing (lifecycle, middleware, app factory) goes under
  `backend/app/infrastructure/`. The `LifecycleRegistry` at
  `infrastructure/lifecycle.py` is the seam for new startup hooks — add one
  file under `infrastructure/startup/<concern>.py` rather than editing the
  lifespan body in `main.py`.
- Typed exception tree lives at `app/exceptions.py` (roots) plus
  per-domain `<domain>/exceptions.py`. New error sites raise these; do not
  introduce new uses of the (now-removed) `returns` library.
- Voice transcription (`/api/v1/stt`, the 4-backend transcriber, telegram
  voice-attachment transcription) was removed in the restructure; voice
  messages reach the agent as a metadata-only annotation. Webhooks
  (`integrations/webhooks/`) and the empty `integrations/notion/` stub
  were also removed.
- xAI auth (OAuth device-code + credential resolution) lives under
  `app/providers/xai/`, not `app/integrations/xai/`.

## Rules
Claude Code rules live in `.claude/rules/`. They fire automatically based on file path globs. Every rule has a `Verify` question — use it before committing.

## Modals & Bottom Sheets
- All modal, dialog, and bottom-sheet UI is built on `@octavian-tocan/react-overlay`.
- Compose through `@/components/ui/app-dialog` (`AppDialog`) — it renders `Modal` on desktop and `BottomSheet` on mobile via `useIsMobile` (implementation: `responsive-modal.tsx`).
- Reach for the raw `Modal` / `BottomSheet` / `ModalWrapper` exports only for viewport-specific surfaces.
- shadcn `Dialog` / `AlertDialog` / `Sheet` in `components/ui/` are low-level primitives for other shadcn components — do not import them into feature code.
- Rule: `.claude/rules/react/use-octavian-overlay-for-modals.md`.

## Stagehand browser automation (MCP + docs)

- **Documentation index:** https://docs.stagehand.dev/llms.txt — fetch this first to discover doc pages before deeper exploration.
- **Project MCP servers** (see `.mcp.json` and `config/mcporter.json`): **stagehand-docs** (`https://docs.stagehand.dev/mcp`), **context7** (`npx -y @upstash/context7-mcp`, [repo](https://github.com/upstash/context7)), **deepwiki** (`https://mcp.deepwiki.com/mcp`, [site](https://mcp.deepwiki.com/)).
- **Claude rules:** `.claude/rules/stagehand/stagehand-documentation-and-mcp.md` (session-wide doc/MCP workflow) and `.claude/rules/stagehand/stagehand-v3-typescript-patterns.md` (path-scoped API patterns for `**/*stagehand*`, `**/e2e/**`, `**/playwright/**`).

## Git
- Branch from `v1.1` for v1.2 features, from `v1.2` for v1.3
- Commit with conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`
- Never commit broken builds
