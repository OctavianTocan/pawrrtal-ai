"""Output helpers for ``paw verify`` commands."""

from __future__ import annotations

from app.cli.paw.errors import PawError, VerificationFailedError
from app.cli.paw.output import emit_human, emit_json
from app.cli.paw.verify.scenarios import ScenarioResult


def emit_runtime_error(label: str, exc: PawError, *, json_out: bool) -> None:
    """Render a Paw runtime error for one verify suite."""
    if json_out:
        payload: dict[str, object] = {
            "scenario": label,
            "passed": False,
            "error": exc.message,
            "exit_code": exc.exit_code,
        }
        if exc.hint:
            payload["hint"] = exc.hint
        emit_json(payload)
        return
    lines = [f"verify {label} failed: {exc.message}"]
    if exc.hint:
        lines.append(f"Hint: {exc.hint}")
    emit_human("\n".join(lines))


def emit_and_exit(result: ScenarioResult, *, json_out: bool, label: str) -> None:
    """Render one scenario result and raise exit 6 when checks failed."""
    if json_out:
        emit_json(result.to_dict())
    else:
        emit_human(render(result))
    if not result.passed:
        failed_names = ", ".join(c.name for c in result.checks if not c.passed)
        raise VerificationFailedError(f"{label} scenario failed ({failed_names})")


def emit_many_and_exit(results: list[ScenarioResult], *, json_out: bool) -> None:
    """Render an aggregate result and raise exit 6 when any suite failed."""
    if json_out:
        emit_json([r.to_dict() for r in results])
    else:
        emit_human(render_aggregate(results))
    if any(not r.passed for r in results):
        failed = ",".join(r.name for r in results if not r.passed)
        raise VerificationFailedError(f"verify all failed for suites: {failed}")


def render(r: ScenarioResult) -> str:
    """Render one scenario result as OK/FAIL lines."""
    lines = [f"scenario: {r.name}  passed={r.passed}"]
    for check in r.checks:
        mark = "OK" if check.passed else "FAIL"
        line = f"  [{mark}] {check.name}"
        if not check.passed and check.detail:
            line += f"   ({check.detail})"
        lines.append(line)
    return "\n".join(lines) + "\n"


def render_aggregate(results: list[ScenarioResult]) -> str:
    """Render multiple scenario results with a suite-count summary."""
    sections = [render(r) for r in results]
    summary_line = f"\n{sum(r.passed for r in results)}/{len(results)} suites passed.\n"
    return "".join(sections) + summary_line
