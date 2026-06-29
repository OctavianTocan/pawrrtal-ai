/**
 * Dev-only test page for the AccessRequestBanner component.
 *
 * Renders multiple banner variants across different widths and user counts to
 * verify text logic branches, avatar overflow, and layout edge cases. Useful for
 * testing the banner's responsive design and text formatting without needing real
 * access request data.
 *
 * @fileoverview Test page for AccessRequestBanner component with multiple variants
 */

'use client';

import { useState } from 'react';
import type { AccessRequest } from '@/features/access-request-banner';
import { AccessRequestBanner } from '@/features/access-request-banner';

/** Dev-only logger — isolates console usage to satisfy lint in the test page. */
// biome-ignore lint/suspicious/noConsole: dev-only test page — actions are logged for visual verification
const devLog = (...args: unknown[]): void => console.log(...args);

/** Mock data for testing the banner with various name lengths and counts. */
const MOCK_REQUESTS: AccessRequest[] = [
  { id: '1', name: 'Octavian Tocan' },
  { id: '2', name: 'Jane Smith' },
  { id: '3', name: 'Alex Chen' },
  { id: '4', name: 'Maria Lopez' },
  { id: '5', name: 'Sam Wilson' },
];

/**
 * Dev-only route for testing the AccessRequestBanner component.
 *
 * Renders multiple variants across different widths and user counts
 * so all text logic branches, avatar overflow, and layout edge cases
 * can be verified visually. Logs actions to console.
 */
export function AccessRequestsDevClient(): React.JSX.Element {
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});

  return (
    /* Fixed full-screen scroll container so scrollbar-gutter applies
		   to this element (not the body). Hides scrollbar visually while
		   reserving its gutter space to prevent content shifts. */
    <div className="fixed inset-0 overflow-y-auto [scrollbar-gutter:stable] [&::-webkit-scrollbar]:hidden">
      <div className="mx-auto flex max-w-3xl flex-col gap-10 p-8">
        <h1 className="font-semibold text-2xl">Access Request Banner - Dev</h1>

        {/* Full width variants */}
        <section className="flex flex-col gap-6">
          <h2 className="font-semibold text-lg text-muted-foreground">Full width (max-w-2xl)</h2>
          <div className="flex max-w-2xl flex-col gap-4">
            {/* 5 users: tests stagger, avatar count bubble, summary text */}
            {!dismissed.full && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">5 users:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, full: true }))}
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}

            {/* 2 users: tests "X and Y" text variant, no count bubble */}
            {!dismissed.two && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">2 users:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, two: true }))}
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS.slice(0, 2)}
                />
              </div>
            )}

            {/* 1 user: tests "X is requesting" variant, single avatar */}
            {!dismissed.single && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">1 user:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, single: true }))}
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS.slice(0, 1)}
                />
              </div>
            )}
          </div>
        </section>

        {/* Narrow width variants: tests text truncation and compact layout */}
        <section className="flex flex-col gap-6">
          <h2 className="font-semibold text-lg text-muted-foreground">Narrow (w-80 / 320px)</h2>
          <div className="flex w-80 flex-col gap-4">
            {!dismissed.narrow5 && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">5 users, narrow:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      narrow5: true,
                    }))
                  }
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}

            {!dismissed.narrow1 && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">1 user, narrow:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      narrow1: true,
                    }))
                  }
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS.slice(0, 1)}
                />
              </div>
            )}
          </div>
        </section>

        {/* Medium width variant */}
        <section className="flex flex-col gap-6">
          <h2 className="font-semibold text-lg text-muted-foreground">Medium (w-[26rem] / 416px)</h2>
          <div className="flex w-[26rem] flex-col gap-4">
            {!dismissed.medium && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">5 users, medium:</p>
                <AccessRequestBanner
                  onApprove={(id) => devLog('Approved:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      medium: true,
                    }))
                  }
                  onReject={(id) => devLog('Rejected:', id)}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}
          </div>
        </section>

        {/* Reset button appears once any banner has been dismissed */}
        {Object.keys(dismissed).length > 0 && (
          <button
            className="cursor-pointer text-muted-foreground text-sm underline hover:text-foreground"
            onClick={() => setDismissed({})}
            type="button"
          >
            Reset all banners
          </button>
        )}
      </div>
    </div>
  );
}
