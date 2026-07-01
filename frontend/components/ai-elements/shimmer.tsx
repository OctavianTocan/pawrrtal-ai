/**
 * Skeleton shimmer for placeholder content.
 *
 * @fileoverview AI Elements — `shimmer`.
 */

'use client';

import { domAnimation, LazyMotion } from 'motion/react';
import * as m from 'motion/react-m';
import type { CSSProperties, ElementType } from 'react';
import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';

// `motion.create()` accepts both intrinsic-tag strings (`'p'`, `'span'`)
// and React component types, but the public typing uses
// `keyof IntrinsicElements`. We cast at the seam (in `resolveMotionComponent`
// below) and treat the result as a permissive component because the
// shape we render is `<MotionComponent>` with the standard `className` /
// `style` / framer props — Framer's typings can't represent that union.
// biome-ignore lint/suspicious/noExplicitAny: Framer Motion 11 typings can't model the ElementType-or-component union
type MotionWrappedComponent = React.ComponentType<any>;

export type TextShimmerProps = {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
};

// Hoist the motion-wrapped element factory cache to module scope.
//
// Why: calling `motion.create(Component)` inside the render body builds
// a brand-new motion-wrapped component on every render.  React sees a
// different component identity each time, unmounts the previous Framer
// Motion tree, and remounts a fresh one — which means animation state
// resets and Framer's heavy mount work runs on every parent re-render.
//
// `<Shimmer>` is rendered while a chat reply is streaming.  The chat
// container re-renders on every SSE delta (one per streamed byte/token),
// so the previous version triggered a Framer remount cascade per byte
// and pegged the renderer at multi-core CPU.  Caching by component
// identity collapses that to one motion-wrap per element type.
// String tags (`'p'`, `'span'`) keyed in a regular Map; React component
// types (functions/classes) keyed in a WeakMap so re-rendered ad-hoc
// components don't pin themselves alive in the cache forever.
const motionTagCache = new Map<string, MotionWrappedComponent>();
const motionComponentCache = new WeakMap<React.ComponentType<unknown>, MotionWrappedComponent>();

function resolveMotionComponent(Component: ElementType): MotionWrappedComponent {
  if (typeof Component === 'string') {
    const cached = motionTagCache.get(Component);
    if (cached) return cached;
    // biome-ignore lint/suspicious/noExplicitAny: see top-of-file
    const created = m.create(Component as any) as MotionWrappedComponent;
    motionTagCache.set(Component, created);
    return created;
  }
  const componentKey = Component as React.ComponentType<unknown>;
  const cached = motionComponentCache.get(componentKey);
  if (cached) return cached;
  // biome-ignore lint/suspicious/noExplicitAny: see top-of-file
  const created = m.create(Component as any) as MotionWrappedComponent;
  motionComponentCache.set(componentKey, created);
  return created;
}

const ShimmerComponent = ({ children, as: Component = 'p', className, duration = 2, spread = 2 }: TextShimmerProps) => {
  const MotionComponent = useMemo(() => resolveMotionComponent(Component), [Component]);

  const dynamicSpread = useMemo(() => (children?.length ?? 0) * spread, [children, spread]);

  return (
    <LazyMotion features={domAnimation}>
      <MotionComponent
        animate={{ backgroundPosition: '0% center' }}
        className={cn(
          'relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent',
          '[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-background),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]',
          className
        )}
        initial={{ backgroundPosition: '100% center' }}
        style={
          {
            '--spread': `${dynamicSpread}px`,
            backgroundImage: 'var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))',
          } as CSSProperties
        }
        transition={{
          repeat: Number.POSITIVE_INFINITY,
          duration,
          ease: 'linear',
        }}
      >
        {children}
      </MotionComponent>
    </LazyMotion>
  );
};

export const Shimmer = memo(ShimmerComponent);
