---
name: remove-root-cause-dont-add-detection
paths: ["**/*.{ts,tsx,js,jsx}"]
---

# Remove the Root Cause Instead of Adding Detection and Recovery Logic - Prevention Is Simpler and Can't Fail to Detect

When facing a recurring issue, prefer removing the root cause over adding
detection and recovery logic. Prevention code is simpler, has fewer edge
cases, and can't fail to detect.

Removing `.allowAirPlay` from audio session options eliminated 40 lines of
AirPlay detection/recovery code. Passing `format: nil` to audio taps
eliminated all device-specific format branching. Both were one-line fixes
that replaced dozens of lines of defensive code.

## Verify

"Am I adding detection/recovery logic? Can I remove the root cause instead?"

## Patterns

Bad — 40 lines of detection + recovery:

```swift
audioSession.setCategory(.playAndRecord, options: [.allowAirPlay, ...])
func handleRouteChange(_ notification: Notification) {
  if isAirPlayActive() { disconnectAirPlay(); restartRecording(); ... }
}
```

Good — root cause removed, zero recovery code needed:

```swift
audioSession.setCategory(.playAndRecord, options: [.mixWithOthers, .allowBluetoothHFP])
```
