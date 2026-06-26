import { CheckCircle2, Circle, CircleDashed, CircleDot } from 'lucide-react';
import type * as React from 'react';
import type { ConversationStatus } from '@/lib/types';

/**
 * Renders the row's left status glyph for a sidebar conversation row.
 *
 * Distinct lucide glyphs per state (rather than `fill="currentColor"` on
 * a single circle) so the status colors render predictably across themes —
 * filled colors blend into hover backgrounds and lose contrast.
 */
export function ConversationStatusGlyph({ status }: { status: ConversationStatus }): React.JSX.Element {
  if (status === 'todo') {
    return (
      <div className="flex items-center justify-center text-info">
        <CircleDashed aria-hidden="true" className="size-3.5" strokeWidth={2} />
      </div>
    );
  }
  if (status === 'in_progress') {
    return (
      <div className="flex items-center justify-center text-warning">
        <CircleDot aria-hidden="true" className="size-3.5" strokeWidth={2} />
      </div>
    );
  }
  if (status === 'done') {
    return (
      <div className="flex items-center justify-center text-success">
        <CheckCircle2 aria-hidden="true" className="size-3.5" strokeWidth={2} />
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center text-muted-foreground/75">
      <Circle aria-hidden="true" className="size-3.5" strokeWidth={1.5} />
    </div>
  );
}
