/**
 * Thin sidebar shell that only mounts the conversations list.
 *
 * @fileoverview Prefer {@link AppShell} for the full app chrome; this is used by the dashboard demo page.
 */

'use client';

import type * as React from 'react';
import { Sidebar, SidebarContent } from '@/components/ui/sidebar';
import { NavChats } from '@/features/nav-chats/NavChats';

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar variant="inset" {...props}>
      <SidebarContent>
        <NavChats />
      </SidebarContent>
    </Sidebar>
  );
}
