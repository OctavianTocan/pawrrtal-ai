'use client';

import { createContext, use, type ReactNode } from 'react';
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownSubmenu,
  DropdownSubmenuTrigger,
  DropdownSubmenuContent,
} from '@octavian-tocan/react-dropdown';

/**
 * Polymorphic menu primitives shared by `DropdownPanelMenu` and
 * `DropdownContextMenu`.
 *
 * Both menus host the same `DropdownRoot` context, so the same vendored
 * `DropdownMenuItem` / `DropdownSubmenu` JSX primitives render identically
 * inside either kind of menu. The `MenuComponentsContext` therefore exposes a
 * single set of components — there's no longer a need to swap between Radix
 * `Dropdown*` and Radix `Context*` flavors as the previous implementation did.
 *
 * The provider components are kept (`DropdownMenuProvider` and
 * `ContextMenuProvider`) so existing consumer code that wraps menu trees in
 * one of them keeps working unchanged.
 */
type MenuComponents = {
  MenuItem: typeof DropdownMenuItem;
  MenuSeparator: typeof DropdownMenuSeparator;
  MenuSub: typeof DropdownSubmenu;
  MenuSubTrigger: typeof DropdownSubmenuTrigger;
  MenuSubContent: typeof DropdownSubmenuContent;
};

const MenuComponentsContext = createContext<MenuComponents | null>(null);

/**
 * Stable shared mapping. Both providers point at the same vendored primitives
 * because `DropdownPanelMenu` and `DropdownContextMenu` use identical JSX item
 * APIs — there's no flavor distinction to bridge.
 */
const VENDORED_MENU_COMPONENTS: MenuComponents = {
  MenuItem: DropdownMenuItem,
  MenuSeparator: DropdownMenuSeparator,
  MenuSub: DropdownSubmenu,
  MenuSubTrigger: DropdownSubmenuTrigger,
  MenuSubContent: DropdownSubmenuContent,
};

/**
 * Returns the polymorphic menu primitives (MenuItem, MenuSeparator, etc.)
 * provided by the nearest `DropdownMenuProvider` or `ContextMenuProvider`.
 *
 * This lets shared menu content render identically inside both a dropdown
 * and a context menu without duplicating the item tree.
 *
 * @throws If called outside a `MenuProvider`.
 */
export function useMenuComponents(): MenuComponents {
  const ctx = use(MenuComponentsContext);
  if (!ctx) {
    throw new Error('useMenuComponents must be used within a MenuProvider');
  }
  return ctx;
}

/** Provides dropdown-flavoured menu components to child menu content. */
export function DropdownMenuProvider({ children }: { children: ReactNode }): React.JSX.Element {
  return <MenuComponentsContext.Provider value={VENDORED_MENU_COMPONENTS}>{children}</MenuComponentsContext.Provider>;
}

/** Provides context-menu-flavoured menu components to child menu content. */
export function ContextMenuProvider({ children }: { children: ReactNode }): React.JSX.Element {
  return <MenuComponentsContext.Provider value={VENDORED_MENU_COMPONENTS}>{children}</MenuComponentsContext.Provider>;
}
