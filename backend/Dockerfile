# AI Nexus backend — Docker image
#
# Multi-stage build:
#   builder  — installs Python deps via uv into /app/.venv
#   runtime  — copies only the venv + source; no build tools in prod layer

# ---------------------------------------------------------------------------
# Stage 1: dependency builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv (fast pip replacement used by the project).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first so Docker can cache the install layer.
COPY pyproject.toml uv.lock ./

# Install all runtime deps into the project venv.
# --no-dev keeps test libs out of the production image.
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime image
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install the official Notion CLI (``ntn``) used by the Notion plugin.
# The plugin subprocesses ``ntn`` per tool call with the workspace`s
# token injected via ``NOTION_API_TOKEN``; see
# ``app/integrations/notion/ntn_client.py``.  Pinned by date so the
# install layer is reproducible — bump the env var to refresh.
ENV NTN_INSTALL_DATE=2026-05-15
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://ntn.dev | bash \
 && mv /root/.ntn/bin/ntn /usr/local/bin/ntn \
 && chmod +x /usr/local/bin/ntn \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /root/.ntn

# Grab the populated venv from the builder stage.
COPY --from=builder /app/.venv /app/.venv

# Activate the venv by prepending it to PATH.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application source.
COPY . .

# Create the default workspace directory so the volume mount has a
# target to bind to even if the host path doesn't pre-exist.
RUN mkdir -p /data/workspaces

EXPOSE 8000

# Start the server. ``alembic upgrade head`` is NOT in the prod CMD
# because the migration history currently has multiple heads (orphan
# ``000_initial_schema`` from PR #166 + ``013_notion_operation_logs``
# sibling of ``013_governance_and_jobs`` from PR #261) and would
# error out before uvicorn ever ran. Migrations are applied manually
# by the operator until the chain is consolidated to a single head.
#
# In the docker-compose dev stack this CMD is overridden by the
# compose command so --reload is active and the source volume mount
# is writable.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
