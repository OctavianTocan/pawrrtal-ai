---
name: ci-lockfile-frozen
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---
# Always Use --frozen-lockfile in CI

CI should never silently update the lockfile. If a developer adds a dependency to `package.json` but forgets to run `pnpm install` (or `yarn install`) locally and commit the updated lockfile, CI should fail — not silently generate a new lockfile and proceed.

Without `--frozen-lockfile`, CI resolves dependencies fresh, potentially getting different versions than local development. This creates "works on my machine" drift where CI installs `lodash@4.17.21` but the developer has `lodash@4.17.20` locked locally. Worse, different CI runs might resolve differently depending on when new versions are published.

Every package manager has a frozen mode: `pnpm install --frozen-lockfile`, `yarn install --frozen-lockfile`, `npm ci` (not `npm install`).

## Verify

"Does my CI install command use --frozen-lockfile (or npm ci)? Will it fail if the lockfile is outdated?"

## Patterns

Bad — CI silently updates lockfile:

```yaml
steps:
  - run: pnpm install
    # If lockfile doesn't match package.json, pnpm updates it
    # CI proceeds with different versions than developer intended
```

Bad — npm install instead of npm ci:

```yaml
steps:
  - run: npm install
    # Modifies package-lock.json in place
    # May resolve different versions than committed lockfile
```

Good — frozen lockfile in all package managers:

```yaml
# pnpm
steps:
  - run: pnpm install --frozen-lockfile

# yarn (classic and berry)
steps:
  - run: yarn install --frozen-lockfile

# npm — use `ci` subcommand, not `install`
steps:
  - run: npm ci
```

Good — in Dockerfiles too:

```dockerfile
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod
```
