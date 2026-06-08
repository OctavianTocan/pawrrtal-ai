# List available recipes
default:
    @just --list

# Start frontend (Next.js) and backend (FastAPI) dev servers
dev:
    bun run dev.ts

# Same as `just dev`, but force the Telegram bot to run in polling mode.
# Use this when iterating on the Telegram channel locally so getUpdates
# stays active even if a stale prod webhook is registered against the
# bot token. Requires TELEGRAM_BOT_TOKEN + TELEGRAM_BOT_USERNAME in
# backend/.env.
dev-telegram:
    TELEGRAM_MODE=polling bun run dev.ts

# Run the Pawrrtal Agent CLI (paw) against the local backend.
# Examples:
#   just paw doctor
#   just paw doctor --json
#   just paw doctor --profile staging
paw *ARGS:
    @scripts/paw {{ARGS}}

# Install the Paw launcher on PATH for invoking `paw` from any directory.
install-paw:
    mkdir -p "$HOME/.local/bin"
    ln -sf "{{justfile_directory()}}/scripts/paw" "$HOME/.local/bin/paw"
    @printf 'Installed paw launcher at %s\n' "$HOME/.local/bin/paw"

# Fast local environment check for agents and CI smoke loops. This does not
# start servers; it verifies writable cache/config paths, binaries, and ports.
env-check:
    PAW_CONFIG_DIR="{{justfile_directory()}}/.cache/paw" UV_CACHE_DIR="{{justfile_directory()}}/.cache/uv" XDG_CACHE_HOME="{{justfile_directory()}}/.cache/xdg" scripts/paw env check

# Start, probe, and stop the full local app. Use this before claiming that
# the developer startup path works end-to-end.
smoke-dev:
    PAW_CONFIG_DIR="{{justfile_directory()}}/.cache/paw" UV_CACHE_DIR="{{justfile_directory()}}/.cache/uv" XDG_CACHE_HOME="{{justfile_directory()}}/.cache/xdg" scripts/paw project preflight
    PAW_CONFIG_DIR="{{justfile_directory()}}/.cache/paw" UV_CACHE_DIR="{{justfile_directory()}}/.cache/uv" XDG_CACHE_HOME="{{justfile_directory()}}/.cache/xdg" scripts/paw project up --boot-timeout 45
    PAW_CONFIG_DIR="{{justfile_directory()}}/.cache/paw" UV_CACHE_DIR="{{justfile_directory()}}/.cache/uv" XDG_CACHE_HOME="{{justfile_directory()}}/.cache/xdg" scripts/paw project status
    PAW_CONFIG_DIR="{{justfile_directory()}}/.cache/paw" UV_CACHE_DIR="{{justfile_directory()}}/.cache/uv" XDG_CACHE_HOME="{{justfile_directory()}}/.cache/xdg" scripts/paw project down

# Auto-generate conventional commit via Gemini
commit *ARGS:
    cd backend && uv run python -m app.cli.commit {{ARGS}}

# Push to remote
push:
    git push

# Lint check (read-only) — Biome (JS/TS) + ruff (Python)
lint: lint-py
    bunx --bun @biomejs/biome@2.4.16 check --no-errors-on-unmatched --files-ignore-unknown=true .

# Lint and auto-fix — Biome (JS/TS) + ruff (Python)
lint-fix: lint-py-fix
    bunx --bun @biomejs/biome@2.4.16 check --write --no-errors-on-unmatched --files-ignore-unknown=true .

# Format — Biome (JS/TS) + ruff (Python)
format: format-py
    bunx --bun @biomejs/biome@2.4.16 format --write .

# Check (read-only) — Biome + ruff lint + ruff format check + TS structural gates
check: check-py
    bunx --bun @biomejs/biome@2.4.16 check --no-errors-on-unmatched --files-ignore-unknown=true .
    node scripts/check-file-lines.mjs
    node scripts/check-nesting.mjs

# --- Python: ruff (lint + format) and mypy (type check) ----------------------

# Lint Python with ruff (read-only)
lint-py:
    cd backend && uv run ruff check .

# Lint Python and auto-fix safe issues
lint-py-fix:
    cd backend && uv run ruff check --fix .

# Format Python with ruff
format-py:
    cd backend && uv run ruff format .

