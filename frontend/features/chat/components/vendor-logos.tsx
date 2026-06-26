'use client';

import Image from 'next/image';
import type * as React from 'react';
import type { ComponentType, SVGProps } from 'react';
import { cn } from '@/lib/utils';

/**
 * Pixel size of the vendor logo rendered in the model menu rows.
 *
 * Matches the size the popover renders (`size-3` = 12px). Kept as a
 * named constant so the `<Image>` `width` / `height` attributes stay in
 * lockstep with the visual size.
 */
const VENDOR_LOGO_SIZE = 12;

/**
 * Builds the `models.dev` CDN URL for a given vendor slug.
 *
 * `models.dev` exposes a stable per-vendor SVG (e.g.
 * `https://models.dev/logos/anthropic.svg`) — the same source the
 * picker has used since its first iteration.
 *
 * @param vendor - Vendor slug exactly as it appears in the catalog
 *   entry's `vendor` field (`anthropic`, `google`, `openai`, …).
 * @returns Absolute URL to the vendor's SVG logo.
 */
function modelsDevLogoUrl(vendor: string): string {
  return `https://models.dev/logos/${vendor}.svg`;
}

/**
 * Factory that creates a thin React component wrapping `next/image`
 * around the `models.dev` SVG for a given vendor.
 *
 * The component accepts the standard `SVGProps<SVGSVGElement>` so it
 * stays interchangeable with any real inline SVG glyph we might add
 * later under `components/brand-icons/`. `className` is forwarded; all
 * other SVG-only props are ignored because the underlying element is
 * an `<img>`, not an `<svg>`.
 *
 * `unoptimized` is required because the host isn't on the project's
 * `next.config` `remotePatterns` allowlist — that matches the original
 * popover behaviour.
 *
 * @param vendor - Vendor slug to render.
 * @returns A React component that renders the vendor's logo.
 */
function createModelsDevLogo(vendor: string): ComponentType<SVGProps<SVGSVGElement>> {
  function ModelsDevLogo({ className }: SVGProps<SVGSVGElement>): React.ReactNode {
    return (
      <Image
        alt={`${vendor} logo`}
        className={cn('size-3 rounded-full dark:invert', className)}
        height={VENDOR_LOGO_SIZE}
        src={modelsDevLogoUrl(vendor)}
        unoptimized
        width={VENDOR_LOGO_SIZE}
      />
    );
  }
  ModelsDevLogo.displayName = `VendorLogo(${vendor})`;
  return ModelsDevLogo;
}

/**
 * Logo used when a catalog vendor doesn't have a brand-specific entry in
 * {@link VENDOR_LOGOS}. Anthropic was picked as the visually neutral
 * fallback because every brand-correct glyph we ship is at least as
 * recognisable; replace this once a generic placeholder lands under
 * `components/brand-icons/`.
 */
const FALLBACK_VENDOR_LOGO: ComponentType<SVGProps<SVGSVGElement>> = createModelsDevLogo('anthropic');

/**
 * Vendor → logo component map. Pure UI concern; not a source of truth
 * for the model catalog itself.
 *
 * Keys mirror the `vendor` field on `ChatModelOption` from
 * `useChatModels()` (which is the canonical-ID `vendor` segment served
 * by `GET /api/v1/models`). New vendors fall back to
 * {@link FALLBACK_VENDOR_LOGO} via {@link vendorLogo}.
 */
const VENDOR_LOGOS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  anthropic: FALLBACK_VENDOR_LOGO,
  google: createModelsDevLogo('google'),
  openai: createModelsDevLogo('openai'),
};

/**
 * Returns the logo component for a vendor, falling back to a sensible
 * default when no entry exists.
 *
 * The fallback keeps the picker UI robust against the catalog adding a
 * new vendor before the frontend ships a matching glyph — the row will
 * still render with a vendor logo, just not the brand-correct one.
 *
 * @param vendor - Vendor slug from the catalog (e.g. `anthropic`).
 * @returns Logo component for the vendor.
 */
export function vendorLogo(vendor: string): ComponentType<SVGProps<SVGSVGElement>> {
  return VENDOR_LOGOS[vendor] ?? FALLBACK_VENDOR_LOGO;
}
