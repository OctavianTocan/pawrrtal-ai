---
name: cancel-push-not-dispatch-on-both-triggers
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# When Push and Dispatch Trigger Simultaneously, Cancel the Push Run

## Rule

When `push` and `workflow_dispatch` events trigger the same workflow simultaneously, identify runs by their `event` type before cancelling. Push-triggered runs have no dispatch inputs. Dispatch-triggered runs carry your configured inputs.

## Why

Two runs of the same workflow can start within seconds of each other. The GitHub Actions list sorts by start time, and it's easy to cancel the wrong one. A cancelled run with your custom inputs (version, environment) cannot be recovered.

## Verify

```bash
# List recent runs and check their trigger type
gh run list -w "publish.yml" --limit 5 --json databaseId,event,displayTitle
# Cancel only the push-triggered one
gh run cancel <push-triggered-id>
```

## Patterns

Bad — cancelling by position without checking event type:

```bash
# Cancel the most recent run — might be the dispatch with your inputs!
gh run list -w "publish.yml" --limit 1 --json databaseId --jq '.[0].databaseId' | xargs gh run cancel
```

Bad — no concurrency control at all:

```yaml
# Both push and dispatch can run simultaneously, wasting runner capacity
on:
  push:
    branches: [main]
  workflow_dispatch:
  # No concurrency group configured
```

Good — use concurrency groups to auto-cancel push when dispatch fires:

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: publish-${{ github.ref }}
  cancel-in-progress: true
  # Push run gets cancelled automatically when dispatch runs
```

Good — manual cancellation with event check:

```bash
# List runs with event type to identify the push run
gh run list -w "publish.yml" --limit 5 --json databaseId,event,displayTitle
# Only cancel the push-triggered run, keep the dispatch
gh run cancel <push-triggered-id>
```

## Origin

a prior release workflow publish — push and dispatch ran simultaneously, wrong run was cancelled, required fresh dispatch.
