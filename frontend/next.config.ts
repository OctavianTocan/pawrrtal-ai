/**
 * Next.js configuration for the Pawrrtal frontend.
 *
 * @fileoverview Sets Turborepo monorepo root for Turbopack, enables
 * `authInterrupts` for `unauthorized()`, and rewrites barrel-style imports
 * from icon / UI libraries into direct imports at build time so the dev
 * server doesn't pay the 200–800 ms cold-start cost of resolving thousands
 * of unused re-exports. The config is wrapped with `createMDX()` from
 * `fumadocs-mdx/next` to enable build-time MDX processing for the
 * documentation site.
 */

import path from 'node:path';
import { createMDX } from 'fumadocs-mdx/next';
import type { NextConfig } from 'next';
import { backendRewriteRules } from './next.backend-rewrites';

const configuredAllowedDevOrigins = process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);

const publicHostname = process.env.PAWRRTAL_PUBLIC_HOSTNAME ?? process.env.CLOUDFLARED_HOSTNAME ?? undefined;

function normalizeDevOrigin(hostname: string | undefined): string | undefined {
  if (!hostname) return undefined;
  const trimmed = hostname.trim();
  if (!trimmed) return undefined;
  return trimmed.startsWith('http://') || trimmed.startsWith('https://')
    ? trimmed.replace(/\/$/, '')
    : `https://${trimmed}`;
}

const cloudflaredDevOrigin = normalizeDevOrigin(publicHostname);

const allowedDevOrigins = [
  ...(configuredAllowedDevOrigins ?? []),
  ...(cloudflaredDevOrigin ? [cloudflaredDevOrigin] : []),
];

const nextConfig: NextConfig = {
  allowedDevOrigins,
  async rewrites() {
    return backendRewriteRules();
  },
  turbopack: {
    root: path.resolve(__dirname, '../'),
  },
  // `standalone` emits a self-contained server bundle at
  // `.next/standalone/` plus a `node_modules/` slice with only the
  // production deps the runtime touches. The Electron desktop shell
  // spawns this server directly (see `electron/src/server.ts`) so the
  // app works offline of any external Next.js host. Vercel + every
  // other Node host ignores the standalone dir, so the web build path
  // is unaffected.
  output: 'standalone',
  experimental: {
    // https://nextjs.org/docs/app/api-reference/functions/unauthorized
    authInterrupts: true,
    // Transforms `import { X } from 'lib'` into the underlying source
    // path so tree-shaking can drop everything else. Per the Vercel
    // `bundle-barrel-imports` rule: 15–70% faster dev boot, ~28% faster
    // builds, ~40% faster cold starts on icon-heavy code. Keep this list
    // in sync with the barrel libraries the app actually consumes.
    optimizePackageImports: [
      'lucide-react',
      '@tabler/icons-react',
      '@hugeicons/react',
      '@radix-ui/react-icons',
      'date-fns',
    ],
  },
};

const withMDX = createMDX();

export default withMDX(nextConfig);
