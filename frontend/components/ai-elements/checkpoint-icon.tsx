/**
 * Bookmark icon for checkpoint markers.
 *
 * @fileoverview AI Elements — `checkpoint` icon subcomponent.
 */

import { BookmarkIcon, type LucideProps } from 'lucide-react';
import { cn } from '@/lib/utils';

export type CheckpointIconProps = LucideProps;

export const CheckpointIcon = ({ className, children, ...props }: CheckpointIconProps) =>
	children ?? <BookmarkIcon className={cn('size-4 shrink-0', className)} {...props} />;
