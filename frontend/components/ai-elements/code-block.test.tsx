import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CodeBlock, CodeBlockCopyButton } from './code-block';

describe('CodeBlock', () => {
  it('renders the outer container even before shiki resolves', () => {
    const { container } = render(<CodeBlock code={'hi'} language="ts" />);
    expect(container.firstElementChild).toBeTruthy();
  });

  it('renders an action button when CodeBlockCopyButton is supplied', () => {
    const { getByRole } = render(
      <CodeBlock code="hi" language="ts">
        <CodeBlockCopyButton />
      </CodeBlock>
    );
    expect(getByRole('button')).toBeTruthy();
  });

  it('does not crash when no code is supplied', () => {
    const { container } = render(<CodeBlock code="" language="ts" />);
    expect(container.firstElementChild).toBeTruthy();
  });
});
