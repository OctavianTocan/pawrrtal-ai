/**
 * `/docs` landing page: hero + three short feature blurbs + section CTAs.
 *
 * Uses Fumadocs' `<Cards>` / `<Card>` primitives for the section
 * choosers so the hover affordances and iconography match the rest of
 * the docs surface. The hero copy keeps the brand voice short: one
 * sentence on what Pawrrtal is, then three blurbs that map to what a
 * visitor would reasonably want next (try it, learn how it works, or
 * read the source).
 */

import { Card, Cards } from 'fumadocs-ui/components/card';
import { BookOpenIcon, BoxIcon, CodeIcon, ExternalLinkIcon } from 'lucide-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Pawrrtal Docs',
  description: 'Pawrrtal documentation: handbook (contributors and agents) and product (users).',
};

const GITHUB_URL = 'https://github.com/OctavianTocan/pawrrtal';

/**
 * Renders the docs landing: hero + feature blurbs + section CTAs.
 *
 * @returns the landing page
 */
export default function DocsLanding(): React.ReactElement {
  return (
    <main className="pawrrtal-docs mx-auto flex max-w-3xl flex-col gap-12 px-6 py-16">
      <header className="flex flex-col gap-3">
        <p className="font-medium text-fd-primary text-sm uppercase tracking-wide">Documentation</p>
        <h1 className="font-medium text-4xl leading-tight tracking-tight md:text-5xl">
          Pawrrtal is a model-agnostic chat app.
        </h1>
        <p className="text-fd-muted-foreground text-lg">
          Pick a model each turn &mdash; Anthropic, Google, OpenAI, whichever fits the task &nbsp;&mdash; and Pawrrtal
          handles history, streaming, modes, and tools around it.
        </p>
      </header>

      <section className="grid gap-6 sm:grid-cols-3">
        <div className="flex flex-col gap-2">
          <BoxIcon aria-hidden="true" className="size-5 text-fd-primary" />
          <h2 className="font-medium text-sm">Model-agnostic</h2>
          <p className="text-fd-muted-foreground text-sm">
            Switch providers mid-conversation. Your history travels with you.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <CodeIcon aria-hidden="true" className="size-5 text-fd-primary" />
          <h2 className="font-medium text-sm">Plan + safety modes</h2>
          <p className="text-fd-muted-foreground text-sm">
            Preview multi-step work before it runs. Approve tool calls when stakes are higher.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <BookOpenIcon aria-hidden="true" className="size-5 text-fd-primary" />
          <h2 className="font-medium text-sm">Open development</h2>
          <p className="text-fd-muted-foreground text-sm">
            ADRs, agent guidance, and CI notes are all public. Read why the codebase looks the way it does.
          </p>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="font-medium text-fd-muted-foreground text-xs uppercase tracking-wide">Pick a section</h2>
        <Cards>
          <Card
            description="How to use Pawrrtal — models, modes, settings, sidebar, conversations."
            href="/docs/product"
            icon={<BoxIcon aria-hidden="true" />}
            title="Product"
          />
          <Card
            description="Architecture decisions, agent guidance, CI, deployment. For contributors and agents."
            href="/docs/handbook"
            icon={<BookOpenIcon aria-hidden="true" />}
            title="Handbook"
          />
          <Card
            description="The repo, the issues, the commit log. Pawrrtal is built in the open."
            external
            href={GITHUB_URL}
            icon={<ExternalLinkIcon aria-hidden="true" />}
            title="Source on GitHub"
          />
        </Cards>
      </section>
    </main>
  );
}
