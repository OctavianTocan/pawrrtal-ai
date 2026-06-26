/**
 * Status submenu metadata for conversation rows.
 *
 * @fileoverview Extracted from `ConversationStatusGlyph.tsx` so the component
 * file only exports React components (react-doctor `only-export-components`).
 */

import { CheckCircle2, Circle, CircleDashed, CircleDot } from 'lucide-react';
import type { ConversationStatus } from '@/lib/types';

/**
 * Catalog of status submenu rows surfaced in the chat row's right-click /
 * dropdown menu. Lives next to the glyph so the icon / status mapping
 * stays in one place.
 */
export const STATUS_SUBMENU = [
  { id: 'todo' as const, label: 'Todo', Icon: CircleDashed, className: 'text-info' },
  {
    id: 'in_progress' as const,
    label: 'In Progress',
    Icon: CircleDot,
    className: 'text-warning',
  },
  { id: 'done' as const, label: 'Done', Icon: CheckCircle2, className: 'text-success' },
  { id: null, label: 'No status', Icon: Circle, className: 'text-muted-foreground' },
] as const satisfies ReadonlyArray<{
  id: ConversationStatus;
  label: string;
  Icon: typeof Circle;
  className: string;
}>;
