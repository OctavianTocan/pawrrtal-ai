import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
} from './confirmation';

const APPROVED = { id: 'a1', approved: true } as const;
const REJECTED = { id: 'a1', approved: false } as const;

describe('Confirmation', () => {
  it('renders the request branch on approval-requested', () => {
    const { getByText } = render(
      <Confirmation approval={APPROVED} state="approval-requested">
        <ConfirmationTitle>Run command?</ConfirmationTitle>
        <ConfirmationRequest>command body</ConfirmationRequest>
      </Confirmation>
    );
    expect(getByText('Run command?')).toBeTruthy();
    expect(getByText('command body')).toBeTruthy();
  });

  it('renders the accepted branch on approval-responded with approved=true', () => {
    const { getByText } = render(
      <Confirmation approval={APPROVED} state="approval-responded">
        <ConfirmationAccepted>accepted body</ConfirmationAccepted>
      </Confirmation>
    );
    expect(getByText('accepted body')).toBeTruthy();
  });

  it('renders the rejected branch on output-denied with approved=false', () => {
    const { getByText } = render(
      <Confirmation approval={REJECTED} state="output-denied">
        <ConfirmationRejected>rejected body</ConfirmationRejected>
      </Confirmation>
    );
    expect(getByText('rejected body')).toBeTruthy();
  });

  it('fires action handlers when ConfirmationAction is clicked', () => {
    const onClick = vi.fn();
    const { getByRole } = render(
      <Confirmation approval={APPROVED} state="approval-requested">
        <ConfirmationActions>
          <ConfirmationAction onClick={onClick}>Yes</ConfirmationAction>
        </ConfirmationActions>
      </Confirmation>
    );
    fireEvent.click(getByRole('button', { name: 'Yes' }));
    expect(onClick).toHaveBeenCalled();
  });

  it('renders nothing when state is input-available', () => {
    const { container } = render(
      <Confirmation approval={APPROVED} state="input-available">
        <ConfirmationTitle>Hidden</ConfirmationTitle>
      </Confirmation>
    );
    expect(container.firstChild).toBeNull();
  });
});
