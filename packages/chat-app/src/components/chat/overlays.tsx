/**
 * `Overlays` — renders whichever transient overlay (model selector, attachment
 * menu, voice capture) is currently open, based on the store's `overlay`
 * state. Shared by the home and thread screens so the composer's controls
 * behave the same wherever it appears.
 */
import { useEffect } from 'react';
import { BackHandler, Platform } from 'react-native';
import { actions, useAppState, useRun } from '@/runtime';
import { AttachmentOverlay } from './attachment-overlay';
import { ModelSelectorOverlay } from './model-selector-overlay';
import { VoiceOverlay } from './voice-overlay';

/** Renders the active composer overlay, if any. */
export function Overlays(): React.JSX.Element | null {
  const { overlay } = useAppState();
  const run = useRun();
  const isOpen = overlay !== 'none';

  // Android hardware Back must dismiss an open overlay rather than pop the
  // route (which would leave a stale popover when the user returns). RN's
  // `BackHandler` is the only API for this, so a subscription effect is
  // required; it is only registered while an overlay is actually open, and
  // only on Android — `hardwareBackPress` never fires on iOS, and on
  // react-native-web `BackHandler` is a no-op shim, so the listener is
  // pointless off-Android. Gating here keeps the intent explicit.
  useEffect(() => {
    if (!isOpen || Platform.OS !== 'android') return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      run(actions.setOverlay('none'));
      return true; // consume the event — do not let the navigator pop
    });
    return () => subscription.remove();
  }, [isOpen, run]);

  // The overlay lives in the global store but visually belongs to the screen
  // that opened it. When this host unmounts — any route change, including the
  // browser Back button on web (where `BackHandler` never fires) — clear it so
  // the next screen that renders <Overlays /> doesn't reopen a stale popover
  // over the wrong route. `run` is stable (useCallback []), so this cleanup
  // runs only on unmount, never on re-render.
  useEffect(() => {
    return () => {
      run(actions.setOverlay('none'));
    };
  }, [run]);

  if (overlay === 'model') return <ModelSelectorOverlay />;
  if (overlay === 'attachment') return <AttachmentOverlay />;
  if (overlay === 'voice') return <VoiceOverlay />;
  return null;
}
