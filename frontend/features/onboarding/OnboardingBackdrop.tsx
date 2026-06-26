'use client';

import type * as React from 'react';
import { useEffect, useRef } from 'react';

const CELL_SIZE = 6;
const TWO_PI = Math.PI * 2;

interface BlobAnchor {
  x: number;
  y: number;
  radius: number;
}

interface VortexPalette {
  background: string;
  foregroundRgb: string;
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));

  return t * t * (3 - 2 * t);
}

function getBlobAnchors(width: number, height: number, time: number): BlobAnchor[] {
  return [
    {
      x: width * (0.28 + Math.cos(time * 0.71) * 0.08),
      y: height * (0.33 + Math.sin(time * 0.92) * 0.1),
      radius: Math.min(width, height) * (0.23 + Math.sin(time * 1.3) * 0.035),
    },
    {
      x: width * (0.72 + Math.cos(time * 0.48 + 1.7) * 0.07),
      y: height * (0.45 + Math.sin(time * 0.82 + 0.5) * 0.11),
      radius: Math.min(width, height) * (0.27 + Math.cos(time * 1.1) * 0.04),
    },
    {
      x: width * (0.52 + Math.cos(time * 0.64 + 3.1) * 0.1),
      y: height * (0.76 + Math.sin(time * 0.56 + 2.2) * 0.08),
      radius: Math.min(width, height) * (0.2 + Math.sin(time * 0.9 + 1.4) * 0.03),
    },
  ];
}

function getBlobInfluence(x: number, y: number, anchors: BlobAnchor[]): number {
  let influence = 0;

  for (const anchor of anchors) {
    const distance = Math.hypot(x - anchor.x, y - anchor.y) / anchor.radius;
    influence += 1 - smoothstep(0.18, 1, distance);
  }

  return Math.min(1, influence);
}

function drawVortex(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  palette: VortexPalette
): void {
  const centerX = width * 0.5;
  const centerY = height * 0.5;
  const maxRadius = Math.hypot(width, height) * 0.58;
  const blobAnchors = getBlobAnchors(width, height, time);

  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);

  for (let y = 0; y < height; y += CELL_SIZE) {
    for (let x = 0; x < width; x += CELL_SIZE) {
      const dx = x - centerX;
      const dy = y - centerY;
      const radius = Math.hypot(dx, dy);
      const normalizedRadius = radius / maxRadius;

      if (normalizedRadius > 1.08) {
        continue;
      }

      const angle = Math.atan2(dy, dx);
      const blobInfluence = getBlobInfluence(x, y, blobAnchors);
      const turbulence = Math.sin(x * 0.009 + time * 0.86) * 0.34 + Math.cos(y * 0.011 - time * 0.74) * 0.28;
      const radialWarp = Math.sin(angle * 3.2 + time * 0.38) * blobInfluence * 1.35;
      const spiral = angle * 5.1 + normalizedRadius * 20.5 - time + radialWarp;
      const counterSpiral = angle * 2.4 - normalizedRadius * 10.8 + time * 0.42 + turbulence * blobInfluence;
      const softBlob = smoothstep(0.18, 0.82, blobInfluence) * 0.34;
      const band = Math.sin(spiral) * 0.66 + Math.sin(counterSpiral) * 0.24 + softBlob;
      const falloff = Math.max(0, 1 - normalizedRadius * 0.86);
      const alpha = Math.max(0, band) * (0.22 + blobInfluence * 0.08) + falloff * 0.075;

      if (alpha < 0.055) {
        continue;
      }

      const size = alpha > 0.22 ? 2 : 1;
      context.fillStyle = `rgba(${palette.foregroundRgb}, ${Math.min(0.34, alpha)})`;
      context.fillRect(x, y, size, size);
    }
  }

  context.fillStyle = `rgba(${palette.foregroundRgb}, 0.035)`;
  context.beginPath();
  context.arc(centerX, centerY, maxRadius * 0.11, 0, TWO_PI);
  context.fill();
}

function getVortexPalette(canvas: HTMLCanvasElement): VortexPalette {
  const styles = window.getComputedStyle(canvas);
  const background = styles.getPropertyValue('--background').trim() || 'Canvas';
  const foregroundRgb = styles.getPropertyValue('--foreground-rgb').trim() || '29, 29, 36';

  return { background, foregroundRgb };
}

/**
 * Full-page atmospheric backdrop for onboarding.
 */
export function OnboardingBackdrop(): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect((): (() => void) => {
    const canvas = canvasRef.current;

    if (!canvas) {
      return (): void => undefined;
    }

    const context = canvas.getContext('2d');

    if (!context) {
      return (): void => undefined;
    }

    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let animationFrame = 0;
    let width = 0;
    let height = 0;
    let palette = getVortexPalette(canvas);

    const resize = (): void => {
      width = Math.max(1, Math.floor(canvas.clientWidth));
      height = Math.max(1, Math.floor(canvas.clientHeight));
      canvas.width = width;
      canvas.height = height;
    };

    const render = (now: number): void => {
      const loopProgress = (now % 52000) / 52000;
      palette = getVortexPalette(canvas);
      drawVortex(context, width, height, loopProgress * TWO_PI, palette);

      if (!reducedMotionQuery.matches) {
        animationFrame = window.requestAnimationFrame(render);
      }
    };

    resize();
    render(0);

    window.addEventListener('resize', resize);

    return (): void => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-background" aria-hidden="true">
      <canvas ref={canvasRef} className="absolute inset-0 size-full" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,transparent_0%,var(--background)_100%)] opacity-20" />
    </div>
  );
}
