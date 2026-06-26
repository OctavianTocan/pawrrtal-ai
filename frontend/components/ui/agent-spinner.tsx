/**
 * Terminal-style braille-dot agent spinner.
 *
 * Web port of {@link https://github.com/Eronred/expo-agent-spinners DotsSpinner}.
 * Cycles through Unicode braille frames at a fixed interval — no SVG, no CSS
 * animation, just `setInterval` swapping a `<span>` text node. Stable layout
 * because the container is fixed-size and braille glyphs are monospace-width.
 *
 * @fileoverview Drop-in replacement for spinner icons in chat/agent loaders.
 */

'use client';

import { type CSSProperties, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

/** Braille frames — same set used by the upstream `dots` spinner. */
const BRAILLE_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'] as const;

/** Frame interval in milliseconds. Matches the upstream library default. */
const FRAME_INTERVAL_MS = 80;

/**
 * Props for {@link AgentSpinner}.
 */
export interface AgentSpinnerProps {
  /** Glyph font-size in pixels. Defaults to 16. */
  size?: number;
  /** Extra class names for the wrapper span. */
  className?: string;
  /** Optional inline style overrides for the wrapper span. */
  style?: CSSProperties;
}

/**
 * Renders an animated braille-dot spinner that cycles every 80 ms.
 *
 * @param props - Spinner sizing and styling.
 * @returns A span element containing the current animation frame.
 */
export function AgentSpinner({ size = 16, className, style }: AgentSpinnerProps): React.JSX.Element {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const id = window.setInterval(
      () => setFrame((current) => (current + 1) % BRAILLE_FRAMES.length),
      FRAME_INTERVAL_MS
    );
    return () => window.clearInterval(id);
  }, []);

  return (
    <span
      aria-hidden="true"
      className={cn('inline-flex items-center justify-center font-mono leading-none', className)}
      style={{
        fontSize: size,
        // Fixed width ≈ 1.2em keeps adjacent text from shifting between frames.
        width: `${size * 1.2}px`,
        height: `${size * 1.2}px`,
        ...style,
      }}
    >
      {BRAILLE_FRAMES[frame]}
    </span>
  );
}
