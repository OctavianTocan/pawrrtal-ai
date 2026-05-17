---
title: Self-hosted GitHub Actions runner
description: Setup and maintenance guide for the hardened self-hosted CI runner on Octavian's VPS.
---

# Self-hosted GitHub Actions runner

This repo has a hardened self-hosted runner story so we can run CI
(eventually backend pytest, frontend vitest, Maestro, etc.) on
Octavian's VPS without the standard public-repo footgun.

The intended VPS pool size is three online runners for the repo. GitHub
Actions assigns each ready job to any idle runner whose labels match
`runs-on`, so three runners can execute three matching jobs concurrently
instead of queueing them behind one service.

## What's hardened

1. **Workflow gating.** Every workflow we own has an `if:` clause that
   only runs when both of the following are true:
   - `github.actor == 'OctavianTocan'`, and
   - the PR head repo equals the base repo (no forks).

   The gate runs *before* any step executes, so a fork PR can never
   land a job on our hardware — even if a future workflow accidentally
   targets `runs-on: [self-hosted, pawrrtal]`.

   `rebase.yml` is intentionally excluded: it uses `pull_request_target`,
   never runs PR code, and has its own `author_association` gates for
   the `/rebase` comment trigger.

2. **Repo-level Actions settings** (set manually in the GitHub UI; the
   `octagent` PAT does not have Actions admin scope so the install
   script can't flip these for you):

   Settings → Actions → General →
   - "Fork pull request workflows from outside collaborators":
     **Require approval for first-time contributors**, or stricter.
   - "Workflow permissions": **Read repository contents and packages
     permissions**.

3. **Runner labels.** The install script registers the runner with
   `self-hosted, openclaw-mini, pawrrtal` so we can selectively opt
   workflows in. Today nothing is pinned to it; add
   `runs-on: [self-hosted, pawrrtal]` to a job only when local hardware
   is the right home for it.

## Layout on the VPS

Matches the existing `openclaw-vps-01..04` runner convention on this
box, so all five runners share one mental model:

| Concern              | Value                                                        |
| -------------------- | ------------------------------------------------------------ |
| Runner user          | `gha` (system user, no shell)                                |
| Working dir          | `/srv/github-runners/pawrrtal/<runner-name>/actions-runner/` |
| Runner name          | `openclaw-vps-NN` (sequential)                               |
| systemd unit         | `actions.runner.OctavianTocan-pawrrtal.openclaw-vps-NN.service` |
| Labels               | `self-hosted, openclaw-mini, pawrrtal`                        |

The unit is a system-level service installed by GitHub's official
`./svc.sh install gha`, not a `--user` linger setup.

## Installing the runner

Run **as root on the VPS host** (not inside the OpenClaw container).

```bash
sudo GH_TOKEN=ghp_... bash scripts/install-self-hosted-runner.sh
```

`GH_TOKEN` is a personal access token with `repo` + `workflow` scope
(classic) or the fine-grained equivalent on this repo. It's used once
to fetch the one-shot registration token and again on re-registration.

The script:

- creates the `gha` system user if it doesn't exist;
- asks GitHub for a registration token (one-hour expiry, single use);
- downloads the latest `actions-runner` for your arch into a per-runner
  directory under `/srv/github-runners/pawrrtal/` owned by `gha`;
- picks the next free `openclaw-vps-NN` slot by scanning existing
  `/srv/github-runners/*/actions-runner/.runner` configs (override
  with `RUNNER_NAME=openclaw-vps-07` if needed);
- registers with labels `self-hosted, openclaw-mini, pawrrtal`;
- runs `./svc.sh install gha && ./svc.sh start` to install + start
  the system service.

To verify:

```bash
systemctl status 'actions.runner.OctavianTocan-pawrrtal.openclaw-vps-*.service'
```

…and check the runner shows online at
<https://github.com/OctavianTocan/Pawrrtal-AI/settings/actions/runners>.

## Removing a runner

```bash
cd /srv/github-runners/pawrrtal/openclaw-vps-NN/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh uninstall

# Deregister with a fresh remove token:
TOKEN=$(curl -fsSL -X POST \
  -H "Authorization: token $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/OctavianTocan/Pawrrtal-AI/actions/runners/remove-token \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
sudo -u gha ./config.sh remove --token "$TOKEN"

cd / && sudo rm -rf /srv/github-runners/pawrrtal/openclaw-vps-NN
```

## When to use the self-hosted runner vs. ubuntu-latest

Default to `ubuntu-latest`. Move a job to `[self-hosted, pawrrtal]`
only when:

- the job needs hardware GitHub-hosted runners can't provide (local
  GPU, Docker-in-Docker without nesting, persistent caches the size of
  the project graph), or
- queue time on `ubuntu-latest` is hurting iteration speed and the
  workload is trustworthy (no untrusted PR code, no privileged
  secrets).

Anything that touches secrets, performs network requests against
third-party APIs with rate limits, or talks to billing-attached
services should stay on `ubuntu-latest` unless we have a specific
reason otherwise. The gate keeps strangers out, but defense-in-depth
is cheap.
