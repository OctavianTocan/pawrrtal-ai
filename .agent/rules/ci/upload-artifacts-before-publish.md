---
name: upload-artifacts-before-publish
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Upload Build Artifacts Before the Publish Step - Publish Can Fail and Lose the Build

Category: ci
Tags: [ci, github-actions, artifacts]

## Rule

Upload build artifacts BEFORE running optional slow steps like Maven publish — if publish times out, artifacts are lost.

## Why

When Maven publish is slow and pushes the job past `timeout-minutes`, the artifact upload step never runs. The release job depends on the uploaded artifact, so it gets skipped too. By uploading first, the release job always gets its artifact even if Maven publish fails.

## Examples

### Bad

```yaml
# If Maven publish times out, artifact upload never runs
- name: Publish to Maven
  run: ./gradlew publishToMaven  # Takes 5+ min
- name: Upload AAR
  uses: actions/upload-artifact@v4  # Skipped on timeout
```

### Good

```yaml
# Upload first, then publish — release job always gets artifact
- name: Upload AAR
  uses: actions/upload-artifact@v4
  with:
    name: android-aar
    path: build/outputs/aar/*.aar
- name: Publish to Maven
  run: ./gradlew publishToMaven  # Can fail without blocking release
```

## References

- rn-twinmind-brownfield-ci skill: Step order matters section
- debug-ci-build-hangs skill: Upload artifacts before optional slow steps

## Verify

"Is the artifact upload step placed before any slow or optional publish steps? Will the release job still get its artifact if publish times out?"

## Patterns

Bad — upload after publish:

```yaml
- name: Publish to Maven
  run: ./gradlew publishToMaven
  timeout-minutes: 10
  # If this times out at 10 min, the upload step below never runs
  # Release job gets no artifact → entire release pipeline stalls
- name: Upload AAR
  uses: actions/upload-artifact@v4
  with:
    path: build/outputs/aar/*.aar
```

Good — upload first, publish second:

```yaml
- name: Upload AAR
  uses: actions/upload-artifact@v4
  with:
    name: android-aar
    path: build/outputs/aar/*.aar
    # Artifact is safe even if next step fails

- name: Publish to Maven
  run: ./gradlew publishToMaven
  # Failure here doesn't block the release job
```
