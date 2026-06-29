'use client';

import { useReducer, useState } from 'react';
import { AccessRequestBannerView } from './AccessRequestBannerView';
import type { AccessRequestBannerProps, BannerState, Decision } from './types';

/** Max real avatars shown in the collapsed bar before collapsing into "+N". */
const MAX_COLLAPSED_AVATARS = 2;

// ---------------------------------------------------------------------------
// Internal banner state machine
// ---------------------------------------------------------------------------

/**
 * Internal state that the Component layer uses to track banner open/close.
 *
 * Extends the public {@link BannerState} by adding `nextExpandKey` to the
 * `collapsed` variant. This is an implementation detail: the View never
 * sees it. It exists because:
 * - `expandKey` belongs on `expanded` (it is only meaningful when the list
 *   is visible and must change on every open).
 * - When collapsing, we pre-compute `nextExpandKey = expandKey + 1` so the
 *   reducer can produce a new key on the next expand without any external
 *   counter or ref.
 *
 * This keeps the entire state machine self-contained in one `useReducer`.
 */
type InternalBannerState = { status: 'collapsed'; nextExpandKey: number } | { status: 'expanded'; expandKey: number };

/**
 * Pure state transition for the banner toggle.
 *
 * - `collapsed -> expanded`: promote `nextExpandKey` to the active key.
 * - `expanded -> collapsed`: store `expandKey + 1` as the next key, ready
 *   for the following open.
 *
 * No action payload is needed; toggle is the only transition.
 */
function reduceBannerState(state: InternalBannerState): InternalBannerState {
  if (state.status === 'collapsed') {
    return { status: 'expanded', expandKey: state.nextExpandKey };
  }
  return { status: 'collapsed', nextExpandKey: state.expandKey + 1 };
}

/** Strip internal fields before handing state to the View layer. */
function toBannerState(state: InternalBannerState): BannerState {
  if (state.status === 'expanded') {
    return state;
  }
  return { status: 'collapsed' };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Stateful Component layer for the access-request banner.
 *
 * Responsibilities (Component layer):
 * - Own all local state: `bannerState` (via reducer), `decisions`.
 * - Derive computed values from props (`collapsedAvatars`, `remainingCount`).
 * - Wire user interactions to state transitions and optional external callbacks.
 * - Render nothing when there are no pending requests.
 * - Delegate all presentation to {@link AccessRequestBannerView}.
 *
 * Why separate Component from View?
 * - The View is a pure function of props; trivially testable and previewable
 *   in isolation (e.g., Storybook) without needing to mock React state.
 * - This Component can be unit-tested by asserting what props it passes down,
 *   without mounting any DOM.
 * - If the banner ever needs server-driven state (for example, optimistic
 *   mutations), only this file changes; the View stays untouched.
 *
 * @example
 * ```tsx
 * <AccessRequestBanner
 *   requests={[{ id: "1", name: "Octavian Tocan" }]}
 *   onApprove={(id) => mutate({ id, action: "approve" })}
 *   onReject={(id) => mutate({ id, action: "reject" })}
 *   onReset={(id) => clearDraftDecision(id)}
 *   onDismiss={() => setVisible(false)}
 * />
 * ```
 */
export function AccessRequestBanner({ requests, onApprove, onReject, onReset, onDismiss }: AccessRequestBannerProps) {
  /**
   * Banner expand/collapse state machine.
   * Uses `InternalBannerState` (not the public `BannerState`) so the reducer
   * can pre-compute `nextExpandKey` on collapse without any external counter.
   * `nextExpandKey: 1` means the first expand gets key `1`.
   */
  const [internalBannerState, dispatchBannerToggle] = useReducer(reduceBannerState, {
    status: 'collapsed',
    nextExpandKey: 1,
  });

  /**
   * Local decision map keeps the banner's UI in sync immediately,
   * even before an optimistic server mutation resolves.
   * The parent's `onApprove` / `onReject` callbacks handle persistence.
   */
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  /** Optimistically marks a request as approved locally, then notifies the parent. */
  const handleApprove = (id: string) => {
    setDecisions((prev) => ({ ...prev, [id]: 'approved' }));
    onApprove?.(id);
  };

  /** Optimistically marks a request as rejected locally, then notifies the parent. */
  const handleReject = (id: string) => {
    setDecisions((prev) => ({ ...prev, [id]: 'rejected' }));
    onReject?.(id);
  };

  /** Reverts a decision back to undecided and mirrors that state to the parent. */
  const handleReset = (id: string) => {
    setDecisions((prev) => ({ ...prev, [id]: 'undecided' }));
    onReset?.(id);
  };

  // Nothing to show — bail before rendering anything.
  if (requests.length === 0) return null;

  // Precomputed for the View so it doesn't repeat slice/max logic.
  const collapsedAvatars = requests.slice(0, MAX_COLLAPSED_AVATARS);
  const remainingCount = Math.max(0, requests.length - MAX_COLLAPSED_AVATARS);

  return (
    <AccessRequestBannerView
      bannerState={toBannerState(internalBannerState)}
      collapsedAvatars={collapsedAvatars}
      decisions={decisions}
      onApproveRequest={handleApprove}
      onDismiss={onDismiss}
      onRejectRequest={handleReject}
      onResetRequest={handleReset}
      onToggleExpand={dispatchBannerToggle}
      remainingCount={remainingCount}
      requests={requests}
    />
  );
}
