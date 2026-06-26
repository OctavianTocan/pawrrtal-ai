/**
 * Tool call input parameters display.
 *
 * @fileoverview AI Elements — `tool` input subcomponent.
 */

import type { ToolUIPart } from 'ai';
import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { CodeBlock } from './code-block';

export type ToolInputProps = ComponentProps<'div'> & {
  input: ToolUIPart['input'];
};

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => (
  <div className={cn('space-y-2 overflow-hidden p-4', className)} {...props}>
    <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">Parameters</h4>
    <div className="rounded-md bg-muted/50">
      <CodeBlock code={JSON.stringify(input, null, 2)} language="json" />
    </div>
  </div>
);
