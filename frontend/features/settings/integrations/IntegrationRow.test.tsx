import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Calendar, Mail } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import type { IntegrationDef } from './catalog';
import { IntegrationRow } from './IntegrationRow';

const SIMPLE: IntegrationDef = {
  id: 'apple-calendar',
  name: 'Apple Calendar',
  description: 'See your events in Apple Calendar',
  badge: 'connected',
  Icon: Calendar,
  tileBgClass: 'bg-foreground/5',
  tileTextClass: 'text-foreground',
};

const WITH_ACCOUNTS: IntegrationDef = {
  id: 'gmail',
  name: 'Gmail',
  description: 'Read and send email in Gmail',
  Icon: Mail,
  tileBgClass: 'bg-red-500/15',
  tileTextClass: 'text-red-500',
  accounts: [
    {
      id: 'gmail-personal',
      email: 'tocan@example.com',
      subtitle: 'tocan@example.com',
      status: 'connected',
    },
    {
      id: 'gmail-work',
      email: 'tocan@work.example',
      status: 'expired',
      label: 'Work',
    },
  ],
};

describe('IntegrationRow', () => {
  it('renders a simple row with badge + settings button when no accounts', () => {
    const { getByText, getByLabelText } = render(<IntegrationRow integration={SIMPLE} />);
    expect(getByText('Apple Calendar')).toBeTruthy();
    expect(getByText('Connected')).toBeTruthy();
    expect(getByLabelText('Settings for Apple Calendar')).toBeTruthy();
  });

  it('renders an expandable header + per-account list when accounts exist', async () => {
    const user = userEvent.setup();
    const { getByText, queryByText } = render(<IntegrationRow integration={WITH_ACCOUNTS} />);
    // Default expanded — accounts should be visible.
    expect(getByText('tocan@example.com', { selector: 'span.truncate' })).toBeTruthy();
    expect(getByText('Work')).toBeTruthy();
    // Toggle collapsed — account rows should disappear.
    await user.click(getByText('Gmail'));
    expect(queryByText('Add another account')).toBeNull();
  });
});
