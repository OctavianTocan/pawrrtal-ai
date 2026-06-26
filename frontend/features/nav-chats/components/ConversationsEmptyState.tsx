import type { ReactNode } from 'react';
import { AppEmptyState } from '@/components/ui/app-empty-state';

interface ConversationsEmptyStateProps {
  /** Icon rendered inside a subtle container above the title. */
  icon: ReactNode;
  /** Primary heading text. */
  title: string;
  /** Secondary description shown below the heading. */
  description: string;
  /** Optional CTA button label. Omit to hide the button. */
  buttonLabel?: string;
  /** Called when the CTA button is clicked. Required when `buttonLabel` is set. */
  onAction?: () => void;
}

/**
 * Centred empty-state placeholder for the conversations sidebar.
 *
 * Used for both the "no sessions yet" and "no search results" states.
 * Optionally renders a call-to-action button when `buttonLabel` is provided.
 */
export function ConversationsEmptyState({
  icon,
  title,
  description,
  buttonLabel,
  onAction,
}: ConversationsEmptyStateProps): React.JSX.Element {
  return (
    <AppEmptyState
      action={buttonLabel && onAction ? { label: buttonLabel, onClick: onAction } : undefined}
      description={description}
      icon={icon}
      title={title}
      tone="sidebar"
    />
  );
}
