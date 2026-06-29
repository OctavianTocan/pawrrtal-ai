'use client';

import { IconChevronDown, IconX } from '@tabler/icons-react';
import { AnimatePresence } from 'motion/react';
import * as m from 'motion/react-m';
import { Avatar, AvatarFallback, AvatarGroup, AvatarGroupCount, AvatarImage } from '@/components/ui/avatar';
import { SummaryText } from './SummaryText';
import type { AccessRequest, BannerHeaderProps, BannerState } from './types';
import { BOUNCY_SPRING, getInitials, TEXT_SWAP_SPRING } from './types';

// ---------------------------------------------------------------------------
// Private sub-components — not exported; only used within this file.
// ---------------------------------------------------------------------------

/**
 * Renders the collapsed avatar stack with an optional overflow count bubble.
 *
 * Only mounted when the banner is in its collapsed state. Unmounting (rather
 * than hiding) is intentional: each avatar carries a Motion `layoutId`, so
 * when the banner expands this element disappears from the DOM and the
 * matching `layoutId` appears inside the expanded rows — triggering Motion's
 * shared-layout "hero" animation that bounces avatars from the header to
 * their row positions.
 *
 * Avatars are assigned descending `z-index` values so the leftmost avatar
 * sits visually on top, matching the standard left-overlap stack convention.
 */
function CollapsedAvatarGroup({
  collapsedAvatars,
  remainingCount,
}: {
  collapsedAvatars: AccessRequest[];
  remainingCount: number;
}) {
  return (
    <AvatarGroup>
      {collapsedAvatars.map((r, i) => (
        <m.div
          key={r.id}
          layoutId={`avatar-${r.id}`}
          // Leftmost avatar (i=0) gets the highest z-index
          style={{ zIndex: collapsedAvatars.length - i + 1 }}
          transition={BOUNCY_SPRING}
        >
          <Avatar>
            {r.avatarUrl && <AvatarImage alt={r.name} src={r.avatarUrl} />}
            <AvatarFallback>{getInitials(r.name)}</AvatarFallback>
          </Avatar>
        </m.div>
      ))}

      {/* Overflow bubble — only rendered when requests exceed the collapsed limit */}
      {remainingCount > 0 && (
        <AvatarGroupCount>
          <span className="text-xs">+{remainingCount}</span>
        </AvatarGroupCount>
      )}
    </AvatarGroup>
  );
}

/**
 * Shows either the "Access Requests" title (expanded) or the summary text
 * (collapsed) with a purely vertical swap animation.
 */
function HeaderTextBlock({ bannerState, requests }: { bannerState: BannerState; requests: AccessRequest[] }) {
  return (
    <div className="min-w-0 flex-1 overflow-hidden">
      <AnimatePresence initial={false} mode="popLayout">
        {bannerState.status === 'expanded' ? (
          <m.div
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -16, filter: 'blur(4px)' }}
            initial={{ opacity: 0, y: -16, filter: 'blur(4px)' }}
            key="title"
            transition={TEXT_SWAP_SPRING}
          >
            <span className="block font-semibold text-foreground text-sm">Access Requests</span>
          </m.div>
        ) : (
          <m.div
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: 16, filter: 'blur(4px)' }}
            initial={{ opacity: 0, y: 16, filter: 'blur(4px)' }}
            key="summary"
            transition={TEXT_SWAP_SPRING}
          >
            <SummaryText requests={requests} />
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exported component
// ---------------------------------------------------------------------------

/**
 * Header row for the access-request banner.
 */
export function BannerHeader({
  bannerState,
  requests,
  collapsedAvatars,
  remainingCount,
  onToggleExpand,
  onDismiss,
}: BannerHeaderProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <button
        aria-expanded={bannerState.status === 'expanded'}
        aria-label={bannerState.status === 'expanded' ? 'Collapse access requests' : 'Expand access requests'}
        className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
        onClick={onToggleExpand}
        type="button"
      >
        {/* Unmounted when expanded so the layoutId hero animation can fire */}
        {bannerState.status === 'collapsed' && (
          <CollapsedAvatarGroup collapsedAvatars={collapsedAvatars} remainingCount={remainingCount} />
        )}

        <HeaderTextBlock bannerState={bannerState} requests={requests} />

        <m.div
          animate={{ rotate: bannerState.status === 'expanded' ? 180 : 0 }}
          className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          transition={BOUNCY_SPRING}
        >
          <IconChevronDown className="size-4" />
        </m.div>
      </button>

      {onDismiss && (
        <button
          aria-label="Dismiss"
          className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={onDismiss}
          type="button"
        >
          <IconX className="size-4" />
        </button>
      )}
    </div>
  );
}
