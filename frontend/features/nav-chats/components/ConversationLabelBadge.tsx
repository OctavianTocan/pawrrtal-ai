/**
 * @file ConversationLabelBadge.tsx
 *
 * Renders a small colored pill for a conversation label in the sidebar.
 *
 * Labels can arrive as either structured objects (from the API) or plain
 * strings (legacy format, e.g. "status:active"). The normalizer handles
 * both so the rendering path doesn't need to branch.
 *
 * The pill intercepts all pointer/click events to prevent accidentally
 * selecting or navigating the parent conversation row when the user
 * interacts with the label itself.
 */
'use client';

import type { ConversationLabel } from '@/lib/types';

/** Derive badge background/text colors from the label's color, falling back to theme defaults. */
function resolveBadgeColor(label: ConversationLabel): { backgroundColor: string; color: string } {
  if (label.color) {
    return {
      backgroundColor: `color-mix(in srgb, ${label.color} 6%, transparent)`,
      color: `color-mix(in srgb, ${label.color} 75%, var(--foreground))`,
    };
  }

  return {
    backgroundColor: 'rgba(var(--foreground-rgb), 0.05)',
    color: 'rgba(var(--foreground-rgb), 0.8)',
  };
}

/**
 * Convert a string label like "status:active" into a structured ConversationLabel.
 * Splits on the FIRST colon only so values containing colons are preserved intact.
 * If the label is already an object, returns it unchanged.
 */
function normalizeConversationLabel(label: ConversationLabel | string): ConversationLabel {
  if (typeof label !== 'string') {
    return label;
  }

  const separatorIndex = label.indexOf(':');

  let namePart: string;
  let valuePart: string | undefined;

  if (separatorIndex === -1) {
    namePart = label;
  } else {
    namePart = label.slice(0, separatorIndex);
    valuePart = label.slice(separatorIndex + 1);
  }

  return {
    id: namePart.trim().toLowerCase().replace(/\s+/g, '-'),
    name: namePart.trim(),
    value: valuePart?.trim(),
  };
}

/**
 * Renders a single label as a colored pill. Accepts both structured and
 * string labels. Stops event propagation so clicking the pill doesn't
 * trigger the parent row's selection/navigation handler.
 */
export function ConversationLabelBadge({ label }: { label: ConversationLabel | string }): React.JSX.Element {
  const normalized = normalizeConversationLabel(label);
  const style = resolveBadgeColor(normalized);

  return (
    <div
      className="flex h-[18px] max-w-[120px] shrink-0 items-center gap-0.5 whitespace-nowrap rounded px-1.5 font-medium text-[10px]"
      onClick={(event) => {
        event.stopPropagation();
      }}
      onMouseDown={(event) => {
        event.stopPropagation();
        event.preventDefault();
      }}
      onPointerDown={(event) => {
        event.stopPropagation();
      }}
      role="presentation"
      style={style}
    >
      <span className="truncate">{normalized.name}</span>
      {normalized.value ? (
        <>
          <span style={{ opacity: 0.4 }}>·</span>
          <span className="min-w-0 truncate font-normal" style={{ opacity: 0.75 }}>
            {normalized.value}
          </span>
        </>
      ) : null}
    </div>
  );
}
