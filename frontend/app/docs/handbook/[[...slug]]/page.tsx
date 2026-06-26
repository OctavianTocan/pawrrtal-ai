/**
 * Dynamic `/docs/handbook/[[...slug]]` page: looks up the MDX page
 * for the active slug in `handbookSource` and renders its body.
 */

import { createRelativeLink } from 'fumadocs-ui/mdx';
import { DocsBody, DocsDescription, DocsPage, DocsTitle } from 'fumadocs-ui/page';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import { handbookSource } from '@/lib/source';

/**
 * Renders a handbook page by slug.
 *
 * @param props.params - dynamic route params (`slug?: string[]`)
 * @returns the rendered MDX page
 */
export default async function HandbookPage(props: {
  params: Promise<{ slug?: string[] }>;
}): Promise<React.ReactElement> {
  const params = await props.params;
  const page = handbookSource.getPage(params.slug);
  if (!page) notFound();

  const MdxContent = page.data.body;

  return (
    <DocsPage toc={page.data.toc} full={page.data.full}>
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody>
        <MdxContent
          components={getMDXComponents({
            a: createRelativeLink(handbookSource, page),
          })}
        />
      </DocsBody>
    </DocsPage>
  );
}

/**
 * Generates static params for every handbook MDX page so they prerender.
 *
 * @returns one params object per page
 */
export async function generateStaticParams(): Promise<{ slug?: string[] }[]> {
  return handbookSource.generateParams();
}

/**
 * Generates per-page metadata (title, description).
 *
 * @param props.params - dynamic route params
 * @returns the metadata for the active slug
 */
export async function generateMetadata(props: { params: Promise<{ slug?: string[] }> }): Promise<Metadata> {
  const params = await props.params;
  const page = handbookSource.getPage(params.slug);
  if (!page) notFound();
  return {
    title: page.data.title,
    description: page.data.description,
  };
}
