'use client';

/**
 * Inline preview card for an artifact rendered during the assistant turn.
 *
 * Click anywhere on the card → opens an {@link ArtifactDialog} that
 * renders the full spec with an X close button. The card itself shows
 * just the title + a tiny "click to expand" affordance, so the chat
 * scroll stays calm even when the agent ships a large artifact.
 */

import { ExpandIcon, FileTextIcon } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import type { ChatArtifactPayload } from '@/lib/types';
import { ArtifactDialog } from './ArtifactDialog';

interface ArtifactCardProps {
  artifact: ChatArtifactPayload;
}

export function ArtifactCard({ artifact }: ArtifactCardProps): ReactNode {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="artifact-preview-card"
        aria-label={`Open artifact "${artifact.title}"`}
      >
        <div className="artifact-preview-card-icon" aria-hidden="true">
          <FileTextIcon className="size-4" />
        </div>
        <div className="artifact-preview-card-body">
          <div className="artifact-preview-card-title">{artifact.title}</div>
          <div className="artifact-preview-card-sub">Click to expand</div>
        </div>
        <div className="artifact-preview-card-chev" aria-hidden="true">
          <ExpandIcon className="size-4" />
        </div>
      </button>
      {open ? <ArtifactDialog artifact={artifact} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
