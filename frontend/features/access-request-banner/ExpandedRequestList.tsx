'use client';

import { AnimatePresence } from 'motion/react';
import * as m from 'motion/react-m';
import { RequestRow } from './RequestRow';
import type { ExpandedRequestListProps } from './types';
import { EXPAND_SPRING } from './types';

/**
 * Sliding animated panel that reveals the per-user request rows.
 *
 * **Height animation** — the panel animates `height: 0 → "auto"` using
 * `EXPAND_SPRING` so the card feels weighty as it opens, not snappy.
 * Motion handles the `height: auto` tween internally via layout animation.
 *
 * **WHY `key={bannerState.expandKey}` on the inner `motion.div`?**
 * `AnimatePresence` only re-runs entry animations when a child's key changes.
 * Without bumping the key, collapsing and re-expanding the banner shows the
 * list without the staggered row bounces — Motion sees the same key and skips
 * `initial → animate`. The Component layer's reducer increments `expandKey`
 * on every expand, guaranteeing a fresh mount and fresh animations each time.
 *
 * Because `expandKey` lives on the `expanded` variant of `BannerState`,
 * TypeScript's narrowing inside the `status === "expanded"` branch makes the
 * access type-safe — no non-null assertion or separate prop needed.
 *
 * **WHY a thin `<div>` separator instead of a `border-t` on the panel?**
 * Applying `border-t` directly to the `motion.div` means it flashes during
 * the height-from-zero animation. A separate static `<div>` renders cleanly
 * at full width from frame one.
 */
export function ExpandedRequestList({
  bannerState,
  requests,
  decisions,
  onApproveRequest,
  onRejectRequest,
  onResetRequest,
}: ExpandedRequestListProps) {
  return (
    <AnimatePresence>
      {bannerState.status === 'expanded' && (
        // expandKey is only accessible here because TypeScript has narrowed
        // bannerState to the `expanded` variant — the union does the guarding.
        <m.div
          animate={{ height: 'auto', opacity: 1 }}
          className="overflow-hidden"
          exit={{ height: 0, opacity: 0 }}
          initial={{ height: 0, opacity: 0 }}
          key={bannerState.expandKey}
          transition={EXPAND_SPRING}
        >
          <div className="border-border border-t" />
          <div className="py-1">
            {requests.map((request) => (
              <RequestRow
                decision={decisions[request.id] ?? 'undecided'}
                key={request.id}
                onApprove={() => onApproveRequest(request.id)}
                onReject={() => onRejectRequest(request.id)}
                onReset={() => onResetRequest(request.id)}
                request={request}
              />
            ))}
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
}
