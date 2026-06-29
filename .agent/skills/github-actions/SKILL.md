---
name: github-actions
description: "Use when creating or modifying GitHub Actions workflows for Pawrrtal. Covers mandatory OctavianTocan actor gate, self-hosted runner defaults, pull_request_target exception, and where CI jobs must live. For VPS runner launch/cleanup, use runner-ops."
---

# GitHub Actions (Pawrrtal)

Public repo on a self-hosted runner pool. **Every** workflow job needs the actor gate — even `ubuntu-latest` jobs.

VPS runner operations (start/cleanup scripts, volume paths) → `runner-ops` skill.  
Rule files → `.cursor/plugins/pawrrtal/rules/github-actions/`.

## Mandatory actor gate

```yaml
if: >-
  github.actor == 'OctavianTocan' &&
  (github.event_name != 'pull_request' ||
    github.event.pull_request.head.repo.full_name == github.repository)
```

Fork PRs and non-owner authors must not trigger workflows.

## Default runner

```yaml
runs-on: [self-hosted, openclaw-mini, pawrrtal]
```

- Pool: `/mnt/HC_Volume_105512717/github-runners/pawrrtal-ephemeral/`
- Ephemeral per-job runners — no persistent runner services on this public repo
- Workdirs on mounted volume, not VPS root disk
- Launch: `scripts/ephemeral-self-hosted-runners.sh start --count <N> --tag <name>`
- Cleanup: `scripts/ephemeral-self-hosted-runners.sh cleanup --count <N> --tag <name>`
- Default batch size: 1–2 when VPS is busy

Use `ubuntu-latest` only with a real reason (macOS/Windows/GPU/untrusted code already gated separately).

## Documented exception

`rebase.yml` uses `pull_request_target` and never runs PR code; uses `author_association` instead of actor gate. See `safe-pull-request-target.mdc`.

## New CI surfaces

Backend pytest, frontend vitest, Maestro E2E, sentrux, etc. belong on **self-hosted + actor gate**. Do not add ungated `ubuntu-latest` jobs "just once."

## Repo settings (GitHub UI)

- Require approval for first-time contributor workflows
- Default workflow permissions = read  
  (standard CI tokens cannot set Actions admin scope)

## Handbook

`frontend/content/docs/handbook/ci/self-hosted-runner.md`

## Checklist for new workflows

- [ ] Actor gate on every job
- [ ] `runs-on` uses self-hosted tags unless exception documented
- [ ] No secrets in workflow logs
- [ ] Paths scoped to what the job needs (`paths:` filters when appropriate)
- [ ] Matches patterns in `.github/workflows/` siblings
