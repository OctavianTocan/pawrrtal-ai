# Pawrrtal backend — Docker image
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

# Install runtime OS deps:
#
#   * ``libpq5`` — the Postgres client library.  ``psycopg`` (we depend on
#     plain ``psycopg``, not ``psycopg[binary]``) loads ``libpq`` via
#     ctypes at import time.  Without it the container crashes at startup
#     with ``ImportError: no pq wrapper available`` from
#     ``psycopg.pq.import_from_libpq`` — every ``alembic upgrade head``
#     and every ``uvicorn`` boot fails because ``app/db.py`` imports
#     ``psycopg`` transitively through SQLAlchemy.  ``python:3.13-slim``
#     does not include ``libpq`` so we install it explicitly.
#   * ``ntn`` — the official Notion CLI used by the Notion plugin.
#     The plugin subprocesses ``ntn`` per tool call with the workspace's
#     token injected via ``NOTION_API_TOKEN``; see
#     ``app/plugins/notion/ntn_client.py``.  Pinned by date so the
#     install layer is reproducible — bump the env var to refresh.
#     The upstream installer (https://ntn.dev) writes ``ntn`` directly to
#     ``/usr/local/bin/ntn`` when run as root (the container build case),
#     so no follow-up ``mv`` is needed.  Earlier versions of this
#     Dockerfile tried to ``mv /root/.ntn/bin/ntn /usr/local/bin/ntn`` and
#     crashed the build with "No such file or directory" — bean
#     ``pawrrtal-ntn``.
#
# ``curl`` and ``ca-certificates`` are only needed for the ``ntn``
# installer, so we install them and ``apt-get purge`` curl afterwards
# to keep the runtime image small.  ``libpq5`` must NOT be purged.
ENV NTN_INSTALL_DATE=2026-05-15
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl ca-certificates \
 && curl -fsSL https://ntn.dev | bash \
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

# Run Alembic migrations then start the server.  The graph is
# single-head as of ``016_merge_notion_into_lcm_lineage`` so
# ``alembic upgrade head`` resolves unambiguously.  The advisory
# lock in ``alembic/env.py`` serialises concurrent invocations
# across rolling-deploy replicas.
#
# In the docker-compose dev stack this CMD is overridden by the
# compose command so --reload is active and the source volume mount
# is writable.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
