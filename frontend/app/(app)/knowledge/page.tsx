import type { ReactNode } from 'react';
import { Suspense } from 'react';
import { KnowledgeContainer } from '@/features/knowledge/KnowledgeContainer';

/**
 * `/knowledge` route entry.
 *
 * Server component shell — renders the client-side {@link KnowledgeContainer}
 * inside a `Suspense` boundary so `useSearchParams` (which requires Suspense
 * in the App Router) works without a CSR bailout warning.
 *
 * The `(app)` segment layout already wraps this in `AppShell`, so the
 * global sidebar and header are present without any extra plumbing here.
 */
export default function KnowledgePage(): ReactNode {
  return (
    <Suspense fallback={null}>
      <KnowledgeContainer />
    </Suspense>
  );
}
