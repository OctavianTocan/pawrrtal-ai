/**
 * Marks resumable checkpoints inside a long-running conversation.
 *
 * @fileoverview AI Elements — `checkpoint`.
 */

'use client';

import type { HTMLAttributes } from 'react';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

export { CheckpointIcon, type CheckpointIconProps } from './checkpoint-icon';
export { CheckpointTrigger, type CheckpointTriggerProps } from './checkpoint-trigger';

export type CheckpointProps = HTMLAttributes<HTMLDivElement>;

export const Checkpoint = ({ className, children, ...props }: CheckpointProps) => (
  <div className={cn('flex items-center gap-0.5 text-muted-foreground overflow-hidden', className)} {...props}>
    {children}
    <Separator />
  </div>
);
