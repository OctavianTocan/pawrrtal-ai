import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SummaryText } from './SummaryText';
import type { AccessRequest } from './types';

const mk = (name: string, id = name): AccessRequest => ({ id, name });

describe('SummaryText', () => {
  it('renders nothing when the request list is empty', () => {
    const { container } = render(<SummaryText requests={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the singular form for one request', () => {
    const { container } = render(<SummaryText requests={[mk('alice')]} />);
    expect(container.textContent).toContain('@alice');
    expect(container.textContent).toContain('is requesting access');
  });

  it('renders the dual form for two requests', () => {
    const { container } = render(<SummaryText requests={[mk('alice'), mk('bob')]} />);
    expect(container.textContent).toContain('@alice');
    expect(container.textContent).toContain('@bob');
    expect(container.textContent).toContain('are requesting access');
  });

  it('renders the +N others form for 3+ requests', () => {
    const { container } = render(<SummaryText requests={[mk('alice'), mk('bob'), mk('carol'), mk('dave')]} />);
    expect(container.textContent).toContain('@alice');
    expect(container.textContent).toContain('3 others');
  });
});