# Check Python (lint + format check, no writes) — used by `just check`
check-py:
    cd backend && uv run ruff check .
    cd backend && uv run ruff format --check .

# Static type-check — Python (mypy) + Effect TS workspace (tsc). Gating — keep green.
typecheck:
    cd backend && uv run mypy
    cd backend-ts && bun run typecheck

# Security scan with bandit (Python). Findings here are real and should fail.
security-py:
    cd backend && uv run bandit -r app -c pyproject.toml --quiet

# Full health gate: ruff + biome + bandit + mypy. Use before pushing.
check-all: check security-py typecheck

# --- Pre-commit hooks --------------------------------------------------------

# Install pre-commit git hooks (run once after cloning the repo)
install-hooks:
    cd backend && uv run pre-commit install --install-hooks

# Update all pre-commit hook versions to their latest release
update-hooks:
    cd backend && uv run pre-commit autoupdate

# Run pre-commit on staged files (mimics what runs on `git commit`)
pre-commit:
    cd backend && uv run pre-commit run

# Run pre-commit across the entire repo (use before opening a PR)
pre-commit-all:
    cd backend && uv run pre-commit run --all-files

# Check application architecture with sentrux
sentrux:
    bash scripts/sentrux-check.sh

# Enforce backend layer ordering + boundaries (mirrors sentrux's Pro-gated
# rules). Config: backend/.importlinter
arch-be:
    cd backend && uv run lint-imports --config .importlinter

# Enforce frontend layer ordering + boundaries (mirrors sentrux's Pro-gated
# rules). Config: frontend/.dependency-cruiser.cjs
arch-fe:
    cd frontend && bun run arch:check

# Full architectural gate: sentrux (quality + 4 OSS rules) + the 13 rules
# OSS sentrux can't enforce (split between import-linter for be + depcruise
# for fe). Run this before opening a PR.
arch: sentrux arch-be arch-fe

# TSDoc coverage audit — report exported declarations missing JSDoc comments
# Usage: just check-docs [path-prefix]  e.g. just check-docs frontend/lib
check-docs *ARGS:
    bun run scripts/check-docs.ts {{ARGS}}

# Run backend pytest suite
test-backend:
    uv run --project backend pytest backend/tests

# Run frontend Vitest suite (CI-style, no watcher)
test-frontend:
    cd frontend && bun run test

# Run backend-ts Vitest suite (CI-style, no watcher)
test-backend-ts:
    cd backend-ts && bun run test

# Run frontend Vitest with v8 coverage; report drops under frontend/coverage/
test-coverage:
    cd frontend && bun run test:coverage

# Run all three suites. Use before pushing — local + CI parity (#271).
test: test-backend test-backend-ts test-frontend

# Playwright E2E suite (frontend/e2e/). Requires backend + frontend dev
# servers to be already running on the standard ports — start them with
# `just dev` in another terminal first. Uses the dev-admin login fixture
# (no UI signup), per the project's API-setup-not-UI rule.
e2e:
    cd frontend && bunx --bun playwright install --with-deps chromium
    cd frontend && bunx --bun playwright test

# --- Stagehand E2E (LLM-driven, lives under frontend/e2e/stagehand) --------

# Run the Stagehand AI-driven end-to-end suite. Requires `just dev` already
# running (frontend + backend) and one of OPENAI_API_KEY / ANTHROPIC_API_KEY
# / GOOGLE_API_KEY set so Stagehand has an LLM to drive `act` / `extract`.
# Tests are slow (10–60s each) and cost real money — keep them out of
# `just check`; run on demand.
stagehand-e2e:
    cd frontend && bunx --bun playwright install --with-deps chromium
    cd frontend && bun run e2e:stagehand

# Install all dependencies (frontend + backend) and git hooks
install:
	bash -c 'if git rev-parse --git-dir >/dev/null 2>&1; then git submodule update --init --recursive; fi'
	bun install
	cd backend-ts && bun install
	uv sync --project backend --group dev
	just install-hooks

# Show active tasks from Notion
tasks:
    bun run tasks.ts

# Remove build caches
clean:
    rm -rf frontend/.next
    find . -type d -name __pycache__ -exec rm -rf {} +
