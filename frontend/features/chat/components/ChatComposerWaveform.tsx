'use client';

import type * as React from 'react';

/**
 * Bar heights (px) used by the scrolling waveform timeline. The pattern
 * is intentionally jagged so the rendered timeline reads as "live audio"
 * rather than a synthesizer-style equalizer; the array is doubled and
 * scrolled with a CSS animation to give the illusion of continuous flow.
 */
const WAVEFORM_BARS = [
  6, 10, 8, 14, 22, 18, 12, 28, 20, 14, 8, 18, 24, 16, 10, 6, 12, 20, 28, 22, 14, 10, 16, 24, 18, 12, 8, 14, 20, 26, 18,
  12, 8, 16, 22, 28, 20, 14, 10, 6,
] as const;
const WAVEFORM_BAR_FRAMES = WAVEFORM_BARS.flatMap((height, barIndex) => [
  { id: `first-${barIndex}`, height },
  { id: `second-${barIndex}`, height },
]);

interface WaveformTimelineProps {
  isPaused: boolean;
  /** Normalized RMS (0–1); scales bar heights while recording. */
  meterLevel: number;
}

/**
 * Continuously scrolling bar timeline used as the recording-state
 * indicator. Renders the bars twice end-to-end and translates the
 * inner strip leftward via CSS keyframe so the result reads as
 * "audio scrolling past a playhead" without an actual analyser node.
 *
 * `isPaused=true` halts the scroll (used while transcribing) so the
 * UI feels frozen on the captured timeline rather than ticking forward
 * after the recording ended.
 */
export function WaveformTimeline({ isPaused, meterLevel }: WaveformTimelineProps): React.JSX.Element {
  const level = Number.isFinite(meterLevel) ? meterLevel : 0;
  const gain = 0.35 + level * 0.85;

  return (
    <div className="relative flex h-8 min-w-0 flex-1 justify-end overflow-hidden">
      <div
        aria-hidden="true"
        className="flex h-full items-end gap-[3px]"
        style={{
          animation: isPaused ? undefined : 'waveform-scroll 6s linear infinite',
        }}
      >
        {WAVEFORM_BAR_FRAMES.map((bar) => (
          <span
            className="w-[2px] shrink-0 rounded-full bg-foreground/75"
            key={bar.id}
            style={{
              height: Math.max(3, bar.height * gain),
              opacity: 0.4 + ((bar.height % 5) / 5) * 0.6,
            }}
          />
        ))}
      </div>
      {/* Fade the seam on the right where older samples scroll away. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-[color:var(--background-elevated)] to-transparent"
      />
    </div>
  );
}
