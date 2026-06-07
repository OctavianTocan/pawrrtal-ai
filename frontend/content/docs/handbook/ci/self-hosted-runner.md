---
title: Self-hosted GitHub Actions runner
description: Setup and maintenance guide for Pawrrtal's hardened ephemeral CI runners on Octavian's VPS.
---

# Self-hosted GitHub Actions runner

Pawrrtal uses repo-scoped, ephemeral self-hosted runners when a CI job
needs the VPS runner labels. Do not install persistent GitHub Actions
runners for this repo. A persistent runner turns every accepted workflow
job into a long-lived remote-code-execution surface on the host.

## Operating rules

1. **Ephemeral only.** Each runner is registered with `--ephemeral`, accepts
   one job, deregisters from GitHub, and exits.
2. **Repo-scoped only.** Register against `OctavianTocan/Pawrrtal-AI`, not
   the organization or enterprise.
3. **No privileged host access.** Runner users do not get sudo, shell access,
   Docker socket access, or shared host mounts.
4. **Bounded concurrency.** Start only the number of runners needed for the
   current CI drain. The default is two, and the launcher refuses batches
   larger than four.
5. **Clean after each drain.** Run cleanup after the queued jobs finish so
   local users, runner directories, and stale units disappear.

## What is hardened

### Workflow gating

Every workflow we own has a job-level `if:` gate that allows only trusted
repo-owned events to reach a runner:

```yaml
if: >-
  (github.actor == 'OctavianTocan' || github.actor == 'octagent') &&
  (github.event_name != 'pull_request' ||
    github.event.pull_request.head.repo.full_name == github.repository)
```

That gate runs before any step executes, so fork PRs do not land jobs on
the VPS runner labels. `rebase.yml` is intentionally excluded: it uses
`pull_request_target`, never runs PR code, and has its own
`author_association` gates for the `/rebase` comment trigger.

### GitHub settings

These are set in the GitHub UI because normal CI tokens do not have
Actions admin scope:

| Setting | Required value |
| --- | --- |
| Fork pull request workflows | Require approval for first-time contributors, or stricter |
| Workflow permissions | Read repository contents and packages permissions |
| Self-hosted runner scope | Repository only |

### Runner process sandbox

The launcher starts each runner through `systemd-run` with a dedicated
system user and a private runner directory:

| Concern | Value |
| --- | --- |
| Base directory | `/mnt/HC_Volume_105512717/github-runners/pawrrtal-ephemeral/` |
| Runner user | `gha-paw-<tag>-NN`, system user, no login shell |
| Runner directory | `/mnt/HC_Volume_105512717/github-runners/pawrrtal-ephemeral/runs/<tag>/<runner>/actions-runner/` |
| Labels | `self-hosted, openclaw-mini, pawrrtal` |
| systemd unit | `pawrrtal-gha-<tag>-NN.service` |
| Writable paths | Runner directory plus private `/tmp` |
| Cache paths | Inside the runner directory, deleted by cleanup |
| Resource limits | `CPUQuota=200%`, `MemoryHigh=6G`, `MemoryMax=8G`, lower CPU/IO weight |

The unit sets `NoNewPrivileges`, `PrivateTmp`, `PrivateDevices`,
`ProtectHome`, `ProtectSystem=strict`, kernel/control-group protection,
process table hiding, an empty capability bounding set, and per-runner CPU,
memory, task, and IO ceilings.

## Starting runners

Run on the VPS host, not inside an application container:

```bash
sudo -E scripts/ephemeral-self-hosted-runners.sh start --count 3 --tag pr-474
```

The script defaults `RUNNER_BASE` to the large mounted volume and checks
for at least 50 GB free before starting a batch. Do not point
`RUNNER_BASE` at the VPS root disk unless you have first verified enough
headroom for every runner workdir and cache. If the VPS is under load, use
`--count 1` or `--count 2`; do not run a max-size batch just to shorten a
queue.

Authentication comes from the GitHub CLI account or `GH_TOKEN`. If using
`GH_TOKEN`, the token must be allowed to create repository self-hosted
runner registration tokens for `OctavianTocan/Pawrrtal-AI`.

Use a tag that identifies the drain, such as `pr-474`. Tags are limited to
16 characters of letters, numbers, underscores, or dashes so generated
user and unit names stay predictable.

## Watching runners

```bash
sudo -E scripts/ephemeral-self-hosted-runners.sh status --count 3 --tag pr-474
gh pr checks 474 --watch
```

If more jobs remain queued after the first runners exit, start another
small batch with the same tag after cleanup, or use a different tag for a
new batch.

## Cleaning up

Run cleanup after the runners finish their one job each:

```bash
sudo -E scripts/ephemeral-self-hosted-runners.sh cleanup --count 3 --tag pr-474
```

Cleanup stops any remaining units, removes stale GitHub runner
registrations when a `.runner` file is still present, deletes the local
runner users, and removes the tagged runner directories.

## When to use these runners

Use the ephemeral self-hosted runner only for jobs that explicitly require
the Pawrrtal runner labels:

```yaml
runs-on: [self-hosted, openclaw-mini, pawrrtal]
```

or:

```yaml
runs-on: [self-hosted, pawrrtal]
```

Use `ubuntu-latest` only for documented exceptions where hosted isolation
is the safer or technically necessary choice. Any workflow that touches
secrets, billing-attached services, or untrusted PR code needs explicit
review before it can target the VPS labels.
