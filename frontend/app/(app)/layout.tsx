/**
 * Authenticated app segment layout: sidebar shell and main content region.
 */

import { AppShell } from '@/features/app-shell/AppShell';

/**
 * Wraps `(app)/*` routes with the persistent {@link AppShell} chrome.
 */
export default function AppShellWrapper({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <AppShell>{children}</AppShell>;
}
