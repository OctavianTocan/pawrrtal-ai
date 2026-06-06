#!/usr/bin/env bash
# Start or clean up hardened, repo-scoped ephemeral GitHub Actions runners.
#
# These runners are intentionally not installed as persistent services. Each
# runner accepts one job, deregisters from GitHub, and then exits. Use cleanup
# after the jobs drain to remove local users and work directories.

set -euo pipefail

REPO="${REPO:-OctavianTocan/Pawrrtal-AI}"
RUNNER_BASE="${RUNNER_BASE:-/srv/github-runners/pawrrtal-ephemeral}"
LABELS="${LABELS:-self-hosted,openclaw-mini,pawrrtal}"
RUNNER_COUNT="${RUNNER_COUNT:-3}"
RUN_TAG="${RUN_TAG:-pr-474}"
MEMORY_MAX="${MEMORY_MAX:-12G}"
CPU_QUOTA="${CPU_QUOTA:-600%}"

usage() {
    cat >&2 <<'USAGE'
Usage:
  sudo -E scripts/ephemeral-self-hosted-runners.sh start [--count N] [--tag NAME]
  sudo -E scripts/ephemeral-self-hosted-runners.sh status [--tag NAME]
  sudo -E scripts/ephemeral-self-hosted-runners.sh cleanup [--tag NAME]

Environment:
  REPO          GitHub repo, default OctavianTocan/Pawrrtal-AI
  RUNNER_BASE   Local base directory, default /srv/github-runners/pawrrtal-ephemeral
  LABELS        Runner labels, default self-hosted,openclaw-mini,pawrrtal
  MEMORY_MAX    systemd MemoryMax per runner, default 12G
  CPU_QUOTA     systemd CPUQuota per runner, default 600%

Authentication:
  Use the GitHub CLI's logged-in account or set GH_TOKEN to a token that can
  create repository self-hosted runner registration tokens.
USAGE
}

die() {
    echo "error: $*" >&2
    exit 1
}

