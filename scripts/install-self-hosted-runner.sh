#!/usr/bin/env bash
# Install an Pawrrtal/Pawrrtal self-hosted GitHub Actions runner on the VPS.
#
# Matches the existing convention used by the other runners on the box
# (openclaw-vps-01..04): a system-level systemd service running as the
# dedicated `gha` user out of `/srv/github-runners/<repo>/actions-runner/`.
# Run as root.
#
# Steps:
#   1. Asks GitHub for a one-shot registration token using the GH_TOKEN
#      env var.
#   2. Creates `/srv/github-runners/pawrrtal/<runner-name>/actions-runner/`
#      owned by gha
#      (creates the gha user if missing).
#   3. Downloads the latest `actions-runner` tarball into that directory.
#   4. Configures the runner with labels [self-hosted, openclaw-mini,
#      pawrrtal] under the next available `openclaw-vps-NN` name.
#   5. Installs + starts the official runner systemd unit (`./svc.sh
#      install gha && ./svc.sh start`), which lands at
#      /etc/systemd/system/actions.runner.<repo-slug>.<runner>.service.
#
# Usage:
#   sudo GH_TOKEN=ghp_... bash scripts/install-self-hosted-runner.sh
#
# Override the runner name explicitly when the next-NN guess is wrong:
#   sudo GH_TOKEN=ghp_... RUNNER_NAME=openclaw-vps-07 \
#     bash scripts/install-self-hosted-runner.sh

set -euo pipefail

REPO="${REPO:-OctavianTocan/Pawrrtal-AI}"
RUNNER_USER="${RUNNER_USER:-gha}"
RUNNER_BASE="${RUNNER_BASE:-/srv/github-runners}"
RUNNER_REPO_DIR="${RUNNER_REPO_DIR:-${RUNNER_BASE}/pawrrtal}"
LABELS="${LABELS:-self-hosted,openclaw-mini,pawrrtal}"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo)." >&2
    exit 1
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
    echo "GH_TOKEN must be set (PAT with repo + workflow scope)." >&2
    exit 1
fi

# --- Resolve runner name -----------------------------------------------------
# Match the openclaw-vps-NN convention used by the other runners on this box.
# The user can pre-set RUNNER_NAME to override; otherwise we scan the existing
# /srv/github-runners/*/actions-runner/.runner files for the highest NN and
# bump it by one.
if [[ -z "${RUNNER_NAME:-}" ]]; then
    HIGHEST=0
    while IFS= read -r config; do
        name=$(python3 -c "import sys,json; print(json.load(open('$config'))['agentName'])" 2>/dev/null || true)
        if [[ "$name" =~ ^openclaw-vps-([0-9]+)$ ]]; then
            n=${BASH_REMATCH[1]#0}
            ((n > HIGHEST)) && HIGHEST=$n
        fi
    done < <(find "$RUNNER_BASE" -maxdepth 3 -name .runner 2>/dev/null)
    NEXT=$((HIGHEST + 1))
    RUNNER_NAME=$(printf "openclaw-vps-%02d" "$NEXT")
fi
echo "==> Runner name: $RUNNER_NAME"

RUNNER_DIR="${RUNNER_DIR:-${RUNNER_REPO_DIR}/${RUNNER_NAME}/actions-runner}"
if [[ -d "$RUNNER_DIR" ]]; then
    echo "Runner directory already exists at $RUNNER_DIR." >&2
    echo "Remove it first if you want to rebuild from scratch." >&2
    exit 1
fi
echo "==> Runner dir: $RUNNER_DIR"

# --- Ensure gha user exists --------------------------------------------------
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
    echo "==> Creating system user $RUNNER_USER..."
    useradd --system --create-home --shell /usr/sbin/nologin "$RUNNER_USER"
fi

# --- Registration token ------------------------------------------------------
echo "==> Requesting registration token from GitHub..."
REG_TOKEN=$(curl -fsSL -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: token ${GH_TOKEN}" \
    "https://api.github.com/repos/${REPO}/actions/runners/registration-token" |
    python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# --- Download runner ---------------------------------------------------------
echo "==> Detecting latest runner version..."
LATEST=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest |
    python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
ARCH_RAW=$(uname -m)
case "$ARCH_RAW" in
    x86_64) ARCH=x64 ;;
    aarch64 | arm64) ARCH=arm64 ;;
    *)
        echo "Unsupported arch: $ARCH_RAW" >&2
        exit 1
        ;;
esac
TARBALL="actions-runner-linux-${ARCH}-${LATEST}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${LATEST}/${TARBALL}"

echo "==> Downloading $TARBALL into $RUNNER_DIR..."
install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0755 "$RUNNER_DIR"
cd "$RUNNER_DIR"
curl -fsSL -o "$TARBALL" "$URL"
sudo -u "$RUNNER_USER" tar xzf "$TARBALL"
rm "$TARBALL"
chown -R "$RUNNER_USER":"$RUNNER_USER" "$RUNNER_DIR"

# --- Configure ---------------------------------------------------------------
echo "==> Configuring runner '${RUNNER_NAME}' for ${REPO} with labels ${LABELS}..."
sudo -u "$RUNNER_USER" ./config.sh \
    --unattended \
    --replace \
    --url "https://github.com/${REPO}" \
    --token "$REG_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$LABELS" \
    --work _work

# --- Install + start systemd service ----------------------------------------
# `./svc.sh` is GitHub's officially supported helper. It writes
# /etc/systemd/system/actions.runner.<owner-repo>.<runner>.service and
# wires it to RestartSec=15 / Restart=always under the runner user.
echo "==> Installing systemd service (via official svc.sh)..."
./svc.sh install "$RUNNER_USER"
./svc.sh start

echo
SERVICE_NAME="actions.runner.${REPO//\//-}.${RUNNER_NAME}.service"
echo "==> Runner installed. Status:"
systemctl status "$SERVICE_NAME" --no-pager | head -12
echo
echo "Verify online at: https://github.com/${REPO}/settings/actions/runners"
