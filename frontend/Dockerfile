# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────
# Next.js production image
#
# Multi-stage build:
#   deps    — install workspace dependencies with bun (BuildKit cache mount)
#   builder — compile the Next.js app (output: standalone)
#   runner  — minimal Node runtime image serving server.js + sharp for
#             native Next.js image optimisation
#
# Build-time ARG:
#   NEXT_PUBLIC_BROWSER_API_BASE  defaults to same-origin browser API calls.
#                                Override only for browser-direct backends.
#
# Notes:
#   - Node version is pinned to a specific minor for reproducibility.
#     Bump the tag deliberately, never rely on "latest minor".
#   - sharp is installed in the runner stage so Next.js can do native
#     AVIF / WebP conversion without falling back to the slow JS path.
#   - BuildKit cache mount (`--mount=type=cache`) cuts `bun install` from
#     minutes to seconds on rebuilds. Requires DOCKER_BUILDKIT=1 (default
#     for `docker buildx`) or `# syntax=docker/dockerfile:1.x` (above).
# ─────────────────────────────────────────────────────────────

# ── Deps ────────────────────────────────────────────────────
FROM oven/bun:1.1.42-alpine AS deps
WORKDIR /app

# Workspace manifests first so the install layer caches on dep changes only.
COPY package.json bun.lock ./
# lib/ contains vendored submodule packages (react-chat-composer, etc.)
COPY lib/ ./lib/

# Cache the bun store across builds. The lockfile is still --frozen so any
# drift between bun.lock and package.json fails the build deterministically.
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

# ── Builder ─────────────────────────────────────────────────
FROM oven/bun:1.1.42-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# NEXT_PUBLIC_* must be set BEFORE `bun run build` because Next.js inlines
# these values into the client bundle at build time.
#
# Client-side browser calls hit /api/* via Nginx (same origin). Server-side
# Next.js calls use BACKEND_INTERNAL_URL at runtime.
ARG NEXT_PUBLIC_BROWSER_API_BASE=""
ENV NEXT_PUBLIC_BROWSER_API_BASE=$NEXT_PUBLIC_BROWSER_API_BASE

RUN bun run build

# ── Runner ──────────────────────────────────────────────────
# Plain Node image for runtime. Smaller than bun, and the standalone
# server.js was emitted assuming a Node runtime.
FROM node:22.11-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# libc6-compat is required by sharp on Alpine; wget is in busybox already
# (used by the Compose healthcheck).
RUN apk add --no-cache libc6-compat

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# next.config.ts sets output: 'standalone' so the build emits a
# self-contained server bundle + trimmed node_modules slice.
COPY --from=builder /app/public                                ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static    ./.next/static

# Install sharp into the standalone tree so Next.js Image picks it up.
# Without sharp, Next.js falls back to a slower JS-only image pipeline
# and logs a warning on every optimised image request in production.
RUN npm install --omit=dev --no-save --prefix . sharp@^0.33 \
 && chown -R nextjs:nodejs node_modules

USER nextjs

EXPOSE 3000

# Liveness check: the standalone server responds 200 on / once ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget --spider -q http://localhost:3000/ || exit 1

# server.js is the standalone entrypoint emitted by Next.js output: standalone
CMD ["node", "server.js"]
