/**
 * MDX component registry shared by every Fumadocs page.
 */

import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';

/**
 * Returns the merged MDX component registry: the Fumadocs default
 * components, optionally overridden by the caller.
 *
 * @param components - optional per-call overrides
 * @returns the full MDX component registry
 */
export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    ...components,
  };
}

const _useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
