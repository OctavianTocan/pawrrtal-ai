'use client';

/**
 * Full-screen viewer for an expanded artifact.
 *
 * @fileoverview Mounted into a portal so the dialog escapes any
 * containing-block transforms in the chat surface (popovers and the
 * floating composer use `transform`, which would otherwise re-anchor
 * the modal). Header carries the artifact title + an X close button;
 * body renders the full json-render spec.
 *
 * Accessibility: traps Escape via the dialog overlay's keydown handler,
 * focuses the close button on mount, and dimming the page background.
 * No focus-trap library — this is a single-action modal, the close
 * button is the only interactive element after mount unless the spec
 * itself contains buttons.
 */

import { XIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { ChatArtifactPayload } from '@/lib/types';
import { ArtifactRenderer } from './ArtifactRenderer';

interface ArtifactDialogProps {
  artifact: ChatArtifactPayload;
  onClose: () => void;
}

export function ArtifactDialog({ artifact, onClose }: ArtifactDialogProps): ReactNode {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    closeRef.current?.focus();
    // Lock body scroll while the dialog is open.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handleKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return createPortal(
    <dialog
      aria-label={artifact.title}
      aria-modal="true"
      className="artifact-dialog-overlay"
      onClick={(e) => {
        // Click on the overlay (but not bubbled from the inner dialog)
        // closes — same affordance most chat-app modals use.
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose();
      }}
      open
    >
      <div className="artifact-dialog">
        <header className="artifact-dialog-header">
          <h2 className="artifact-dialog-title">{artifact.title}</h2>
          <button
            aria-label="Close artifact"
            className="artifact-dialog-close"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            <XIcon className="size-4" />
          </button>
        </header>
        <div className="artifact-dialog-body">
          {/* Close on successful interaction submit so the user sees
					    the chat respond instead of staring at the modal. */}
          <ArtifactRenderer artifact={artifact} onInteractionSubmitted={onClose} />
        </div>
      </div>
    </dialog>,
    document.body
  );
}
