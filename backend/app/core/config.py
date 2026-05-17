"""Application settings."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. This class uses Pydantic's BaseSettings to automatically read environment variables and provide type validation."""

    # Load environment variables from a .env file in the current directory, with UTF-8 encoding. This allows you to define your settings in a .env file instead of setting them directly in the environment.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # The URL for the database connection.
    database_url: str = ""
    # The secret key used for signing authentication tokens. This should be set to a secure random value in production.
    auth_secret: str
    # The environment in which the application is running. Can be "dev" for development or "prod" for production.
    env: str = "dev"
    # The API key for Google services.
    google_api_key: str
    # Encryption key for per-user workspace .env files.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    workspace_encryption_key: str
    # OAuth token used by the Claude Agent SDK to authenticate the bundled
    # Claude Code CLI subprocess. Optional — only required when a chat
    # request resolves to a Claude model. Generate with `claude setup-token`.
    claude_code_oauth_token: str = ""
    # API key for Exa (https://exa.ai). Powers the provider-agnostic
    # `exa_search` tool wired into chat providers.
    # Leave empty to disable web search; the tool returns a clear
    # "not configured" error rather than crashing the turn.
    exa_api_key: str = ""
    # API key for xAI (https://x.ai). Powers the speech-to-text proxy
    # endpoint at POST /api/v1/stt — the frontend records audio with the
    # browser's MediaRecorder, uploads the blob, and the backend forwards
    # it to https://api.x.ai/v1/stt. Leave empty to disable voice input
    # (the endpoint returns 503 with a clear "not configured" message).
    xai_api_key: str = ""
    # CORS
    cors_origins: list[str]
    cors_origin_regex: str | None = r"^https:\/\/.*\.vercel\.app$"
    # The domain to set for cookies (e.g., "example.com"). This is important for authentication cookies to work correctly across subdomains.
    cookie_domain: str | None = None
    # Controls cross-site cookie behavior ("lax", "strict", "none"). Set to "none" (with secure=True) to allow auth across completely different domains (like Vercel previews).
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # If True, forces the Secure flag on cookies. If False, forces HTTP allowed. If None, auto-detects based on is_production.
    cookie_secure: bool | None = None
    # The base directory where workspaces will be stored. Each workspace can contain files, configurations, and other resources specific to a user's project or environment.
    workspace_base_dir: str = "/data/workspaces"

    # ── Agent loop safety ────────────────────────────────────────────────
    # See backend/app/core/agent_loop/types.py::AgentSafetyConfig for the
    # behavioural contract.  All four caps accept None to opt out of the
    # specific guard (set the matching env var to an empty string in
    # ``.env`` and Pydantic will coerce to None — or pass --None).

    # Hard cap on assistant turns per chat invocation.  Default 25 covers
    # multi-step refactors and deep research; runaway tool loops trip
    # well before this.  Set 0/empty to disable.
    agent_max_iterations: int | None = 25

    # Wall-clock budget (seconds) for one chat invocation.  Counted from
    # entry to ``agent_loop``.  Default 300 (5 min); raise for long-
    # running automations.
    agent_max_wall_clock_seconds: float | None = 300.0

    # Back-to-back stream errors before the loop bails.  Resets on any
    # successful stream.  Default 3 — covers transient provider blips
    # while still bailing out of a real outage quickly.
    agent_max_consecutive_llm_errors: int | None = 3

    # Back-to-back tool failures before the loop bails.  Resets on any
    # successful tool call.  Default 5.
    agent_max_consecutive_tool_errors: int | None = 5

    # Base backoff (seconds) between LLM retries; doubles each retry,
    # capped at 30s inside the loop.  Set 0 for instant retry.
    agent_llm_retry_backoff_seconds: float = 1.0
    # Admin user credentials (for testing).
    admin_email: str | None = None
    admin_password: str | None = None

    # --- Access control ------------------------------------------------------
    # Optional bearer token all clients must supply in the X-Pawrrtal-Key
    # request header. When set, any request missing or carrying the wrong
    # value is rejected with 401 before auth runs. Leave empty to disable
    # (useful in local dev or for the public demo instance where
    # ALLOWED_EMAILS is the only gate). Generate with: openssl rand -hex 32
    backend_api_key: str = ""

    # Comma-separated list of email addresses that are allowed to use this
    # backend. When non-empty, authenticated users whose email is not on
    # the list receive a 403 on any authenticated endpoint. Google and Apple
    # OAuth both deliver verified emails, so this check is reliable across
    # all login methods (Google, Apple, password).
    # Example: ALLOWED_EMAILS=you@example.com,partner@example.com
    # Leave empty to allow all authenticated users (open / demo mode).
    allowed_emails: str = ""

    @property
    def allowed_emails_set(self) -> frozenset[str]:
        """Return the normalised email allowlist as a frozen set."""
        if not self.allowed_emails:
            return frozenset()
        return frozenset(
            addr.strip().lower() for addr in self.allowed_emails.split(",") if addr.strip()
        )

    # --- OAuth: Google ---
    # Set both to enable the "Continue with Google" button on the login
    # page. When either is empty the start endpoint returns 503 with a
    # clear "not configured" message. Get these from the Google Cloud
    # Console: https://console.cloud.google.com/apis/credentials
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Where Google redirects back to after auth. Must be an authorized
    # redirect URI on the OAuth client. Default targets local dev.
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    # --- OAuth: Apple ---
    # Apple Sign In requires four pieces: services ID (acts as client_id),
    # team ID, key ID, and the .p8 private key contents. Set all four to
    # enable the "Continue with Apple" button.
    apple_oauth_client_id: str = ""
    apple_oauth_team_id: str = ""
    apple_oauth_key_id: str = ""
    apple_oauth_private_key: str = ""
    apple_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/apple/callback"

    # Where to send the user after a successful OAuth sign-in. Override in
    # production to point at the deployed frontend (e.g. https://app/...).
    oauth_post_login_redirect: str = "http://localhost:3001/"

    # --- Channels: Telegram --------------------------------------------------
    # Bot token issued by @BotFather. Leaving this empty disables the
    # whole Telegram channel — the link/unbind routes report "not
    # configured" and the bot adapter never starts. Use a separate dev
    # bot for local work so a busted handler can't spam real users.
    telegram_bot_token: str = ""
    # Username of the bot the token belongs to (without the leading @).
    # Surfaced in the link-code response so the frontend can render a
    # `https://t.me/<bot>?start=<code>` deep link without hard-coding.
    telegram_bot_username: str = ""
    # How the bot receives updates. "polling" works everywhere (no public
    # URL needed) and is the default so local dev just works. "webhook"
    # is the prod path and requires `telegram_webhook_url`.
    telegram_mode: Literal["polling", "webhook"] = "polling"
    # Public HTTPS URL Telegram should POST updates to when running in
    # webhook mode. Ignored in polling mode.
    telegram_webhook_url: str = ""
    # Optional shared secret Telegram sends in the
    # `X-Telegram-Bot-Api-Secret-Token` header on every webhook delivery
    # so the receiving FastAPI route can drop forgeries.
    telegram_webhook_secret: str = ""

    # Per-user chat rate limit (requests per 60-second rolling window).
    # Zero disables the limit entirely — useful for local dev.  Production
    # deployments should pick a value that matches the operator's monthly
    # token budget divided by expected request count.
    chat_rate_limit_per_minute: int = 0

    # When True, ConversationRead 422s on a non-canonical stored
    # model_id. When False (operator escape hatch), the bad value falls
    # back to ``catalog.default_model().id`` and the row is logged.
    strict_conversation_read_validation: bool = True

    # Demo-mode toggle.  When true, the backend refuses to start the
    # Telegram channel (which would expose a public reply surface) and
    # the chat router enforces the demo restrictions documented in
    # docs/deployment/demo-mode.md.  Default false so production /
    # private deploys are never accidentally demo-shaped.
    demo_mode: bool = False

    # ── Governance: cost tracking + audit log (PRs 02, 04) ───────────────
    # When False, the cost middleware short-circuits and the per-turn
    # ledger writes are skipped — useful for local dev and tests.
    cost_tracker_enabled: bool = True
    # Per-request hard cap forwarded to the Claude SDK as
    # ``max_budget_usd``; the agent loop's pre-turn safety check mirrors
    # it for Gemini. Zero disables (the SDK treats 0 as unlimited).
    cost_max_per_request_usd: float = 1.0
    # Per-user rolling window cap enforced by ``CostBudgetMiddleware``.
    # Zero disables the user-level cap; the per-request cap still applies.
    cost_max_per_user_daily_usd: float = 10.0
    # Length of the rolling window (hours) used for the per-user cap.
    cost_reset_window_hours: int = 24

    # When False, the audit logger no-ops and the audit API returns 404.
    # The dashboard query still works against historical rows.
    audit_log_enabled: bool = True
    # Retention for audit rows. The purge job runs from the scheduler
    # lifespan (PR 12); zero disables the purge so rows live forever.
    audit_log_retention_days: int = 90

    # Master switch for the secret-redaction pass over log lines and
    # persisted tool inputs (PR 02). Off only for adversarial test runs.
    secret_redaction_enabled: bool = True

    # ── Tools: in-process Python execution ───────────────────────────────
    # When True, ``build_agent_tools`` appends the ``python`` tool which
    # runs LLM-supplied source via ``exec()`` in the FastAPI worker
    # process.  Off by default: the execution is *not* sandboxed and the
    # operator opts in explicitly per the threat model documented in
    # ``app/core/tools/python_exec.py``.
    virtual_python_enabled: bool = False
    # Wall-clock cap (seconds) for one ``python`` tool call.  The
    # awaiter is cancelled at this point; runaway code holds the worker
    # thread until it returns (see module docstring).
    virtual_python_timeout_seconds: float = 30.0
    # Maximum bytes of captured stdout + stderr returned to the model.
    # Head + tail truncation preserves tracebacks at the tail.
    virtual_python_output_cap_bytes: int = 32_000

    # ── Governance: Claude SDK options (PR 05) ───────────────────────────
    # When True, the Claude provider passes the SDK's ``sandbox`` option
    # to the bundled CLI subprocess. The CLI's macOS Seatbelt sandbox
    # is the strongest containment for the agent's filesystem reach.
    claude_sandbox_enabled: bool = False
    # When True, Bash invocations are auto-allowed inside the sandbox.
    # Pairs with the can_use_tool gate (PR 03) so we never auto-allow
    # commands that escape the workspace.
    claude_sandbox_auto_allow_bash: bool = True
    # Comma-separated bash commands the SDK should exclude from the
    # sandbox auto-allow list (e.g. ``sudo,ssh``). Parsed lazily so the
    # env var stays a single-line string.
    claude_sandbox_excluded_commands: str = "sudo,ssh,scp,rsync"

    # ── Governance: retry-with-backoff (PR 05) ───────────────────────────
    # Mirrors CCT's transient-error retry. Capped to keep a single turn
    # from spending minutes on a flapping network.
    claude_retry_max_attempts: int = 3
    claude_retry_base_delay_seconds: float = 1.0
    claude_retry_max_delay_seconds: float = 30.0
    claude_retry_backoff_factor: float = 2.0

    # ── Governance: workspace context (PR 06) ────────────────────────────
    # When True, the chat router calls
    # ``governance.workspace_context.load_workspace_context`` to read
    # CLAUDE.md/AGENTS.md/SOUL.md + skills/ + settings.json and assemble
    # the unified system prompt + tool allowlist.
    workspace_context_enabled: bool = True
    # Workspace-relative path to the skills directory. Each subdirectory
    # is expected to contain a ``SKILL.md`` file.
    workspace_skills_dir_name: str = ".claude/skills"
    # Workspace-relative path to the Claude Code-compatible settings
    # file. When present, ``permissions.allow``/``deny`` shape the
    # ``can_use_tool`` gate.
    workspace_settings_filename: str = ".claude/settings.json"

    # ── Ops platform: webhooks (PR 11) ───────────────────────────────────
    # When False the POST /webhooks routes return 503 with a clear
    # "not configured" message. Setting either secret to a non-empty
    # value implicitly enables the matching provider.
    webhook_api_enabled: bool = False
    # Shared bearer token for non-GitHub providers.
    webhook_api_secret: str = ""
    # HMAC-SHA256 shared secret for GitHub deliveries.
    github_webhook_secret: str = ""

    # ── Ops platform: scheduler (PR 12) ──────────────────────────────────
    # When False the scheduler lifespan task never starts; the API
    # routes still serve historical job rows but disable mutate verbs.
    scheduler_enabled: bool = False
    # When True, APScheduler uses ``SQLAlchemyJobStore`` against the
    # configured database. When False, jobs live in memory only and are
    # lost on restart (fine for tests).
    scheduler_persistent_jobstore: bool = True

    # ── Telegram polish (PR 07) ──────────────────────────────────────────
    # Default verbose level for new Telegram conversations.
    # 0 = quiet, 1 = normal (tool names live), 2 = detailed (+ thinking).
    telegram_verbose_default: Literal[0, 1, 2] = 1
    # How often the persistent typing indicator is refreshed. Telegram
    # auto-clears typing after ~5 s so the refresh must be faster.
    telegram_typing_refresh_seconds: float = 2.5
    # When True, the Telegram channel uses Bot API 9.3+ ``sendMessageDraft``
    # for animated streaming. Falls back to ``editMessageText`` when
    # aiogram doesn't expose the binding.
    telegram_use_draft_streaming: bool = False

    # ── Voice transcription (PR 14) ──────────────────────────────────────
    # Selects which STT backend the voice handler routes to. The
    # historical ``xai`` value still works — the existing
    # ``api/stt.py`` proxy is kept as one option among many.
    voice_provider: Literal["xai", "mistral", "openai", "local"] = "xai"
    voice_mistral_api_key: str = ""
    voice_openai_api_key: str = ""
    # When ``voice_provider == "local"``: path to the whisper.cpp binary
    # and the GGML model file. Both auto-detected from PATH /
    # ``~/.cache/whisper-cpp/`` when left empty.
    voice_whisper_cpp_binary: str = ""
    voice_whisper_cpp_model: str = "base"
    # Maximum voice file size accepted, in MB.
    voice_max_size_mb: int = 25

    # ── Lossless Context Management (LCM) ────────────────────────────
    # Master switch for the LCM compaction system (see app.core.lcm).
    # Default OFF so the schema can land without changing runtime
    # behaviour.  Later stack PRs activate ingest → assemble → compact.
    lcm_enabled: bool = False
    # Last N raw messages that are always kept verbatim, never compacted.
    # 64 matches the upstream plugin's default; increase for chattier
    # surfaces (Telegram) where short messages dominate.
    lcm_fresh_tail_count: int = 64
    # Approximate source-token ceiling per leaf summary.  Raise this on
    # quota-limited summary providers; lower it for tighter context.
    lcm_leaf_chunk_tokens: int = 20000
    # Auto-trigger compaction when the conversation context is at or
    # above this fraction of the model's window.  ``0.75`` is the
    # upstream default.
    lcm_context_threshold: float = 0.75
    # How many condensation passes to run after each leaf compaction.
    # 0 = leaf-only, -1 = unlimited cascade.
    lcm_incremental_max_depth: int = 1
    # Optional model override for compaction summarisation.  When unset,
    # falls back to the same model the conversation is using — fine for
    # cheap models, wasteful for premium ones.
    lcm_summary_model: str = ""

    @property
    def claude_sandbox_excluded_commands_list(self) -> list[str]:
        """Parsed view of ``claude_sandbox_excluded_commands``."""
        if not self.claude_sandbox_excluded_commands:
            return []
        return [
            cmd.strip() for cmd in self.claude_sandbox_excluded_commands.split(",") if cmd.strip()
        ]

    @property
    def voice_max_size_bytes(self) -> int:
        """Voice size cap in bytes (the handler validates against this)."""
        bytes_per_mb = 1024 * 1024
        return self.voice_max_size_mb * bytes_per_mb

    @field_validator("telegram_bot_username", mode="before")
    @classmethod
    def _strip_telegram_at_prefix(cls, value: object) -> object:
        """Forgive a leading ``@`` in ``TELEGRAM_BOT_USERNAME``.

        Telegram deep links are ``https://t.me/<username>``; an ``@``
        produces ``t.me/@username`` which Telegram redirects to its
        homepage instead of the bot. Humans frequently paste the
        ``@``-prefixed handle into ``.env``, so we normalize once at the
        config boundary instead of forcing every consumer to remember.
        """
        if isinstance(value, str):
            return value.lstrip("@")
        return value

    @model_validator(mode="after")
    def validate_secure_cookie(self) -> "Settings":
        """Reject misconfigurations where ``SameSite=none`` is paired with insecure cookies."""
        secure = self.cookie_secure if self.cookie_secure is not None else self.is_production
        if self.cookie_samesite == "none" and not secure:
            raise ValueError(
                "cookie_samesite='none' requires HTTPS (cookie_secure must be True, or run with ENV=prod)."
            )
        return self

    @property
    def is_production(self) -> bool:
        """A convenience property that returns True if the application is running in production mode (i.e., if env is set to "prod")."""
        return self.env == "prod"

    @property
    def _normalized_database_url(self) -> str:
        """Return the configured database URL in a normalized form."""
        url = self.database_url.strip()
        if not url:
            return "sqlite:///./nexus.db"

        parsed = urlparse(url)
        if parsed.scheme.startswith(("postgresql", "sqlite")):
            return url

        # Treat bare filesystem paths as SQLite database files.
        if not parsed.scheme:
            return f"sqlite:///{url}"

        return url

    @property
    def is_sqlite(self) -> bool:
        """Whether the configured database uses SQLite."""
        return urlparse(self._normalized_database_url).scheme.startswith("sqlite")

    @property
    def db_url_sync(self) -> str:
        """Return the database URL formatted for synchronous connections.

        PostgreSQL URLs are normalized to the installed psycopg driver, while
        SQLite async URLs are converted back to the sync sqlite dialect.
        """
        url = self._normalized_database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        return url

    @property
    def db_url_async(self) -> str:
        """Return the database URL formatted for asynchronous connections.

        PostgreSQL URLs are normalized to the psycopg async dialect and SQLite
        sync URLs are converted to the aiosqlite dialect.
        """
        url = self._normalized_database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url


settings = Settings()
