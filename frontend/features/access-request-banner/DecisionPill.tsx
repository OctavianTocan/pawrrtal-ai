'use client';

import { IconCheck, IconX } from '@tabler/icons-react';
import * as m from 'motion/react-m';
import type { Decision } from './types';
import { BOUNCY_SPRING } from './types';

/**
 * Sliding pill toggle for approve/reject decisions.
 *
 * Both sides always render with fixed widths so the pill never
 * changes size when a decision is made (prevents layout shift).
 * A sliding highlight indicator animates between positions.
 * Uses neutral muted colors. Clicking the active side resets
 * to undecided (reversible).
 */
export function DecisionPill({
  decision,
  onApprove,
  onReject,
  onReset,
  /** Unique ID to scope the layoutId so multiple pills don't conflict */
  pillId,
}: {
  decision: Decision;
  onApprove: () => void;
  onReject: () => void;
  onReset: () => void;
  pillId: string;
}) {
  const isApproved = decision === 'approved';
  const isRejected = decision === 'rejected';
  const isDecided = isApproved || isRejected;

  return (
    /* Fixed width prevents layout shift when text changes.
		   Both halves are always the same size via grid columns. */
    <div className="relative grid w-[160px] shrink-0 grid-cols-2 overflow-hidden rounded-full border border-border">
      {/* Sliding highlight: animates between left/right halves via layoutId */}
      {isDecided && (
        <m.div
          className={`absolute inset-y-0 w-1/2 rounded-full bg-muted ${isApproved ? 'left-0' : 'left-1/2'}`}
          layoutId={`pill-highlight-${pillId}`}
          transition={BOUNCY_SPRING}
        />
      )}

      {/* Approve side: always rendered, always same grid cell width */}
      <m.button
        className={`relative z-10 flex cursor-pointer items-center justify-center gap-1 py-1 font-medium text-xs transition-colors ${
          isApproved ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
        }`}
        onClick={isApproved ? onReset : onApprove}
        type="button"
        whileTap={{ scale: 0.95 }}
      >
        {isApproved && <IconCheck className="size-3" />}
        {isApproved ? 'Approved' : 'Approve'}
      </m.button>

      {/* Reject side: always rendered, always same grid cell width */}
      <m.button
        className={`relative z-10 flex cursor-pointer items-center justify-center gap-1 border-border border-l py-1 font-medium text-xs transition-colors ${
          isRejected ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
        }`}
        onClick={isRejected ? onReset : onReject}
        type="button"
        whileTap={{ scale: 0.95 }}
      >
        {isRejected && <IconX className="size-3" />}
        {isRejected ? 'Rejected' : 'Reject'}
      </m.button>
    </div>
  );
}
