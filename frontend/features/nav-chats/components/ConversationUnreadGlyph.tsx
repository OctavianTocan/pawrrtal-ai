import type * as React from 'react';

/**
 * Small filled chat-bubble glyph rendered immediately to the LEFT of the
 * conversation title when `is_unread` is true. Mirrors the reference
 * Stitch sidebar look — pushes the title rightward so the unread state
 * reads at a glance even before the user notices the bolder font weight.
 */
export function ConversationUnreadGlyph(): React.JSX.Element {
  return (
    <svg aria-hidden="true" className="size-3 text-accent" fill="currentColor" viewBox="0 0 24 24">
      <title>Unread</title>
      <path d="M2 5.5A3.5 3.5 0 015.5 2h13A3.5 3.5 0 0122 5.5v9a3.5 3.5 0 01-3.5 3.5h-7l-4.5 3.5v-3.5h-1.5A3.5 3.5 0 012 14.5v-9z" />
    </svg>
  );
}
