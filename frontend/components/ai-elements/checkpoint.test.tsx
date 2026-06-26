import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Checkpoint, CheckpointIcon, CheckpointTrigger } from './checkpoint';

describe('Checkpoint', () => {
  it('renders children inside the wrapper', () => {
    const { getByText } = render(
      <Checkpoint>
        <span>checkpoint label</span>
      </Checkpoint>
    );
    expect(getByText('checkpoint label')).toBeTruthy();
  });
});

describe('CheckpointIcon', () => {
  it('renders the bookmark glyph by default', () => {
    const { container } = render(<CheckpointIcon />);
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('renders provided children instead of the default glyph', () => {
    const { getByText } = render(
      <CheckpointIcon>
        <span>★</span>
      </CheckpointIcon>
    );
    expect(getByText('★')).toBeTruthy();
  });
});

describe('CheckpointTrigger', () => {
  it('renders without a tooltip by default', () => {
    const { getByRole } = render(<CheckpointTrigger>Resume</CheckpointTrigger>);
    expect(getByRole('button', { name: 'Resume' })).toBeTruthy();
  });

  it('still renders the button when a tooltip is supplied', () => {
    const { getByRole } = render(<CheckpointTrigger tooltip="hover hint">Resume</CheckpointTrigger>);
    expect(getByRole('button', { name: 'Resume' })).toBeTruthy();
  });
});
