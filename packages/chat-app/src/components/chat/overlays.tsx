/**
 * `Overlays` — renders whichever transient overlay (model selector, attachment
 * menu, voice capture) is currently open, based on the store's `overlay`
 * state. Shared by the home and thread screens so the composer's controls
 * behave the same wherever it appears.
 */
import { useAppState } from '@/runtime';
import { AttachmentOverlay } from './attachment-overlay';
import { ModelSelectorOverlay } from './model-selector-overlay';
import { VoiceOverlay } from './voice-overlay';

/** Renders the active composer overlay, if any. */
export function Overlays(): React.JSX.Element | null {
  const { overlay } = useAppState();
  if (overlay === 'model') return <ModelSelectorOverlay />;
  if (overlay === 'attachment') return <AttachmentOverlay />;
  if (overlay === 'voice') return <VoiceOverlay />;
  return null;
}
