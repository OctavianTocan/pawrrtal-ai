---
name: single-lockfile-per-workspace
paths: ["pnpm-workspace.yaml", "**/package.json", "pnpm-lock.yaml", "yarn.lock"]
---
# One Lockfile per Monorepo — Root or Per-Workspace, Never Both

A monorepo should have exactly one lockfile at the root (pnpm, yarn berry) OR one per workspace (npm workspaces, legacy yarn). Never both. When a root lockfile and a workspace-level lockfile coexist, `install` resolves dependencies differently depending on which directory you run it from.

The symptoms are maddening: a package works in CI (which installs from root) but fails locally when a developer runs `npm install` inside a workspace directory. Or worse, the workspace lockfile pins `react@18.2.0` while the root lockfile pins `react@18.3.0`, causing duplicate React instances and the infamous "Invalid hook call" error.

For pnpm and yarn berry, the lockfile lives at the root. Period. Delete any `pnpm-lock.yaml` or `yarn.lock` files inside workspace packages. For npm, use `--workspaces` flag from root.

## Verify

"Is there a lockfile inside a workspace package directory? If so, is it intentional and is the CI install strategy consistent?"

## Patterns

Bad — lockfiles at both levels:

```text
monorepo/
├── pnpm-lock.yaml        # Root lockfile: react@18.3.0
├── pnpm-workspace.yaml
└── packages/
    └── web-app/
        ├── package.json
        └── pnpm-lock.yaml  # ❌ Workspace lockfile: react@18.2.0
```

```bash
# Developer runs install inside workspace
cd packages/web-app && pnpm install
# Uses workspace lockfile, gets react@18.2.0
# CI runs install from root
pnpm install --frozen-lockfile
# Uses root lockfile, gets react@18.3.0
# 💥 "Works on my machine" but fails in CI
```

Good — single lockfile at root:

```text
monorepo/
├── pnpm-lock.yaml        # Single source of truth
├── pnpm-workspace.yaml
└── packages/
    └── web-app/
        └── package.json   # No lockfile here
```

```bash
# Always install from root
pnpm install --frozen-lockfile
# Consistent resolution everywhere
```

Good — .gitignore nested lockfiles as a safety net:

```gitignore
# .gitignore at repo root
# Prevent accidental nested lockfiles
packages/*/pnpm-lock.yaml
packages/*/yarn.lock
packages/*/package-lock.json
```
