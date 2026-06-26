/**
 * Expandable "thinking" panel for extended model rationale.
 *
 * @fileoverview AI Elements — `reasoning`.
 */

'use client';

import { useControllableState } from '@radix-ui/react-use-controllable-state';
import type { ComponentProps } from 'react';
import { memo, useEffect, useMemo, useRef } from 'react';
import { Collapsible } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { ReasoningContext } from './reasoning-context';

export { ReasoningContent, type ReasoningContentProps } from './reasoning-content';
export { useReasoning } from './reasoning-context';
export { ReasoningTrigger, type ReasoningTriggerProps } from './reasoning-trigger';

export type ReasoningProps = ComponentProps<typeof Collapsible> & {
  isStreaming?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  duration?: number;
};

const AUTO_CLOSE_DELAY = 1000;
const MS_IN_S = 1000;

export const Reasoning = memo(
  ({
    className,
    isStreaming = false,
    open,
    defaultOpen = true,
    onOpenChange,
    duration: durationProp,
    children,
    ...props
  }: ReasoningProps) => {
    const [isOpen, setIsOpen] = useControllableState({
      prop: open,
      defaultProp: defaultOpen,
      onChange: onOpenChange,
    });
    const hasAutoClosedRef = useRef(false);
    const durationRef = useRef<number | undefined>(undefined);
    const startTimeRef = useRef<number | null>(null);
    if (isStreaming && startTimeRef.current === null) {
      startTimeRef.current = Date.now();
    }
    if (!isStreaming && startTimeRef.current !== null) {
      durationRef.current = Math.ceil((Date.now() - startTimeRef.current) / MS_IN_S);
      startTimeRef.current = null;
    }
    const duration = durationProp ?? durationRef.current;

    // Auto-open when streaming starts, auto-close when streaming ends (once only)
    useEffect(() => {
      if (defaultOpen && !isStreaming && isOpen && !hasAutoClosedRef.current) {
        // Add a small delay before closing to allow user to see the content
        const timer = setTimeout(() => {
          setIsOpen(false);
          hasAutoClosedRef.current = true;
        }, AUTO_CLOSE_DELAY);

        return () => clearTimeout(timer);
      }
    }, [isStreaming, isOpen, defaultOpen, setIsOpen]);

    const handleOpenChange = (newOpen: boolean) => {
      setIsOpen(newOpen);
    };

    const contextValue = useMemo(
      () => ({ isStreaming, isOpen, setIsOpen, duration }),
      [isStreaming, isOpen, setIsOpen, duration]
    );

    return (
      <ReasoningContext.Provider value={contextValue}>
        <Collapsible
          className={cn('not-prose mb-4', className)}
          onOpenChange={handleOpenChange}
          open={isOpen}
          {...props}
        >
          {children}
        </Collapsible>
      </ReasoningContext.Provider>
    );
  }
);

Reasoning.displayName = 'Reasoning';
