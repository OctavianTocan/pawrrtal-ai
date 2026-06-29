---
name: clear-timers-on-spam
paths: ["**/*.{ts,tsx,js,jsx}"]
---

# Clear Timers Before Re-Triggering State Flips

Buttons that flash a state then revert (copy → checkmark → unmount, save →
toast → fade, error → shake → reset) MUST store the timeout/interval in a
`useRef` and clear the previous one before scheduling a new one. The rule
of thumb: **your UI is only as polished as its worst spam test.** If a
user can spam-click a button hard enough to trigger UI desync, the
component is broken — even if the user-visible behavior looks fine in
normal use.

Spamming an unprotected timer-flip pattern produces:

- **Old timeouts firing mid-animation**, yanking the visual state away
  unexpectedly. The "checkmark vanishes a frame after the next click"
  bug.
- **State desync** — a second click while the first checkmark is still
  showing schedules a new revert; both timers fire, the second tears
  down state the first attempted to restore.
- **Memory leaks** from accumulated unfired timers, especially with
  long-lived components (chat windows, kanban boards).

This rule applies to:

- Copy-to-clipboard buttons that flash a checkmark.
- Save buttons that flash "Saved!" then revert.
- Error states that show a shake animation and reset.
- Any component that calls `setTimeout` / `setInterval` and revisits
  the same state on re-trigger.

## Verify

"Does this component flash a state then revert via `setTimeout`? Is the
timeout stored in a `useRef`? Is the previous timer cleared before
scheduling a new one? Is the timer cleared on unmount?"

## Patterns

Bad — naked `setTimeout`, accumulates leaks, breaks under spam:

```tsx
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000); // ← leak risk
      }}
    >
      {copied ? <Check /> : <Copy />}
    </button>
  );
}
```

Spamming this 5 times in a row schedules 5 separate `setCopied(false)`
calls — the first 4 fire while the visible state is `true`, briefly
flipping the checkmark off and on. The cumulative effect is a
flickering icon for the duration of the slowest timer.

Good — ref-stored, cleared before re-scheduling, cleared on unmount:

```tsx
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Clear on unmount so a stale setCopied(false) doesn't fire after
  // the component is gone.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        // Clear the previous timer before scheduling a new one. This is
        // the spam-resistance — every click resets the "show success"
        // window cleanly, no overlap.
        if (timerRef.current) clearTimeout(timerRef.current);
        setCopied(true);
        timerRef.current = setTimeout(() => {
          setCopied(false);
          timerRef.current = undefined;
        }, 2000);
      }}
    >
      {copied ? <Check /> : <Copy />}
    </button>
  );
}
```

Even better — extract the pattern into a reusable hook:

```ts
/** Flashes a boolean true for `durationMs`, resetting the window on each call. */
function useFlashState(durationMs: number): readonly [boolean, () => void] {
  const [active, setActive] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const flash = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setActive(true);
    timerRef.current = setTimeout(() => {
      setActive(false);
      timerRef.current = undefined;
    }, durationMs);
  }, [durationMs]);

  return [active, flash];
}

// Consumer:
function CopyButton({ text }: { text: string }) {
  const [copied, flashCopied] = useFlashState(2000);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        flashCopied();
      }}
    >
      {copied ? <Check /> : <Copy />}
    </button>
  );
}
```

## Same logic applies to setInterval

Polling intervals must be ref-stored and cleared on unmount; restarting
the same interval (e.g. on prop change) must clear the previous one
before starting the new one. The agent-spinner in
`frontend/components/ui/agent-spinner.tsx` is a clean reference example.

## Same logic applies to `requestAnimationFrame`

`rAF` IDs returned from `requestAnimationFrame` must be `cancelAnimationFrame`-ed
on rerun. SSE/WebSocket consumers that batch updates via `rAF` (see the
"buffer-high-frequency-stream-updates" rule) already follow this pattern.
