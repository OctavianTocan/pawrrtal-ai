'use client';

/**
 * Centered empty-state card.
 *
 * Reused across the Skills / Shared with me / Shared by me sub-views and
 * inside the Brain access tabs. Rendered as a single elevated card
 * with a soft icon, title, body, and optional CTA button.
 */

import type { ComponentType, ReactNode, SVGProps } from 'react';
import { AppEmptyState } from '@/components/ui/app-empty-state';

interface EmptyStateProps {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

/**
 * Pure presentation. The container chooses copy and the optional CTA;
 * this component never reads any state of its own.
 */
export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps): ReactNode {
  return (
    <AppEmptyState
      action={action}
      description={description}
      icon={<Icon aria-hidden="true" className="size-5" />}
      title={title}
      tone="card"
    />
  );
}
