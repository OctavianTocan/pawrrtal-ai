'use client';

import { domAnimation, LayoutGroup, LazyMotion } from 'motion/react';
import { BannerHeader } from './BannerHeader';
import { ExpandedRequestList } from './ExpandedRequestList';
import type { AccessRequestBannerViewProps } from './types';

/**
 * Pure presentation layer for the access-request banner.
 *
 * This component is intentionally thin — it owns no state and contains no
 * animation or layout logic of its own. Its only job is to compose the two
 * structural pieces (`BannerHeader` and `ExpandedRequestList`) inside the
 * shared `LayoutGroup` that enables Motion's cross-component layout
 * animations (the avatar hero transitions).
 *
 * **WHY `LayoutGroup` here and not further down?**
 * `LayoutGroup` must wrap *all* components that share `layoutId` values. The
 * avatar `layoutId`s are used in both `BannerHeader` (collapsed stack) and
 * `RequestRow` (expanded rows), which live in separate subtrees. Placing
 * `LayoutGroup` at the view root ensures Motion can track the same id across
 * both subtrees and animate the positional hand-off.
 *
 * **WHY no `layout` on the outer card?**
 * The `ExpandedRequestList` already animates its own `height: 0 → auto`.
 * Adding `layout` to the card would make Motion *also* spring-animate the
 * card's bounding box in response to the content change — two springs
 * fighting each other, causing a compounded double-bounce.
 * `overflow-hidden` prevents content from peeking outside the card during
 * the height tween.
 *
 * @see {@link AccessRequestBanner} for the stateful Component that drives this View.
 * @see {@link BannerHeader} for the header row (toggle + dismiss).
 * @see {@link ExpandedRequestList} for the sliding user-row panel.
 */
export function AccessRequestBannerView({
  requests,
  bannerState,
  decisions,
  collapsedAvatars,
  remainingCount,
  onToggleExpand,
  onDismiss,
  onApproveRequest,
  onRejectRequest,
  onResetRequest,
}: AccessRequestBannerViewProps) {
  return (
    <LazyMotion features={domAnimation}>
      <LayoutGroup>
        <div className="w-full overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <BannerHeader
            bannerState={bannerState}
            collapsedAvatars={collapsedAvatars}
            onDismiss={onDismiss}
            onToggleExpand={onToggleExpand}
            remainingCount={remainingCount}
            requests={requests}
          />

          <ExpandedRequestList
            bannerState={bannerState}
            decisions={decisions}
            onApproveRequest={onApproveRequest}
            onRejectRequest={onRejectRequest}
            onResetRequest={onResetRequest}
            requests={requests}
          />
        </div>
      </LayoutGroup>
    </LazyMotion>
  );
}
