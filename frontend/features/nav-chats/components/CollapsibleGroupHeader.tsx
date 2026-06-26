'use client';

import { SidebarSectionHeader } from '@/components/ui/sidebar-section-header';

interface CollapsibleGroupHeaderProps {
  /** The date-group label text (e.g. "Today", "Yesterday", "Mar 25"). */
  label: string;
  /** Whether this group is currently collapsed. */
  isCollapsed: boolean;
  /** Number of items hidden behind the collapsed state. */
  itemCount: number;
  /** Called when the user clicks to toggle the group open/closed. */
  onToggle: () => void;
}

/**
 * A clickable section header for a conversation date group.
 *
 * Shows a chevron that rotates when expanded, the group label, and —
 * when collapsed — an item count badge so the user knows how many
 * conversations are hidden.
 */
export function CollapsibleGroupHeader({
  label,
  isCollapsed,
  itemCount,
  onToggle,
}: CollapsibleGroupHeaderProps): React.JSX.Element {
  return (
    <li>
      <SidebarSectionHeader
        collapsedMetaCount={itemCount}
        isCollapsed={isCollapsed}
        label={label}
        onToggle={onToggle}
        variant="collapsible"
      />
    </li>
  );
}
