/**
 * Notebook layout for the product section. Fumadocs' Notebook layout is
 * a compact variant of `DocsLayout` — tighter chrome, less navigation
 * weight — which fits the short, user-facing product pages better than
 * the full DocsLayout used on the handbook.
 *
 * The handbook intentionally keeps `DocsLayout` because long-form ADRs
 * benefit from the heavier sidebar tree and breadcrumb chrome.
 */

import { DocsLayout } from 'fumadocs-ui/layouts/notebook';
import type { ReactNode } from 'react';
import { DocsSidebarBanner, DocsSidebarFooter } from '@/components/docs/sidebar-chrome';
import { baseOptions } from '@/lib/layout.shared';
import { productSource } from '@/lib/source';

/**
 * Renders the product chrome (compact Notebook variant) around child routes.
 *
 * @param props.children - the active product page
 * @returns the wrapped layout
 */
export default function ProductLayout({ children }: { children: ReactNode }): React.ReactElement {
  return (
    <DocsLayout
      containerProps={{ className: 'pawrrtal-docs' }}
      sidebar={{
        defaultOpenLevel: 1,
        banner: <DocsSidebarBanner />,
        footer: <DocsSidebarFooter />,
      }}
      tabs={[
        { title: 'Handbook', url: '/docs/handbook' },
        { title: 'Product', url: '/docs/product' },
      ]}
      tree={productSource.pageTree}
      {...baseOptions()}
    >
      {children}
    </DocsLayout>
  );
}
