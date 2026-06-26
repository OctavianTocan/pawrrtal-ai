/**
 * Manual vitest mock for @octavian-tocan/react-dropdown.
 *
 * The package is vendored at lib/react-dropdown/ which may not be present in
 * CI or ephemeral checkouts.  This stub exports the minimum surface needed to
 * render components that use the dropdown in tests.
 */
import type * as React from 'react';

export function DropdownPanelMenu({
  children,
}: {
  children: React.ReactNode;
  [key: string]: unknown;
}): React.JSX.Element {
  return <div data-testid="dropdown-panel-menu">{children}</div>;
}

export function DropdownMenuItem({
  children,
}: {
  children: React.ReactNode;
  [key: string]: unknown;
}): React.JSX.Element {
  // biome-ignore lint/a11y/useFocusableInteractive: test mock — no real interaction
  return <div role="menuitem">{children}</div>;
}

export function DropdownMenuSeparator(): React.JSX.Element {
  return <hr />;
}
