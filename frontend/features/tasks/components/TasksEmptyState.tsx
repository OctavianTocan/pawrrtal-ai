'use client';

/**
 * Centered editorial empty state for any Tasks sub-view.
 *
 * Uses Newsreader display type for the headline so an empty Today doesn't
 * read as a broken page — it reads as a moment of quiet. The optional CTA
 * stays low-key (foreground fill, no accent) so the message stays primary.
 */

import type { ComponentType, ReactNode, SVGProps } from 'react';
import { AppEmptyState } from '@/components/ui/app-empty-state';

export interface TasksEmptyStateProps {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

/**
 * Pure presentation. The container picks copy + CTA; this component never
 * reads any state of its own.
 */
export function TasksEmptyState({ icon: Icon, title, description, action }: TasksEmptyStateProps): ReactNode {
  return (
    <AppEmptyState
      action={action}
      description={description}
      icon={<Icon aria-hidden="true" className="size-5" strokeWidth={1.75} />}
      title={title}
      tone="page"
    />
  );
}
