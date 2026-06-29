# Domain Knowledge

> Stable facts about Pawrrtal. Not procedures (skills), not personal taste
> (`memory/personal/PREFERENCES.md`), not time-bound events (episodic).
> Agents read this every session after PREFERENCES.

## Project overview

Self-hosted AI agent platform. Local planning specs live in gitignored `specs/` (not on GitHub).

| Area | Path | Role |
|------|------|------|
| Frontend | `frontend/` | Next.js 15 App Router — `app/`, `components/`, `features/` |
| Backend | `backend/` | Python FastAPI — canonical `:8000` until route parity |
| Effect strangler | `backend-ts/` | Effect v4 — `:8001` |
| Desktop | `electron/` | Wraps frontend; IPC via `frontend/lib/desktop.ts` |
| Agent brain | `.agent/` | Portable memory, skills, protocols |
| Tasks | `.beans/` | Local tracker (`beans` CLI) |
| Design system | `DESIGN.md` | Tokens in `frontend/app/globals.css` |
| Handbook | `frontend/content/docs/` | Versioned product + agent docs (not repo-root `/docs/`) |

## Agent brain layout

| What | Canonical path | Notes |
|------|----------------|-------|
| Skills | `.agent/skills/` | `bun run skill-gen:generate` writes here; run `agentic-stack sync-manifest` after tree changes |
| Rules | `.agent/rules/` | `.claude/rules`, `.agents/rules` symlink here |
| Preferences | `.agent/memory/personal/PREFERENCES.md` | Taste and workflow — not in AGENTS.md |
| Facts | `.agent/memory/semantic/DOMAIN_KNOWLEDGE.md` | Stable repo facts — not in AGENTS.md |
| Entry contract | `.agent/AGENTS.md` | Bootstrap + non-negotiables only |
| Root stub | `AGENTS.md` | Pointer to `.agent/AGENTS.md`; `CLAUDE.md` symlinks here |

**VPS host CLI:** `~/.local/bin/agentic-stack` (source at `/mnt/work/code/personal/agentic-stack`).

**Gitignored local paths (keep untracked):** `/docs/`, `/specs/`, `/reference/`, `.mcp.json`, `**/.mcp.json`, `config/mcporter.json`, `.beans/`, `GLOSSARY.md`, `WARP.md`, `.vscode/`, harness skill/rule mirrors.

## Architecture layers (sentrux)

| Stack | Layers |
|-------|--------|
| Frontend | `app → features → ai-elements → ui-primitives → lib` |
| Backend | `entry → api → crud → models → core` |
| Cross | `frontend/*` ⇏ `backend/*` |

```bash
just sentrux    # local check; CI posts PR comment on failure
```

**Provider tools:** implementations `backend/app/tools/` · adapters `backend/app/providers/` (never import tools) · turn composition `backend/app/agents/tool_surface.py`.

## Commands

Primary runner: `just`. A **gate** is a verification set that must be green.

```bash
just install
just dev                                  # :53001, :8000, :8001
just check                                # Biome, VCS-scoped
just lint-fix
just format
bun run typecheck
just sentrux
bun run design:lint
just install-paw && paw verify
cd backend && uv run alembic upgrade head   # after models.py changes
```

**Scoped tests:**

```bash
cd frontend && bun run test -- <file-or-pattern>
cd backend && uv run pytest <path> -q
cd backend-ts && bun run check && bun run typecheck && bun run test
```

## Local development

| Service | URL |
|---------|-----|
| Next.js | `http://localhost:53001` (`DEV_FRONTEND_PORT` in `scripts/dev-ports.ts`) |
| Python | `http://localhost:8000` |
| Effect TS | `http://localhost:8001` |

- `just dev` — all three; branch-scoped SQLite
- Plain `localhost` — no HTTPS/proxy hostnames in dev
- Unset stray shell `DATABASE_URL` before raw `uvicorn`
- Cookie auth works cross-port on localhost (`credentials: 'include'`, `COOKIE_SAMESITE=lax`, `COOKIE_SECURE=false`)

## Domain vocabulary

**Projects** = authenticated conversation folders at `/api/v1/projects` (`backend/app/projects/`). Not Tasks UI mocks or chat endpoints. Effect migration pilot = that CRUD slice on `:8001`.

## Auth (current Python world)

- **Post-login:** `LoginForm` uses `window.location.replace('/')`, not `router.push` — avoids 401 before `Set-Cookie` commits
- **Private deploy:** `ALLOWED_EMAILS` — empty admits any authed user; non-empty → 403 `This Pawrrtal deployment is private.`

**003 direction:** profiles via `X-Pawrrtal-Profile` + `Tailscale-User-Login`; see local gitignored `specs/003-pawrrtal-overhaul/research.md` §11. Do not extend cookie auth in new `003` slices.

## Production routing (current)

One Cloudflared hostname + Cloudflare Access. Browser same-origin `/api/v1`, `/auth`, `/users` → API to FastAPI `:8000`, else Next `:3000`. No `api.*` browser routing.

**003 direction:** `tailscale serve` (tailnet-only); web same-origin; Electron/Expo use tailnet base URL + `wss://…/rpc`.

## Effect TS (`backend-ts/`)

| Package | Role |
|---------|------|
| `@pawrrtal/api-core` | HttpApi groups, Domain, Errors, Api |
| `@pawrrtal/api` | Http*Live, Service, Repo, Modules/Layers |

- Auth: `apps/api/src/Modules/Authentication/` (`SessionStore` → Python `/users/me` until native session)
- Health: `GET /api/v1/health` — not `/api/v1/system/health`
- Pin `effect@4.0.0-beta.74`; API truth: `backend/vendor/effect-smol` (`ai-docs/`)
- `backend/vendor/effect` is v3 only
- Repo `just check` is VCS-scoped — run `cd backend-ts && bun run check` for full workspace lint

Deep guidance: `skills/domain-effect/SKILL.md`.

## Toolchain gotchas

| Topic | Detail |
|-------|--------|
| Root `tsconfig.json` | Orchestrator scripts only — excludes `frontend/`, `backend-ts/`, vendor |
| VS Code | Excludes `backend/vendor/`, `.worktrees/` from watch/search |
| Pre-commit | `backend/.venv/bin/python3 -m pre_commit` |
| Frontend Vitest | `bun run test -- <pattern>` — not `bun run test --run <path>` |
| Font stack | `Google Sans Flex`, `Google Sans`, `Helvetica Neue`, `sans-serif` — keep `DESIGN.md` + `globals.css` aligned |

## Code boundary example

```tsx
// Good — feature component, design tokens
export function ChatHeader({ title }: { title: string }): React.ReactElement {
  return <h1 className="text-foreground text-sm font-medium">{title}</h1>;
}

// Bad — cross-stack import, invented color
import { get_user } from "../../../backend/app/crud/user";
return <h1 className="text-gray-900">{title}</h1>;
```

Full authoring rules: `skills/code-quality/SKILL.md`.
