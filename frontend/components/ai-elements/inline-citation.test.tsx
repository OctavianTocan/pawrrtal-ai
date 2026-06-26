import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { InlineCitation, InlineCitationCard, InlineCitationCardTrigger, InlineCitationText } from './inline-citation';

describe('InlineCitation', () => {
  it('wraps text content with the inline class', () => {
    const { container } = render(
      <InlineCitation>
        <InlineCitationText>The sky is blue.</InlineCitationText>
      </InlineCitation>
    );
    expect(container.textContent).toContain('The sky is blue.');
  });

  it('renders the trigger badge with the first source hostname', () => {
    const { getByText } = render(
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={['https://anthropic.com/research']} />
      </InlineCitationCard>
    );
    expect(getByText(/anthropic\.com/)).toBeTruthy();
  });

  it('shows the +N affordance when there are 2+ sources', () => {
    const { container } = render(
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={['https://a.com/p', 'https://b.com/p', 'https://c.com/p']} />
      </InlineCitationCard>
    );
    expect(container.textContent).toContain('+2');
  });

  it('falls back to "unknown" when no sources are passed', () => {
    const { getByText } = render(
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={[]} />
      </InlineCitationCard>
    );
    expect(getByText('unknown')).toBeTruthy();
  });
});
