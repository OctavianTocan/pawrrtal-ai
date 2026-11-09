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

import { useCallback, useState } from 'react';
import type { AccessRequest } from '@/features/access-request-banner';
import { AccessRequestBanner } from '@/features/access-request-banner';

/** Logs dev-page banner actions for visual verification. */
// biome-ignore lint/suspicious/noConsole: dev-only test page — actions are logged for visual verification
const devLog = (action: string, id: string): void => console.log(action, id);

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
  const handleApprove = useCallback((id: string): void => devLog('Approved:', id), []);
  const handleReject = useCallback((id: string): void => devLog('Rejected:', id), []);
  const handleDismissFull = useCallback((): void => {
    setDismissed((current) => ({ ...current, full: true }));
  }, []);
  const handleDismissTwo = useCallback((): void => {
    setDismissed((current) => ({ ...current, two: true }));
  }, []);
  const handleDismissSingle = useCallback((): void => {
    setDismissed((current) => ({ ...current, single: true }));
  }, []);
  const handleDismissNarrow5 = useCallback((): void => {
    setDismissed((current) => ({ ...current, narrow5: true }));
  }, []);
  const handleDismissNarrow1 = useCallback((): void => {
    setDismissed((current) => ({ ...current, narrow1: true }));
  }, []);
  const handleDismissMedium = useCallback((): void => {
    setDismissed((current) => ({ ...current, medium: true }));
  }, []);
  const handleReset = useCallback((): void => {
    setDismissed({});
  }, []);
  const hasDismissedBanner = Object.keys(dismissed).length > 0;

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
                  onApprove={handleApprove}
                  onDismiss={handleDismissFull}
                  onReject={handleReject}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}

            {/* 2 users: tests "X and Y" text variant, no count bubble */}
            {!dismissed.two && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">2 users:</p>
                <AccessRequestBanner
                  onApprove={handleApprove}
                  onDismiss={handleDismissTwo}
                  onReject={handleReject}
                  requests={MOCK_REQUESTS.slice(0, 2)}
                />
              </div>
            )}

            {/* 1 user: tests "X is requesting" variant, single avatar */}
            {!dismissed.single && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">1 user:</p>
                <AccessRequestBanner
                  onApprove={handleApprove}
                  onDismiss={handleDismissSingle}
                  onReject={handleReject}
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
                  onApprove={handleApprove}
                  onDismiss={handleDismissNarrow5}
                  onReject={handleReject}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}

            {!dismissed.narrow1 && (
              <div>
                <p className="mb-2 text-muted-foreground text-xs">1 user, narrow:</p>
                <AccessRequestBanner
                  onApprove={handleApprove}
                  onDismiss={handleDismissNarrow1}
                  onReject={handleReject}
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
                  onApprove={handleApprove}
                  onDismiss={handleDismissMedium}
                  onReject={handleReject}
                  requests={MOCK_REQUESTS}
                />
              </div>
            )}
          </div>
        </section>

        {/* Reset button appears once any banner has been dismissed */}
        {hasDismissedBanner && (
          <button
            className="cursor-pointer text-muted-foreground text-sm underline hover:text-foreground"
            onClick={handleReset}
            type="button"
          >
            Reset all banners
          </button>
        )}
      </div>
    </div>
  );
}
