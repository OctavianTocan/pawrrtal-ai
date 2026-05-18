"""Tests for the OpenTelemetry bootstrap.

The bootstrap MUST be a no-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
unset — that's the contract that lets us ship the import + lifespan
wiring on the development branch without forcing every dev to run an
OTel collector locally.

Live OTel export is verified with an in-memory span exporter so we
don't need a real collector in CI.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest


@pytest.fixture
def _clean_telemetry_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset the module-level _initialised flag between cases."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    import app.core.telemetry as telemetry_module

    importlib.reload(telemetry_module)
    yield
    telemetry_module.shutdown_tracing()
    importlib.reload(telemetry_module)


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_setup_tracing_is_a_noop_without_endpoint() -> None:
    """Default state — no env var, no init, no failure."""
    from app.core.telemetry import setup_tracing

    # Should return cleanly even with no app.
    setup_tracing(app=None)
    setup_tracing(app=None)  # idempotent — second call also no-ops


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_setup_tracing_is_idempotent_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling setup twice with an endpoint doesn't double-instrument."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "pawrrtal-test")
    from app.core.telemetry import setup_tracing, shutdown_tracing

    setup_tracing(app=None)
    setup_tracing(
        app=None
    )  # idempotent — must not raise even though instrumentors already installed
    shutdown_tracing()


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_get_tracer_returns_noop_tracer_when_disabled() -> None:
    """Call sites can call ``get_tracer().start_as_current_span()`` unconditionally."""
    from app.core.telemetry import get_tracer

    tracer = get_tracer("pawrrtal.test")
    # The OTel API returns a NoOpTracer when no provider is installed —
    # start_as_current_span should produce a context manager that just
    # works without doing anything observable.
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("pawrrtal.test", True)


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_shutdown_tracing_is_safe_before_init() -> None:
    """Calling shutdown before setup should be a clean no-op."""
    from app.core.telemetry import shutdown_tracing

    shutdown_tracing()  # No exception.


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_setup_tracing_handles_missing_optional_packages_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the OTel extras are not installed, setup must log + return.

    We simulate this by setting the endpoint but stubbing the import to
    raise.  Note: in our actual venv the extras ARE installed, so we
    can't trigger the ImportError naturally; the test guards the error
    handling path is wired and won't crash the app.
    """
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    # Force-shadow one of the deferred imports.
    fake_modules = {
        "opentelemetry.instrumentation.httpx": None,
    }
    import sys

    original = {k: sys.modules.get(k) for k in fake_modules}
    for name in fake_modules:
        sys.modules[name] = None  # type: ignore[assignment]
    try:
        from app.core.telemetry import setup_tracing

        # Should not raise even though one of the imports is broken.
        setup_tracing(app=None)
    finally:
        for name, value in original.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_otel_enabled_reads_endpoint_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """The enabled gate is purely the standard endpoint env var."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    import app.core.telemetry as telemetry_module

    with TemporaryDirectory() as tmp:
        monkeypatch.setattr(telemetry_module, "_BACKEND_DIR", Path(tmp))
        assert telemetry_module._otel_enabled() is False
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        assert telemetry_module._otel_enabled() is False
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
        assert telemetry_module._otel_enabled() is True


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_json_exporter_sends_valid_otlp_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """The JSON exporter produces camelCase OTLP JSON that Workshop accepts."""
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    import app.core.telemetry as telemetry_module

    received: list[bytes] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            received.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true,"spansIngested":1}')

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{port}/v1/traces")

    exporter = telemetry_module._make_json_exporter()

    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("json-export-test") as span:
        span.set_attribute("test.key", "value")

    provider.shutdown()
    server.shutdown()
    thread.join(timeout=2)

    assert len(received) == 1
    body = json.loads(received[0])
    assert "resourceSpans" in body
    assert body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "json-export-test"


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_drop_grpc_connect_spans_filters_connect_names() -> None:
    """The _drop_grpc_connect_spans wrapper discards spans named 'connect'."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    import app.core.telemetry as telemetry_module

    exported_names: list[str] = []

    class _RecordingExporter:
        def export(self, spans):
            exported_names.extend(s.name for s in spans)
            return 0

        def shutdown(self):
            pass

        def force_flush(self, _timeout_millis=0):
            return True

    inner = _RecordingExporter()
    filtered = telemetry_module._drop_grpc_connect_spans(inner)

    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(filtered))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("connect"):
        pass
    with tracer.start_as_current_span("pawrrtal.turn"):
        pass
    with tracer.start_as_current_span("connect"):
        pass
    with tracer.start_as_current_span("chat.stream grok-4.3"):
        pass

    provider.shutdown()
    assert exported_names == ["pawrrtal.turn", "chat.stream grok-4.3"]


@pytest.mark.usefixtures("_clean_telemetry_state")
def test_drop_grpc_connect_spans_passes_through_empty_batches() -> None:
    """When all spans are filtered, the inner exporter is not called at all."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult

    import app.core.telemetry as telemetry_module

    called = False

    class _NeverCalledExporter:
        def export(self, _spans):
            nonlocal called
            called = True
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

        def force_flush(self, _timeout_millis=0):
            return True

    inner = _NeverCalledExporter()
    filtered = telemetry_module._drop_grpc_connect_spans(inner)

    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(filtered))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("connect"):
        pass

    provider.shutdown()
    assert not called
