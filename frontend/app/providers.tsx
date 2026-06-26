'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import type * as React from 'react';
import { Toaster } from 'sonner';
import { getQueryClient } from './get-query-client';

/**
 * App-root provider tree.
 *
 * Mounts TanStack Query and the global Sonner toaster.
 *
 * The `<AppearanceProvider>` that used to sit here was removed as part of
 * the 2026-05-06 theming-system rip
 * (see `frontend/content/docs/handbook/decisions/2026-05-06-rip-theming-system.md`). The cascade
 * defaults defined in `frontend/app/globals.css` now drive the entire
 * theme; per-user runtime CSS variable injection is gone.
 *
 * @param children - The children to wrap in the query client provider.
 * @returns The query client provider wrapped around the children.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      {/* <QueryDevtools /> */}
      {children}
      <Toaster closeButton duration={3500} position="top-center" richColors={false} theme="system" visibleToasts={3} />
    </QueryClientProvider>
  );
}
