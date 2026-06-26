'use client';

import { useEffect, useState } from 'react';
import { getDesktopPlatformSync } from '@/lib/desktop';

/**
 * Track whether the renderer is running inside the macOS Electron shell
 * so layouts can apply desktop-specific chrome (e.g. `-webkit-app-region`
 * drag on the in-app header). Starts `false` so SSR and the first client
 * render agree (avoids hydration mismatch); flips on mount once `window.pawrrtal`
 * is readable.
 *
 * @returns `true` only when the Electron preload bridge reports
 * `process.platform === 'darwin'`.
 */
export function useIsMacDesktop(): boolean {
  const [isMacDesktop, setIsMacDesktop] = useState(false);
  useEffect(() => {
    setIsMacDesktop(getDesktopPlatformSync() === 'darwin');
  }, []);
  return isMacDesktop;
}
