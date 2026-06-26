'use client';

import { Construction } from 'lucide-react';
import type * as React from 'react';
import { SettingsPage } from '../primitives';

/**
 * Placeholder body rendered for settings sections that aren't yet built
 * (Configuration, MCP servers, Git, Environments, Worktrees, Browser
 * use, ...). Wraps the standard `SettingsPage` so the title row matches
 * every other section's vertical rhythm — only the body differs.
 */
export function PlaceholderSection({ title }: { title: string }): React.JSX.Element {
  return (
    <SettingsPage description="This section is on the roadmap but not yet implemented." title={title}>
      <div className="flex items-center gap-3 rounded-[10px] border border-dashed border-foreground/15 bg-foreground/[0.02] px-5 py-8 text-sm text-muted-foreground">
        <Construction aria-hidden="true" className="size-4" />
        <span>This section is coming soon.</span>
      </div>
    </SettingsPage>
  );
}