info() {
    echo "==> $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        die "run as root with sudo"
    fi
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

safe_identifier() {
    local value="$1"
    [[ "$value" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$ ]] || {
        die "tag must be 1-16 chars of letters, numbers, underscores, or dashes"
    }
}

validate_config() {
    [[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "invalid REPO: $REPO"
    [[ "$LABELS" =~ ^[A-Za-z0-9_,.-]+$ ]] || die "invalid LABELS: $LABELS"
    [[ "$RUNNER_BASE" = /* ]] || die "RUNNER_BASE must be absolute"
    [[ "$RUNNER_BASE" != "/" ]] || die "RUNNER_BASE cannot be /"
    [[ "$RUNNER_COUNT" =~ ^[1-9][0-9]*$ ]] || die "count must be a positive integer"
    ((RUNNER_COUNT <= 8)) || die "count must be 8 or less"
    safe_identifier "$RUN_TAG"
}

parse_args() {
    ACTION="${1:-}"
    [[ -n "$ACTION" ]] || {
        usage
        exit 2
    }
    shift || true

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --count)
                RUNNER_COUNT="${2:-}"
                shift 2
                ;;
            --tag)
                RUN_TAG="${2:-}"
                shift 2
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            *)
                die "unknown argument: $1"
                ;;
        esac
    done
}

resolve_arch() {
    case "$(uname -m)" in
        x86_64) echo "x64" ;;
        aarch64 | arm64) echo "arm64" ;;
        *) die "unsupported architecture: $(uname -m)" ;;
    esac
}

latest_runner_version() {
    gh release view --repo actions/runner --json tagName --jq '.tagName | ltrimstr("v")'
}

download_runner() {
    local version="$1"
    local arch="$2"
    local cache_dir="${RUNNER_BASE}/cache"
    local tarball="actions-runner-linux-${arch}-${version}.tar.gz"
    local path="${cache_dir}/${tarball}"
    local url="https://github.com/actions/runner/releases/download/v${version}/${tarball}"

    install -d -m 0700 "$cache_dir"
    if [[ ! -f "$path" ]]; then
        info "downloading ${tarball}"
        curl -fsSL -o "$path" "$url"
        chmod 0600 "$path"
    fi
    echo "$path"
}

registration_token() {
    gh api \
        --method POST \
        "repos/${REPO}/actions/runners/registration-token" \
        --jq '.token'
}

remove_token() {
    gh api \
        --method POST \
        "repos/${REPO}/actions/runners/remove-token" \
        --jq '.token'
}

runner_name() {
    local index="$1"
    printf "pawrrtal-%s-%02d" "$RUN_TAG" "$index"
}

runner_user() {
    local index="$1"
    printf "gha-paw-%s-%02d" "$RUN_TAG" "$index"
}

runner_dir() {
    local name="$1"
    printf "%s/runs/%s/%s/actions-runner" "$RUNNER_BASE" "$RUN_TAG" "$name"
}

unit_name() {
    local index="$1"
    printf "pawrrtal-gha-%s-%02d" "$RUN_TAG" "$index"
}

create_runner_user() {
    local user="$1"
    local home="$2"

    if id "$user" >/dev/null 2>&1; then
        die "user already exists: $user"
    fi
    useradd --system --home-dir "$home" --shell /usr/sbin/nologin --user-group "$user"
}

configure_runner() {
    local dir="$1"
    local user="$2"
    local name="$3"
    local token
    token="$(registration_token)"

    sudo -u "$user" env HOME="$dir" "$dir/config.sh" \
        --unattended \
        --ephemeral \
        --replace \
        --url "https://github.com/${REPO}" \
        --token "$token" \
        --name "$name" \
        --labels "$LABELS" \
        --work _work
}

start_runner_unit() {
    local unit="$1"
    local user="$2"
    local dir="$3"

    install -d -o "$user" -g "$user" -m 0700 "$dir/_temp"
    install -d -o "$user" -g "$user" -m 0700 "$dir/_tool"
    install -d -o "$user" -g "$user" -m 0700 "$dir/.cache"
    systemd-run \
        --unit "$unit" \
        --description "Pawrrtal ephemeral GitHub Actions runner ${unit}" \
        --property "User=${user}" \
        --property "Group=${user}" \
        --property "WorkingDirectory=${dir}" \
        --property "Environment=HOME=${dir}" \
        --property "Environment=RUNNER_TEMP=${dir}/_temp" \
        --property "Environment=RUNNER_TOOL_CACHE=${dir}/_tool" \
        --property "Environment=AGENT_TOOLSDIRECTORY=${dir}/_tool" \
        --property "Environment=XDG_CACHE_HOME=${dir}/.cache" \
        --property "Environment=BUN_INSTALL=${dir}/.bun" \
        --property "UMask=0077" \
        --property "MemoryMax=${MEMORY_MAX}" \
        --property "CPUQuota=${CPU_QUOTA}" \
        --property "TasksMax=2048" \
        --property "NoNewPrivileges=yes" \
        --property "PrivateDevices=yes" \
        --property "PrivateTmp=yes" \
        --property "ProtectHome=yes" \
        --property "ProtectSystem=strict" \
        --property "ProtectControlGroups=yes" \
        --property "ProtectKernelModules=yes" \
        --property "ProtectKernelTunables=yes" \
        --property "ReadWritePaths=${dir}" \
        --property "CapabilityBoundingSet=" \
        --property "LockPersonality=yes" \
        --property "RestrictRealtime=yes" \
        --property "RestrictSUIDSGID=yes" \
        --property "SystemCallArchitectures=native" \
        "$dir/run.sh"
}

start_runners() {
    local arch version tarball
    arch="$(resolve_arch)"
    version="$(latest_runner_version)"
    tarball="$(download_runner "$version" "$arch")"

    install -d -m 0700 "$RUNNER_BASE/runs/$RUN_TAG"
    for index in $(seq 1 "$RUNNER_COUNT"); do
        local name user dir unit
        name="$(runner_name "$index")"
        user="$(runner_user "$index")"
        dir="$(runner_dir "$name")"
        unit="$(unit_name "$index")"

        [[ ! -d "$dir" ]] || die "runner directory already exists: $dir"
        info "creating ${name}"
        install -d -m 0700 "$dir"
        create_runner_user "$user" "$dir"
        tar xzf "$tarball" -C "$dir"
        chown -R "$user:$user" "$dir"
        configure_runner "$dir" "$user" "$name"
        start_runner_unit "$unit" "$user" "$dir"
    done
}

status_runners() {
    for index in $(seq 1 "$RUNNER_COUNT"); do
        local unit
        unit="$(unit_name "$index")"
        systemctl status "$unit.service" --no-pager --lines=3 || true
    done
}

stop_unit() {
    local unit="$1"
    if systemctl list-units --all --type=service --no-legend "${unit}.service" | grep -q .; then
        systemctl stop "${unit}.service" || true
        systemctl reset-failed "${unit}.service" || true
    fi
}

remove_runner_config() {
    local dir="$1"
    local user="$2"

    [[ -f "$dir/.runner" ]] || return 0
    local token
    token="$(remove_token)"
    sudo -u "$user" env HOME="$dir" "$dir/config.sh" remove --token "$token" || true
}

cleanup_runners() {
    for index in $(seq 1 "$RUNNER_COUNT"); do
        local name user dir unit
        name="$(runner_name "$index")"
        user="$(runner_user "$index")"
        dir="$(runner_dir "$name")"
        unit="$(unit_name "$index")"

        info "cleaning ${name}"
        stop_unit "$unit"
        if id "$user" >/dev/null 2>&1; then
            remove_runner_config "$dir" "$user"
            userdel "$user" || true
        fi
        if [[ -d "$dir" ]]; then
            rm -rf "$dir"
        fi
    done
}

main() {
    parse_args "$@"
    require_root
    require_command curl
    require_command gh
    require_command sudo
    require_command systemctl
    require_command systemd-run
    require_command tar
    require_command useradd
    require_command userdel
    validate_config

    case "$ACTION" in
        start) start_runners ;;
        status) status_runners ;;
        cleanup) cleanup_runners ;;
        *)
            usage
            exit 2
            ;;
    esac
}

main "$@"
