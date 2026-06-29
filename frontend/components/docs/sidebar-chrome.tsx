/**
 * Sidebar banner + footer slots for Fumadocs `DocsLayout`.
 *
 * The banner sits above the page tree (below the section tabs) and
 * gives the docs sidebar a small product identity without veering
 * into full design-system integration. The footer sits at the bottom
 * with attribution + a link to GitHub.
 */

import { ExternalLinkIcon } from 'lucide-react';

const GITHUB_URL = 'https://github.com/OctavianTocan/pawrrtal';

/**
 * Small wordmark + tagline rendered at the top of the docs sidebar.
 *
 * @returns the banner element
 */
export function DocsSidebarBanner(): React.ReactElement {
  return (
    <div className="rounded-md border border-fd-border bg-fd-card/40 px-3 py-2.5">
      <div className="font-medium text-fd-foreground text-sm">Pawrrtal</div>
      <div className="mt-0.5 text-[11px] text-fd-muted-foreground leading-tight">Model-agnostic chat. Public docs.</div>
    </div>
  );
}

/**
 * Attribution + GitHub link rendered at the bottom of the docs sidebar.
 *
 * @returns the footer element
 */
export function DocsSidebarFooter(): React.ReactElement {
  return (
    <div className="flex flex-col gap-1 text-[11px] text-fd-muted-foreground">
      <a
        className="inline-flex cursor-pointer items-center gap-1 hover:text-fd-foreground"
        href={GITHUB_URL}
        rel="noreferrer"
        target="_blank"
      >
        Source on GitHub
        <ExternalLinkIcon aria-hidden="true" className="size-3" />
      </a>
      <span>Built by Octavian Tocan</span>
    </div>
  );
}
