/**
 * Manual vitest mock for streamdown (ESM-only markdown renderer).
 *
 * In tests we only care that the text content is reachable in the DOM,
 * not that it's styled/rendered as rich HTML.
 */
import type * as React from 'react';

export function Streamdown({ children }: { children: string }): React.JSX.Element {
  return <div data-testid="streamdown">{children}</div>;
}
