---
name: pawrrtal-runner-ops
description: Operate Pawrrtal self-hosted GitHub Actions runners safely. Use when starting, stopping, installing, debugging, replacing, scaling, cleaning, or checking CI runners for Pawrrtal, especially on the VPS mounted volume.
---

# Pawrrtal Runner Ops

Use this before touching GitHub Actions runners for Pawrrtal.

## Non-Negotiables

1. Runner work directories, `_work`, `_tool`, caches, and temp state belong under `/mnt/HC_Volume_105512717/github-runners/`. Never put them on `/`, `/root`, or the VPS main disk.
2. Do not print runner registration tokens, removal tokens, repository tokens, secrets, service tokens, or environment files.
3. Public-repo self-hosted jobs must be locked by workflow policy, not trust. Jobs must gate on `github.actor == 'OctavianTocan'`. If workflows require an `octavian-only` label, the runner launcher and CI handbook must register that label in the same PR.
4. Use repo-scoped runners for `OctavianTocan/Pawrrtal-AI`. Do not create org/global runners for this repo without explicit user approval.
5. Installing persistent runner services is a security model change. Get explicit approval after stating the blast radius.

## Authoritative Discovery

Treat this skill as the policy, but confirm the current repo constants before editing workflows or installing runners:

```bash
rg -n "github\\.actor|octavian-only|runs-on: \\[self-hosted|github-runners|ephemeral-self-hosted-runners" AGENTS.md .github/workflows frontend/content/docs scripts
df -h / /mnt/HC_Volume_105512717
```

If the repo has intentionally renamed labels, paths, or scripts, follow the checked-in policy and update this skill in the same PR.

## Runner Labels

Use the labels that the checked-in launcher and CI handbook agree on. Current `main` defaults to:

```text
self-hosted
openclaw-mini
pawrrtal
```

When moving to an explicit `octavian-only` runner pool, update all of these together:

- `.github/workflows/**` `runs-on` labels
- `scripts/ephemeral-self-hosted-runners.sh` `LABELS`
- `frontend/content/docs/handbook/ci/self-hosted-runner.md`
- `AGENTS.md`
- this skill

## Before Starting Runners

```bash
df -h / /mnt/HC_Volume_105512717
gh api repos/OctavianTocan/Pawrrtal-AI/actions/runners --jq '{total_count, runners: [.runners[] | {name, status, busy, labels: [.labels[].name]}]}'
ps -eo pid,user,cmd | rg 'actions-runner|Runner.Listener|Runner.Worker|gh pr checks' || true
rg -n "github\\.actor|runs-on: \\[self-hosted|octavian-only" .github/workflows
```

If disk is tight, clean stale runner workdirs before adding capacity.

## Persistent Runner Shape

When explicitly approved, persistent runners should be:

- under `/mnt/HC_Volume_105512717/github-runners/pawrrtal-persistent/`
- one system user per runner
- repo-scoped to `OctavianTocan/Pawrrtal-AI`
- labeled to match the checked-in workflow requirements
- resource-bounded with systemd CPU, memory, task, and IO limits
- configured so `HOME`, `RUNNER_TOOL_CACHE`, `ACTIONS_RUNNER_TEMP`, `UV_CACHE_DIR`, `BUN_INSTALL_CACHE_DIR`, and `npm_config_cache` point inside the runner directory

## Ephemeral Runner Shape

Only use ephemeral runners when the user asks for ephemeral behavior or the security model requires it. Use bounded batches and tags, then clean them.

```bash
scripts/ephemeral-self-hosted-runners.sh start --count <N> --tag <tag>
scripts/ephemeral-self-hosted-runners.sh cleanup --count <N> --tag <tag>
```

## After CI Work

Always prove the runner state and disk state:

```bash
gh api repos/OctavianTocan/Pawrrtal-AI/actions/runners --jq '{total_count, runners: [.runners[] | {name, status, busy, labels: [.labels[].name]}]}'
systemctl list-units --type=service --all 'pawrrtal-gha-*.service' --no-pager
ps -eo pid,user,cmd | rg 'actions-runner|Runner.Listener|Runner.Worker|ephemeral-self-hosted-runners' || true
df -h / /mnt/HC_Volume_105512717
```

Report where runners live, which labels they have, whether any are busy, and how much disk remains.
