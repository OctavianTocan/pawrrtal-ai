---
name: dispatch-inputs-empty-on-push-trigger
paths: [".github/workflows/**"]
---

# workflow_dispatch Inputs Are Empty When the Same Workflow Is Triggered by a Push

## Rule

`workflow_dispatch` inputs are only populated when the workflow is triggered via dispatch (UI, API, or `gh workflow run`). Push-triggered runs of the same workflow get empty/default input values.

## Why

A push to `main` triggers the workflow but doesn't populate `workflow_dispatch` inputs. If your workflow uses `${{ github.event.inputs.version }}` for versioning, a push-triggered run builds with an empty string or the default value.

## Verify

"Does this workflow use both push and workflow_dispatch triggers? Are dispatch inputs guarded with fallback values for push-triggered runs?"

## Patterns

Bad — dispatch inputs assumed populated on push:

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      version:
        required: true

jobs:
  build:
    # This is empty on push triggers!
    env:
      VERSION: ${{ github.event.inputs.version }}
```

Good — guard dispatch inputs with fallbacks:

```yaml
env:
  VERSION: ${{ github.event.inputs.version || '0.0.0-auto.'  }}
```

Or separate workflows: one for auto-publish on push (auto-versioned), one for manual dispatch (explicit version).

## Origin

a prior release workflow publish — push to main triggered the publish workflow with empty version input, building `0.0.0-auto.{sha}` instead of `0.3.1`. Had to cancel and re-dispatch manually.
