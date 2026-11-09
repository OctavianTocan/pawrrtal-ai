"""``paw services`` command surface."""

from __future__ import annotations

import sys

import typer

from app.cli.paw.commands.services.bws import secret_check_payload
from app.cli.paw.commands.services.systemd import (
    preflight_systemd,
    render_unit,
    run,
    systemctl,
    unit_path,
)
from app.cli.paw.commands.services.targets import (
    ServiceTarget,
    config_path,
    load_services_config,
    resolve_target,
    save_default_target,
)
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

app = typer.Typer(no_args_is_help=True)
targets_app = typer.Typer(no_args_is_help=True)
secrets_app = typer.Typer(no_args_is_help=True)
app.add_typer(targets_app, name="targets", help="List and select service targets.")
app.add_typer(secrets_app, name="secrets", help="Validate Bitwarden secrets.")


@targets_app.command("list")
def targets_list(
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List configured service targets."""
    require_one_output_mode(json_out=json_out, plain=plain)
    config = load_services_config()
    rows = [target.payload() for target in config.targets.values()]
    if json_out:
        emit_json({"default_target": config.default_target, "targets": rows})
        return
    if plain:
        emit_plain_rows(
            (
                target.name,
                target.service_name,
                target.env,
                target.frontend_port,
                target.backend_port,
            )
            for target in config.targets.values()
        )
        return
    emit_human(
        "\n".join(
            f"{target.name}\t{target.service_name}\t{target.env}\t"
            f"{target.frontend_port}->{target.backend_port}"
            for target in config.targets.values()
        )
    )


@targets_app.command("show")
def targets_show(
    target_name: str | None = typer.Argument(None, metavar="[TARGET]"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Show one service target; omitting TARGET uses the selected default."""
    require_one_output_mode(json_out=json_out, plain=plain)
    target = resolve_target(target_name)
    payload = target.payload()
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows(payload.items())
        return
    emit_human("\n".join(f"{key}: {value}" for key, value in payload.items()))


@targets_app.command("use")
def targets_use(target_name: str = typer.Argument(..., metavar="TARGET")) -> None:
    """Persist the default service target in the local services config."""
    save_default_target(target_name)
    _emit_progress(f"default service target: {target_name}")


@app.command("install")
def install(
    target_name: str | None = typer.Argument(None, metavar="[TARGET]"),
    yes: bool = typer.Option(False, "--yes", help="Allow writing and enabling the unit."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the unit without writing it."),
    enable: bool = typer.Option(True, "--enable/--no-enable", help="Enable the unit."),
    now: bool = typer.Option(True, "--now/--no-now", help="Start the unit after install."),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Install a systemd service for TARGET."""
    require_one_output_mode(json_out=json_out, plain=plain)
    if not yes and not dry_run:
        raise LocalError(
            "Installing a service requires --yes or --dry-run.",
            hint="Run `paw services install TARGET --dry-run` to preview.",
        )
    target = resolve_target(target_name)
    unit = render_unit(target)
    if dry_run:
        _emit_install_payload(target, dry_run=True, json_out=json_out, plain=plain, unit=unit)
        return
    preflight_systemd()
    destination = unit_path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(unit, encoding="utf-8")
    systemctl("daemon-reload")
    if enable:
        args = ["enable", target.service_name]
        if now:
            args.insert(1, "--now")
        systemctl(*args)
    elif now:
        systemctl("start", target.service_name)
    _emit_install_payload(target, dry_run=False, json_out=json_out, plain=plain, unit=unit)


@app.command("uninstall")
def uninstall(
    target_name: str | None = typer.Argument(None, metavar="[TARGET]"),
    yes: bool = typer.Option(False, "--yes", help="Allow disabling and removing the unit."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
) -> None:
    """Disable and remove a systemd service for TARGET."""
    if not yes and not dry_run:
        raise LocalError(
            "Uninstalling a service requires --yes or --dry-run.",
            hint="Run `paw services uninstall TARGET --dry-run` to preview.",
        )
    target = resolve_target(target_name)
    destination = unit_path(target)
    if dry_run:
        emit_human(str(destination))
        return
    systemctl("disable", "--now", target.service_name)
    destination.unlink(missing_ok=True)
    systemctl("daemon-reload")
    _emit_progress(f"removed {target.service_name}")


@app.command("start")
def start(target_name: str | None = typer.Argument(None, metavar="[TARGET]")) -> None:
    """Start a service target."""
    target = resolve_target(target_name)
    systemctl("start", target.service_name)
    _emit_progress(f"started {target.service_name}")


@app.command("stop")
def stop(target_name: str | None = typer.Argument(None, metavar="[TARGET]")) -> None:
    """Stop a service target."""
    target = resolve_target(target_name)
    systemctl("stop", target.service_name)
    _emit_progress(f"stopped {target.service_name}")


@app.command("restart")
def restart(target_name: str | None = typer.Argument(None, metavar="[TARGET]")) -> None:
    """Restart a service target."""
    target = resolve_target(target_name)
    systemctl("restart", target.service_name)
    _emit_progress(f"restarted {target.service_name}")


@app.command("status")
def status(target_name: str | None = typer.Argument(None, metavar="[TARGET]")) -> None:
    """Show systemd status for a service target."""
    target = resolve_target(target_name)
    result = systemctl("status", target.service_name, "--no-pager", check=False)
    emit_human((result.stdout or result.stderr).strip())
    raise typer.Exit(code=result.returncode)


@app.command("logs")
def logs(
    target_name: str | None = typer.Argument(None, metavar="[TARGET]"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs."),
    lines: int = typer.Option(100, "--lines", min=1, help="Number of log lines to show."),
) -> None:
    """Show journal logs for a service target."""
    target = resolve_target(target_name)
    args = ["journalctl", "-u", target.service_name, "--no-pager", "-n", str(lines)]
    if follow:
        args.append("-f")
    result = run(args, check=False)
    emit_human((result.stdout or result.stderr).strip())
    raise typer.Exit(code=result.returncode)


@secrets_app.command("check")
def secrets_check(
    target_name: str | None = typer.Argument(None, metavar="[TARGET]"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Validate Bitwarden access and required secret names for TARGET."""
    require_one_output_mode(json_out=json_out, plain=plain)
    payload = secret_check_payload(resolve_target(target_name))
    raw_loaded_keys = payload["loaded_keys"]
    loaded_keys = [str(key) for key in raw_loaded_keys] if isinstance(raw_loaded_keys, list) else []
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows(
            (
                ("target", payload["target"]),
                ("project_id", payload["project_id"]),
                ("shared_project_id", payload["shared_project_id"]),
                ("loaded_keys", ",".join(loaded_keys)),
            )
        )
        return
    emit_human(
        "\n".join(
            [
                f"target: {payload['target']}",
                f"project_id: {payload['project_id']}",
                f"shared_project_id: {payload['shared_project_id']}",
                f"loaded_keys: {', '.join(loaded_keys)}",
            ]
        )
    )


def _emit_install_payload(
    target: ServiceTarget,
    *,
    dry_run: bool,
    json_out: bool,
    plain: bool,
    unit: str,
) -> None:
    """Emit install result without leaking secrets."""
    payload = {
        "target": target.name,
        "service_name": target.service_name,
        "unit_path": str(unit_path(target)),
        "config_path": str(config_path()),
        "dry_run": dry_run,
    }
    if json_out:
        emit_json({**payload, "unit": unit if dry_run else None})
        return
    if plain:
        emit_plain_rows(payload.items())
        return
    if dry_run:
        emit_human(unit)
        return
    _emit_progress(f"installed {target.service_name} at {unit_path(target)}")


def _emit_progress(message: str) -> None:
    """Emit progress/status text to stderr."""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


if __name__ == "__main__":
    app()
