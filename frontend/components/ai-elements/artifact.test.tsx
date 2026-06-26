import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  Artifact,
  ArtifactAction,
  ArtifactActions,
  ArtifactClose,
  ArtifactContent,
  ArtifactDescription,
  ArtifactHeader,
  ArtifactTitle,
} from './artifact';

describe('Artifact', () => {
  it('renders the title + description copy + content', () => {
    const { getByText } = render(
      <Artifact>
        <ArtifactHeader>
          <ArtifactTitle>my artifact</ArtifactTitle>
          <ArtifactDescription>summary line</ArtifactDescription>
        </ArtifactHeader>
        <ArtifactContent>
          <p>body</p>
        </ArtifactContent>
      </Artifact>
    );
    expect(getByText('my artifact')).toBeTruthy();
    expect(getByText('summary line')).toBeTruthy();
    expect(getByText('body')).toBeTruthy();
  });

  it('fires onClose when the close button is activated', () => {
    const onClose = vi.fn();
    const { getByRole } = render(
      <Artifact>
        <ArtifactHeader>
          <ArtifactClose onClick={onClose} />
        </ArtifactHeader>
      </Artifact>
    );
    getByRole('button').click();
    expect(onClose).toHaveBeenCalled();
  });

  it('renders custom action buttons inside ArtifactActions', () => {
    const { getByRole } = render(
      <Artifact>
        <ArtifactHeader>
          <ArtifactActions>
            <ArtifactAction tooltip="copy">
              <span>copy</span>
            </ArtifactAction>
          </ArtifactActions>
        </ArtifactHeader>
      </Artifact>
    );
    expect(getByRole('button', { name: /copy/i })).toBeTruthy();
  });
});
