import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Source, Sources, SourcesTrigger } from './sources';

describe('Sources', () => {
  it('renders the trigger with the default "Used N sources" copy', () => {
    const { getByText } = render(
      <Sources>
        <SourcesTrigger count={3} />
      </Sources>
    );
    expect(getByText('Used 3 sources')).toBeTruthy();
  });

  it('renders custom trigger children when supplied', () => {
    const { getByText } = render(
      <Sources>
        <SourcesTrigger count={1}>my trigger</SourcesTrigger>
      </Sources>
    );
    expect(getByText('my trigger')).toBeTruthy();
  });

  it('renders a Source link with the supplied href + title', () => {
    const { getByRole } = render(<Source href="https://example.com" title="Example" />);
    const link = getByRole('link');
    expect(link.getAttribute('href')).toBe('https://example.com');
    expect(link.textContent).toContain('Example');
  });
});
