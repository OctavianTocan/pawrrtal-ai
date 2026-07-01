'use client';

import * as m from 'motion/react-m';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { DecisionPill } from './DecisionPill';
import type { RequestRowProps } from './types';
import { BOUNCY_SPRING, getInitials } from './types';

/**
 * A single user row inside the expanded access-request list.
 *
 * Three animated elements enter together when the list mounts:
 * - **Avatar** — uses a Motion `layoutId` matching its collapsed counterpart
 *   in the header. Motion physically animates it bouncing from the header
 *   position to this row — the "hero" transition that makes the expand feel
 *   alive.
 * - **Name** — bounces in with a scale (`0.7 → 1`) to echo the avatar's
 *   playful spring and reinforce that the row is "arriving".
 * - **DecisionPill** — scales up slightly (`0.85 → 1`) with the same spring,
 *   keeping the row entry feeling cohesive.
 *
 * The row itself fades in (opacity `0 → 1`) as a cheap catch-all for when
 * the avatar doesn't have a matching collapsed layoutId (e.g., requests
 * beyond `MAX_COLLAPSED_AVATARS`).
 */
export function RequestRow({ request, decision, onApprove, onReject, onReset }: RequestRowProps) {
  return (
    <m.div
      animate={{ opacity: 1 }}
      className="flex items-center justify-between gap-3 px-4 py-2"
      initial={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
    >
      <div className="flex items-center gap-3">
        {/*
         * layoutId matches the collapsed avatar in BannerHeader so Motion
         * creates a shared-layout transition: the avatar appears to physically
         * fly from the header group into this row position on expand.
         */}
        <m.div layoutId={`avatar-${request.id}`} transition={BOUNCY_SPRING}>
          <Avatar size="sm">
            {request.avatarUrl && <AvatarImage alt={request.name} src={request.avatarUrl} />}
            <AvatarFallback>{getInitials(request.name)}</AvatarFallback>
          </Avatar>
        </m.div>

        {/* Scale bounce echoes the avatar spring for a cohesive row entry */}
        <m.span
          animate={{ scale: 1, opacity: 1 }}
          className="font-medium text-sm"
          initial={{ scale: 0.92, opacity: 0 }}
          transition={BOUNCY_SPRING}
        >
          {request.name}
        </m.span>
      </div>

      {/* Same spring as the name so the entire right side arrives together */}
      <m.div animate={{ scale: 1, opacity: 1 }} initial={{ scale: 0.85, opacity: 0 }} transition={BOUNCY_SPRING}>
        <DecisionPill
          decision={decision}
          onApprove={onApprove}
          onReject={onReject}
          onReset={onReset}
          pillId={request.id}
        />
      </m.div>
    </m.div>
  );
}
