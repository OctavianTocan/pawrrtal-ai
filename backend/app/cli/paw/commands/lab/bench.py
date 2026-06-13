"""Benchmark commands for ``paw lab``."""

from __future__ import annotations

import asyncio
import shutil
import statistics
import time
from typing import Any

import typer

from app.cli.paw import ids
from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

from .storage import new_run_id, write_run

MAX_DEFAULT_RUNS = 5
MAX_DEFAULT_WARMUPS = 3
DEFAULT_BENCH_TIMEOUT_SECONDS = 240.0
DEFAULT_PROVIDER_ALLOWLIST = {
    "agy-api",
    "openai-codex",
    "opencode-go",
}

app = typer.Typer(help="Model/provider benchmark helpers.", no_args_is_help=True)


@app.command("model")
def bench_model(
    model: str = typer.Option(..., "--model", help="Model id to benchmark."),
    prompt: str = typer.Option(..., "--prompt", help="Prompt text for each turn."),
    runs: int = typer.Option(3, "--runs", min=1),
    warmup: int = typer.Option(0, "--warmup", min=0),
    compare: str | None = typer.Option(None, "--compare", help="Optional baseline: agy-cli."),
    timeout: float = typer.Option(DEFAULT_BENCH_TIMEOUT_SECONDS, "--timeout", min=1.0),
    yes_big_run: bool = typer.Option(False, "--yes-big-run"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Benchmark one model through the live Pawrrtal HTTP/SSE path."""
    _enforce_caps(runs=runs, warmup=warmup, yes_big_run=yes_big_run)
    state = load_state(profile)
    payload = asyncio.run(
        _bench_model_payload(
            state,
            model_id=model,
            prompt=prompt,
            runs=runs,
            warmup=warmup,
            request_timeout=timeout,
            compare=compare,
        )
    )
    path = write_run(profile, payload)
    payload["run_path"] = str(path)
    if json_out:
        emit_json(payload)
        return
    emit_human(_render_bench(payload))


@app.command("providers")
def bench_providers(
    prompt: str = typer.Option("Say hello briefly.", "--prompt"),
    runs: int = typer.Option(1, "--runs", min=1),
    warmup: int = typer.Option(0, "--warmup", min=0),
    include_host: list[str] = typer.Option([], "--host"),
    include_paid: bool = typer.Option(False, "--include-paid"),
    yes_big_run: bool = typer.Option(False, "--yes-big-run"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Benchmark one selected authenticated model per provider host."""
    _enforce_caps(runs=runs, warmup=warmup, yes_big_run=yes_big_run)
    state = load_state(profile)
    payload = asyncio.run(
        _bench_providers_payload(
            state,
            prompt=prompt,
            runs=runs,
            warmup=warmup,
            include_hosts=set(include_host),
            include_paid=include_paid,
        )
    )
    path = write_run(profile, payload)
    payload["run_path"] = str(path)
    if json_out:
        emit_json(payload)
        return
    emit_human(_render_provider_bench(payload))


def _enforce_caps(*, runs: int, warmup: int, yes_big_run: bool) -> None:
    """Reject accidental expensive runs unless the operator opts in."""
    if yes_big_run:
        return
    if runs > MAX_DEFAULT_RUNS:
        raise LocalError(
            f"--runs {runs} exceeds the default cap of {MAX_DEFAULT_RUNS}.",
            hint="Pass --yes-big-run when you intentionally want a larger live run.",
        )
    if warmup > MAX_DEFAULT_WARMUPS:
        raise LocalError(
            f"--warmup {warmup} exceeds the default cap of {MAX_DEFAULT_WARMUPS}.",
            hint="Pass --yes-big-run when you intentionally want more warmup turns.",
        )


async def _bench_model_payload(
    state: PersonaState,
    *,
    model_id: str,
    prompt: str,
    runs: int,
    warmup: int,
    request_timeout: float,
    compare: str | None,
) -> dict[str, Any]:
    """Build and execute a benchmark payload for one model."""
    measurements: list[dict[str, Any]] = []
    async with PawClient(state, timeout=request_timeout) as client:
        measurements.extend(
            [
                await _measure_turn(
                    client,
                    model_id=model_id,
                    prompt=prompt,
                    phase="warmup",
                    index=i,
                )
                for i in range(warmup)
            ]
        )
        measurements.extend(
            [
                await _measure_turn(
                    client,
                    model_id=model_id,
                    prompt=prompt,
                    phase="run",
                    index=i,
                )
                for i in range(runs)
            ]
        )
    payload = {
        "run_id": new_run_id("bench-model"),
        "kind": "bench-model",
        "model_id": model_id,
        "prompt": prompt,
        "runs_requested": runs,
        "warmup_requested": warmup,
        "measurements": measurements,
        "summary": _summarize_measurements(measurements),
    }
    if compare is not None:
        payload["comparisons"] = [await _run_compare(compare, prompt=prompt)]
    return payload


async def _bench_providers_payload(
    state: PersonaState,
    *,
    prompt: str,
    runs: int,
    warmup: int,
    include_hosts: set[str],
    include_paid: bool,
) -> dict[str, Any]:
    """Select catalog models and benchmark each selected provider host."""
    async with PawClient(state, timeout=DEFAULT_BENCH_TIMEOUT_SECONDS) as client:
        models = _extract_models((await client.request("GET", "/api/v1/models")).json())
    selected = _select_provider_models(
        models, include_hosts=include_hosts, include_paid=include_paid
    )
    children = []
    for row in selected:
        model_id = str(row.get("model_id") or row.get("id"))
        children.append(
            await _bench_model_payload(
                state,
                model_id=model_id,
                prompt=prompt,
                runs=runs,
                warmup=warmup,
                request_timeout=DEFAULT_BENCH_TIMEOUT_SECONDS,
                compare=None,
            )
        )
    return {
        "run_id": new_run_id("bench-providers"),
        "kind": "bench-providers",
        "prompt": prompt,
        "selected_models": selected,
        "provider_runs": children,
        "summary": {"providers": len(children), "runs_per_provider": runs},
    }


async def _measure_turn(
    client: PawClient,
    *,
    model_id: str,
    prompt: str,
    phase: str,
    index: int,
) -> dict[str, Any]:
    """Create a conversation, stream one turn, fetch persisted messages, cleanup."""
    conv_id = ids.new_conversation_id()
    await client.request(
        "POST",
        f"/api/v1/conversations/{conv_id}",
        json_body={"id": conv_id, "title": "paw lab bench"},
        expect=(200, 201),
    )
    started = time.perf_counter()
    ttft_ms: int | None = None
    events: list[dict[str, Any]] = []
    try:
        async for event in client.stream_events(
            method="POST",
            url="/api/v1/chat/",
            json_body={"question": prompt, "conversation_id": conv_id, "model_id": model_id},
        ):
            if ttft_ms is None and _is_first_visible_event(event):
                ttft_ms = int((time.perf_counter() - started) * 1000)
            events.append(event)
        client_duration_ms = int((time.perf_counter() - started) * 1000)
        messages = (await client.request("GET", f"/api/v1/conversations/{conv_id}/messages")).json()
    finally:
        await client.request("DELETE", f"/api/v1/conversations/{conv_id}", expect=(200, 204))
    return _measurement_from_events(
        events,
        messages if isinstance(messages, list) else [],
        conversation_id=conv_id,
        model_id=model_id,
        phase=phase,
        index=index,
        ttft_ms=ttft_ms,
        client_duration_ms=client_duration_ms,
    )


def _measurement_from_events(
    events: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    *,
    conversation_id: str,
    model_id: str,
    phase: str,
    index: int,
    ttft_ms: int | None,
    client_duration_ms: int,
) -> dict[str, Any]:
    """Reduce raw events + messages to one compact benchmark row."""
    assistant = _last_assistant(messages)
    event_counts = _event_counts(events)
    usage = _usage_totals(events)
    final_text = "".join(
        str(e.get("content")) for e in events if e.get("type") in {"delta", "message"}
    )
    thinking = "".join(str(e.get("content")) for e in events if e.get("type") == "thinking")
    return {
        "phase": phase,
        "index": index,
        "conversation_id": conversation_id,
        "model_id": model_id,
        "ttft_ms": ttft_ms,
        "client_duration_ms": client_duration_ms,
        "backend_duration_ms": _coerce_int(assistant.get("duration_ms")) if assistant else None,
        "event_counts": event_counts,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "thinking_chars": len(thinking),
        "tool_call_count": event_counts.get("tool_use", 0),
        "final_text_chars": len(final_text),
        "assistant_status": assistant.get("assistant_status") if assistant else None,
        "error_count": event_counts.get("error", 0),
    }


def _is_first_visible_event(event: dict[str, Any]) -> bool:
    """Return True for the first event type a user would experience."""
    return event.get("type") in {"delta", "message", "thinking", "tool_use"}


def _last_assistant(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the final assistant row from a messages payload."""
    for row in reversed(messages):
        if isinstance(row, dict) and row.get("role") == "assistant":
            return row
    return None


def _event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _usage_totals(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0}
    for event in events:
        if event.get("type") != "usage":
            continue
        totals["input_tokens"] += _coerce_int(event.get("input_tokens")) or 0
        totals["output_tokens"] += _coerce_int(event.get("output_tokens")) or 0
    return totals


def _summarize_measurements(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    runs = [m for m in measurements if m.get("phase") == "run"]
    return {
        "runs": len(runs),
        "mean_client_duration_ms": _mean_int(runs, "client_duration_ms"),
        "mean_backend_duration_ms": _mean_int(runs, "backend_duration_ms"),
        "mean_ttft_ms": _mean_int(runs, "ttft_ms"),
        "errors": sum(int(m.get("error_count") or 0) for m in runs),
    }


def _mean_int(rows: list[dict[str, Any]], key: str) -> int | None:
    values = [_coerce_int(row.get(key)) for row in rows]
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return round(statistics.mean(cleaned))


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def _extract_models(payload: Any) -> list[dict[str, Any]]:
    models = payload.get("models") if isinstance(payload, dict) else payload
    if not isinstance(models, list):
        return []
    return [row for row in models if isinstance(row, dict)]


def _select_provider_models(
    models: list[dict[str, Any]],
    *,
    include_hosts: set[str],
    include_paid: bool,
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    allowed = set(include_hosts) or set(DEFAULT_PROVIDER_ALLOWLIST)
    if include_paid:
        allowed = {str(row.get("host")) for row in models if row.get("host")}
    for row in models:
        host = str(row.get("host") or "")
        model_id = row.get("model_id") or row.get("id")
        if not host or not model_id or host not in allowed or host in selected:
            continue
        selected[host] = row
    return list(selected.values())


async def _run_compare(compare: str, *, prompt: str) -> dict[str, Any]:
    """Run an optional source-CLI baseline."""
    if compare != "agy-cli":
        raise LocalError("Unsupported --compare value.", hint="Valid value: agy-cli")
    if shutil.which("agy") is None:
        return {"kind": "agy-cli", "ok": False, "error": "agy binary not found"}
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        "agy",
        "--print",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return {
        "kind": "agy-cli",
        "ok": proc.returncode == 0,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "exit_code": proc.returncode,
        "stdout_chars": len(stdout.decode("utf-8", errors="replace")),
        "stderr_preview": stderr.decode("utf-8", errors="replace")[:500],
        "model_match": "current-agy-cli-selection",
    }


def _render_bench(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return (
        f"run_id: {payload.get('run_id')}\n"
        f"model: {payload.get('model_id')}\n"
        f"runs: {summary.get('runs')}\n"
        f"mean_client_duration_ms: {summary.get('mean_client_duration_ms')}\n"
        f"mean_backend_duration_ms: {summary.get('mean_backend_duration_ms')}\n"
        f"run_path: {payload.get('run_path')}"
    )


def _render_provider_bench(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return (
        f"run_id: {payload.get('run_id')}\n"
        f"providers: {summary.get('providers')}\n"
        f"runs_per_provider: {summary.get('runs_per_provider')}\n"
        f"run_path: {payload.get('run_path')}"
    )
