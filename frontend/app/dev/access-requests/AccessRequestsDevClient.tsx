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
import { type AccessRequest, AccessRequestBanner } from '@/features/access-request-banner';

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
        <h1 className="text-2xl font-semibold">Access Request Banner - Dev</h1>

        {/* Full width variants */}
        <section className="flex flex-col gap-6">
          <h2 className="text-lg font-semibold text-muted-foreground">Full width (max-w-2xl)</h2>
          <div className="flex max-w-2xl flex-col gap-4">
            {/* 5 users: tests stagger, avatar count bubble, summary text */}
            {!dismissed.full && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">5 users:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, full: true }))}
                />
              </div>
            )}

            {/* 2 users: tests "X and Y" text variant, no count bubble */}
            {!dismissed.two && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">2 users:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS.slice(0, 2)}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, two: true }))}
                />
              </div>
            )}

            {/* 1 user: tests "X is requesting" variant, single avatar */}
            {!dismissed.single && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">1 user:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS.slice(0, 1)}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() => setDismissed((d) => ({ ...d, single: true }))}
                />
              </div>
            )}
          </div>
        </section>

        {/* Narrow width variants: tests text truncation and compact layout */}
        <section className="flex flex-col gap-6">
          <h2 className="text-lg font-semibold text-muted-foreground">Narrow (w-80 / 320px)</h2>
          <div className="flex w-80 flex-col gap-4">
            {!dismissed.narrow5 && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">5 users, narrow:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      narrow5: true,
                    }))
                  }
                />
              </div>
            )}

            {!dismissed.narrow1 && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">1 user, narrow:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS.slice(0, 1)}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      narrow1: true,
                    }))
                  }
                />
              </div>
            )}
          </div>
        </section>

        {/* Medium width variant */}
        <section className="flex flex-col gap-6">
          <h2 className="text-lg font-semibold text-muted-foreground">Medium (w-[26rem] / 416px)</h2>
          <div className="flex w-[26rem] flex-col gap-4">
            {!dismissed.medium && (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">5 users, medium:</p>
                <AccessRequestBanner
                  requests={MOCK_REQUESTS}
                  onApprove={(id) => devLog('Approved:', id)}
                  onReject={(id) => devLog('Rejected:', id)}
                  onDismiss={() =>
                    setDismissed((d) => ({
                      ...d,
                      medium: true,
                    }))
                  }
                />
              </div>
            )}
          </div>
        </section>

        {/* Reset button appears once any banner has been dismissed */}
        {Object.keys(dismissed).length > 0 && (
          <button
            type="button"
            onClick={() => setDismissed({})}
            className="cursor-pointer text-sm text-muted-foreground underline hover:text-foreground"
          >
            Reset all banners
          </button>
        )}
      </div>
    </div>
  );
}
