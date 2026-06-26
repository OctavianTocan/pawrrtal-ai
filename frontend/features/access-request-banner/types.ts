/**
 * Discriminated union for the banner's expand/collapse state.
 *
 * **WHY a union instead of `isExpanded: boolean` + `expandKey: number`?**
 * `expandKey` is only meaningful when the banner is open — a collapsed banner
 * has no list to key. Pairing it with `status: "expanded"` makes the
 * relationship explicit and prevents callers from passing an `expandKey` that
 * silently goes unused in the collapsed state. TypeScript narrows the type
 * at every usage site, so `bannerState.expandKey` is only accessible inside
 * an `bannerState.status === "expanded"` branch.
 */
export type BannerState = { status: 'collapsed' } | { status: 'expanded'; expandKey: number };

/** A single access request entry. */
export type AccessRequest = {
  id: string;
  name: string;
  avatarUrl?: string;
};

/** Decision state for a single access request. */
export type Decision = 'undecided' | 'approved' | 'rejected';

/** Props for the {@link AccessRequestBanner} component (public API). */
export type AccessRequestBannerProps = {
  /** All pending access requests to display. An empty array renders nothing. */
  requests: AccessRequest[];
  /** Called when the user approves a request. Receives the request's `id`. */
  onApprove?: (id: string) => void;
  /** Called when the user rejects a request. Receives the request's `id`. */
  onReject?: (id: string) => void;
  /** Called when the user clears a previously chosen decision. */
  onReset?: (id: string) => void;
  /** Called when the user dismisses the entire banner. */
  onDismiss?: () => void;
};

/**
 * Props for the {@link AccessRequestBannerView} presentation component.
 *
 * Every value that the View needs is passed explicitly — no internal state.
 * This is the contract between the Component layer and the View layer.
 *
 * Naming convention for callbacks:
 * - `onToggleExpand` — UI interaction with no payload (the Component owns the state).
 * - `onApproveRequest` / `onRejectRequest` / `onResetRequest` — scoped to a single
 *   request id; named differently from the public `onApprove`/`onReject` to make it
 *   clear these are internal, already-bound handlers rather than raw external callbacks.
 */
export type AccessRequestBannerViewProps = {
  /** Full list of requests; passed through so the View can iterate rows. */
  requests: AccessRequest[];
  /**
   * Current expand/collapse state of the banner.
   * The `expanded` variant carries `expandKey` — the key that forces
   * AnimatePresence to re-mount the list for fresh stagger animations.
   */
  bannerState: BannerState;
  /** Per-request decision map; drives the DecisionPill selected state. */
  decisions: Record<string, Decision>;
  /**
   * Pre-sliced avatar list for the collapsed header (≤ MAX_COLLAPSED_AVATARS).
   * Derived in the Component so the View doesn't repeat the slice logic.
   */
  collapsedAvatars: AccessRequest[];
  /**
   * Number of requests beyond the collapsed avatar limit.
   * Rendered as the "+N" overflow count bubble. 0 means no bubble shown.
   */
  remainingCount: number;
  /** Fired when the user clicks/keys the header bar to open or close the list. */
  onToggleExpand: () => void;
  /** Forwarded from the public `onDismiss` prop; optional so callers can omit it. */
  onDismiss?: () => void;
  /** Approves the given request id and notifies the parent. */
  onApproveRequest: (id: string) => void;
  /** Rejects the given request id and notifies the parent. */
  onRejectRequest: (id: string) => void;
  /** Reverts the given request's decision back to undecided. */
  onResetRequest: (id: string) => void;
};

/**
 * Props for the {@link BannerHeader} internal component.
 *
 * Owns the toggle button (avatars + text crossfade + chevron) and the
 * sibling dismiss button. Kept internal — not exported from the barrel.
 */
export type BannerHeaderProps = {
  /** Current expand/collapse state; drives avatar group visibility and chevron rotation. */
  bannerState: BannerState;
  /** Full request list — forwarded to `SummaryText` for the collapsed label. */
  requests: AccessRequest[];
  /**
   * Pre-sliced avatar list for the collapsed state (≤ MAX_COLLAPSED_AVATARS).
   * Derived by the Component layer so this component stays free of slice logic.
   */
  collapsedAvatars: AccessRequest[];
  /** Number of requests beyond the visible avatar limit; renders "+N" bubble when > 0. */
  remainingCount: number;
  /** Fired when the user clicks the toggle button or activates it via keyboard. */
  onToggleExpand: () => void;
  /** Forwarded from the public `onDismiss` prop. */
  onDismiss?: () => void;
};

/**
 * Props for the {@link RequestRow} internal component.
 *
 * Represents a single user row in the expanded list. Kept internal — not
 * exported from the barrel.
 */
export type RequestRowProps = {
  /** The request this row represents. */
  request: AccessRequest;
  /** Current decision for this request; drives the DecisionPill state. */
  decision: Decision;
  /** Called when the approve side of the pill is activated. */
  onApprove: () => void;
  /** Called when the reject side of the pill is activated. */
  onReject: () => void;
  /** Called when the active side is re-clicked to revert to undecided. */
  onReset: () => void;
};

/**
 * Props for the {@link ExpandedRequestList} internal component.
 *
 * Owns the AnimatePresence sliding panel and iterates {@link RequestRow}s.
 * Kept internal — not exported from the barrel.
 */
export type ExpandedRequestListProps = {
  /**
   * Current expand/collapse state. The `expanded` variant's `expandKey` is
   * used directly as the `motion.div` key — TypeScript narrowing inside the
   * `status === "expanded"` branch makes the key access type-safe without
   * an extra prop or non-null assertion.
   */
  bannerState: BannerState;
  /** Full list of requests to render as rows. */
  requests: AccessRequest[];
  /** Per-request decision map passed down to each `RequestRow`. */
  decisions: Record<string, Decision>;
  /** Approves the request with the given id. */
  onApproveRequest: (id: string) => void;
  /** Rejects the request with the given id. */
  onRejectRequest: (id: string) => void;
  /** Reverts the request with the given id back to undecided. */
  onResetRequest: (id: string) => void;
};

/**
 * Spring config reused across all bouncy animations in this component family.
 *
 * Damping was increased from 15 → 20 (~30% reduction in overshoot) to feel
 * lively without being distractingly springy on repeated open/close cycles.
 */
export const BOUNCY_SPRING = {
  type: 'spring' as const,
  stiffness: 300,
  damping: 20,
};

/**
 * Critically-damped spring for the card expand/collapse.
 *
 * Uses high damping relative to stiffness so the height settles smoothly
 * into place without overshooting. This prevents the card from "bouncing"
 * (growing past its final height then snapping back), which felt jarring
 * when combined with the inner row animations.
 *
 * The playful bounce is preserved on micro-interactions (avatars, pills)
 * via `BOUNCY_SPRING` — the card itself stays calm.
 */
export const EXPAND_SPRING = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 40,
};

/**
 * Spring for the header text swap (title ↔ summary crossfade).
 *
 * Matches the stiffness/damping used by the chevron rotation so all
 * header-level transitions feel like a single cohesive gesture.
 */
export const TEXT_SWAP_SPRING = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 30,
};

/**
 * Extracts up to 2 initials from a full name for avatar fallbacks.
 *
 * "Octavian Tocan" -> "OT", "Jane" -> "J"
 */
export function getInitials(name: string): string {
  name = name.trim();
  if (!name) {
    return '';
  }

  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((n) => n[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase();
}
