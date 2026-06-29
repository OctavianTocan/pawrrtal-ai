'use client';

import type * as React from 'react';
import { useCallback, useEffect, useReducer } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { OnboardingBackdrop } from '@/features/onboarding/OnboardingBackdrop';
import type { PersonalizationProfile } from '@/lib/personalization/storage';
import { loadPersonalizationProfile, savePersonalizationProfile } from '@/lib/personalization/storage';
import { useGetPersonalization, useUpsertPersonalization } from '@/lib/personalization/use-personalization';
import { StepContext } from './step-context';
import { StepIdentity } from './step-identity';
import { StepMessaging } from './step-messaging';
import { StepPersonality } from './step-personality';

/** Browser event used by app chrome to open the onboarding flow. */
export const OPEN_ONBOARDING_FLOW_EVENT = 'pawrrtal:open-onboarding-flow';

/**
 * Localstorage flag + query-string param that suppress the auto-open
 * onboarding modal entirely. Used by the E2E suite so Stagehand-driven
 * specs can land directly on `/` without first having to walk through
 * the 4-step wizard. The wizard is mounted at app-layout level with
 * `initialOpen=true`, has no Escape close, and burns ~3 minutes + a lot
 * of LLM tokens to traverse — gating it here keeps the chat / sidebar /
 * tool E2Es fast and deterministic.
 *
 * Triggered by either:
 *   - `localStorage.setItem('pawrrtal:e2e-skip-onboarding', '1')` (set
 *     by `fixtures.ts` via an `addInitScript` before navigation), OR
 *   - visiting any URL with `?e2e_skip_onboarding=1` (manual debugging).
 *
 * The wizard remains usable in production: nothing fires unless one of
 * those signals is present, and the workspace selector's "Add Workspace"
 * dropdown still opens the (separate) `OnboardingModal` either way.
 */
export const E2E_SKIP_ONBOARDING_STORAGE_KEY = 'pawrrtal:e2e-skip-onboarding';
export const E2E_SKIP_ONBOARDING_QUERY_PARAM = 'e2e_skip_onboarding';

/**
 * Persisted when the user completes the onboarding wizard via {@link finish}.
 * Prevents the wizard from re-opening on subsequent page loads.
 * Clear this key to re-trigger the wizard (e.g. from Settings → Onboarding).
 */
export const ONBOARDING_COMPLETE_STORAGE_KEY = 'pawrrtal:onboarding-v2-complete';

/** Wizard step IDs in render order. */
const STEP_IDS = ['identity', 'context', 'personality', 'messaging'] as const;
export type StepId = (typeof STEP_IDS)[number];

interface OnboardingFlowState {
  open: boolean;
  profile: PersonalizationProfile;
  step: StepId;
}

type OnboardingFlowAction =
  | { type: 'hydrate-profile'; profile: PersonalizationProfile }
  | { type: 'open-at-step'; profile: PersonalizationProfile; step: StepId }
  | { type: 'patch-profile'; patch: Partial<PersonalizationProfile> }
  | { type: 'set-open'; open: boolean }
  | { type: 'set-step'; step: StepId };

function onboardingFlowReducer(state: OnboardingFlowState, action: OnboardingFlowAction): OnboardingFlowState {
  if (action.type === 'hydrate-profile') {
    return { ...state, profile: action.profile };
  }
  if (action.type === 'open-at-step') {
    return { open: true, profile: action.profile, step: action.step };
  }
  if (action.type === 'patch-profile') {
    return { ...state, profile: { ...state.profile, ...action.patch } };
  }
  if (action.type === 'set-open') {
    return { ...state, open: action.open };
  }
  if (action.type === 'set-step') {
    return { ...state, step: action.step };
  }
  return state;
}

/**
 * Returns true when the current page should suppress the auto-open
 * onboarding wizard (E2E test mode). Safe to call on the server — the
 * `window` guard returns false during SSR so React hydrates with the
 * production-default state and we flip to "skip" on first client paint
 * (which then runs before any user interaction is possible).
 */
function shouldSkipOnboardingForE2E(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (window.localStorage.getItem(E2E_SKIP_ONBOARDING_STORAGE_KEY) === '1') {
      return true;
    }
  } catch {
    // localStorage may throw in private browsing — fall through to
    // the URL check rather than crashing the whole app.
  }
  const searchParams = new URLSearchParams(window.location.search);
  return searchParams.get(E2E_SKIP_ONBOARDING_QUERY_PARAM) === '1';
}

/**
 * Returns true when the user has already completed the onboarding wizard
 * in this browser. Safe to call on the server — the window guard returns
 * false during SSR so the modal hydrates correctly.
 */
function hasCompletedOnboarding(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(ONBOARDING_COMPLETE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function shouldInitiallyOpenFlow(initialOpen: boolean): boolean {
  if (!initialOpen) return false;
  if (shouldSkipOnboardingForE2E()) return false;
  if (hasCompletedOnboarding()) return false;
  return true;
}

/**
 * Close the wizard, mark onboarding complete, and (on first completion)
 * force a full-page navigation so the app shell boots with a committed
 * session cookie. Extracted to keep {@link OnboardingFlow} under the
 * Biome `noExcessiveLinesPerFunction` budget.
 */
function finishOnboarding(dispatch: React.Dispatch<OnboardingFlowAction>): void {
  const wasAlreadyComplete = hasCompletedOnboarding();
  try {
    window.localStorage.setItem(ONBOARDING_COMPLETE_STORAGE_KEY, '1');
  } catch {
    /* quota / private browsing — ignore */
  }
  dispatch({ type: 'set-open', open: false });
  // Reset to step 1 so re-opening from the workspace selector starts
  // fresh — without this the user would land on whatever step they
  // last left off, which is jarring for a "new workspace" intent.
  dispatch({ type: 'set-step', step: 'identity' });
  if (!wasAlreadyComplete) {
    // Full-page navigation on first completion resets the app shell
    // with the session cookie fully committed — prevents the blank-page
    // race where authed queries fire before Set-Cookie flushes.
    // Re-opens from the workspace selector skip this to avoid discarding
    // in-progress UI state (active conversations, etc.).
    window.location.replace('/');
  }
}

/** Props for {@link OnboardingFlow}. */
export interface OnboardingFlowProps {
  /** Open on first mount. Defaults to false (event-driven). */
  initialOpen?: boolean;
  /** Step shown when the flow opens on first mount. Defaults to identity. */
  initialStep?: StepId;
  /** Listen for the OPEN_ONBOARDING_FLOW_EVENT to open. Defaults to true. */
  listenForOpenEvent?: boolean;
}

/**
 * Four-step onboarding wizard mounted once at app-layout level.
 *
 * Steps: Identity → Context → Personality → Connect Messaging.
 *
 * Stays closed until either `initialOpen` is true OR the
 * `OPEN_ONBOARDING_FLOW_EVENT` is dispatched (the workspace selector's
 * "Add Workspace" item dispatches it).
 *
 * The personalization answers persist to localStorage under the same
 * key the Settings → Personalization section reads, so changes round-trip.
 */
export function OnboardingFlow({
  initialOpen = false,
  initialStep = 'identity',
  listenForOpenEvent = true,
}: OnboardingFlowProps): React.JSX.Element {
  // The reducer initializer reads the E2E skip flag exactly once on mount.
  // During SSR `shouldSkipOnboardingForE2E` returns false so the dialog
  // hydrates closed (no flash); on the client we re-check synchronously
  // before the first paint so the modal never visibly appears in test
  // mode. Production users' `initialOpen=true` survives unchanged
  // because the skip helper short-circuits to false without the flag.
  const remotePersonalization = useGetPersonalization();
  const upsertPersonalization = useUpsertPersonalization();
  // Seed from localStorage on first render so the form has data to
  // display before the React Query GET resolves. Once the remote
  // profile arrives, hydrate over the local copy below in an effect.
  const [flowState, dispatchFlowState] = useReducer(
    onboardingFlowReducer,
    null,
    (): OnboardingFlowState => ({
      open: shouldInitiallyOpenFlow(initialOpen),
      profile: loadPersonalizationProfile(),
      step: initialStep,
    })
  );
  const { open, profile, step } = flowState;

  // Hydrate from the backend the first time it arrives + on every
  // subsequent refetch — keeps local state aligned with persisted state
  // after the user navigates away and comes back.
  useEffect(() => {
    if (remotePersonalization.data) {
      dispatchFlowState({ type: 'hydrate-profile', profile: remotePersonalization.data });
    }
  }, [remotePersonalization.data]);

  /**
   * Persist on every patch.
   *
   * Two-channel write: localStorage stays the synchronous draft buffer
   * (so a refresh during the session never loses the user's work even
   * if the backend is down) and the backend PUT is the source of truth.
   * Both writes are fire-and-forget — the form treats success as the
   * default and only surfaces backend failures as a toast through the
   * mutation's error path (handled in the calling component / hook).
   */
  const patchProfile = useCallback(
    (patch: Partial<PersonalizationProfile>): void => {
      const next = { ...flowState.profile, ...patch };
      savePersonalizationProfile(next);
      upsertPersonalization.mutate(next);
      dispatchFlowState({ type: 'patch-profile', patch });
    },
    [flowState.profile, upsertPersonalization]
  );

  const goNext = useCallback(() => {
    const index = STEP_IDS.indexOf(step);
    const nextStep = STEP_IDS[Math.min(STEP_IDS.length - 1, index + 1)];
    dispatchFlowState({ type: 'set-step', step: nextStep ?? step });
  }, [step]);

  const finish = useCallback(() => {
    finishOnboarding(dispatchFlowState);
  }, []);

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      dispatchFlowState({ type: 'set-open', open: true });
    }
  }, []);

  // Listen for the generic "open the flow" event — gated by listenForOpenEvent
  // so embedders that manage their own open state can opt out.
  useEffect(() => {
    if (!listenForOpenEvent) return;
    // Honor the same E2E skip flag for the event-driven open path so
    // a stray "Add Workspace" click during a test can't accidentally
    // re-open the wizard. The legacy workspace OnboardingModal lives
    // in a separate component and is unaffected.
    if (shouldSkipOnboardingForE2E()) return;
    const handler = (): void => {
      dispatchFlowState({
        type: 'open-at-step',
        profile: loadPersonalizationProfile(),
        step: 'identity',
      });
    };
    window.addEventListener(OPEN_ONBOARDING_FLOW_EVENT, handler);
    return () => window.removeEventListener(OPEN_ONBOARDING_FLOW_EVENT, handler);
  }, [listenForOpenEvent]);

  return (
    <Dialog onOpenChange={handleOpenChange} open={open}>
      <DialogContent
        className="top-0 left-0 h-[100dvh] max-h-none w-screen max-w-none translate-x-0 translate-y-0 overflow-y-auto overscroll-contain rounded-none border-0 bg-background p-0 text-foreground shadow-none ring-0 sm:max-w-none sm:p-0 [&>button]:top-6 [&>button]:right-6 [&>button]:z-30 [&>button]:rounded-control [&>button]:bg-foreground/[0.035] [&>button]:text-muted-foreground [&>button]:ring-1 [&>button]:ring-border [&>button]:hover:bg-foreground/[0.07] [&>button]:hover:text-foreground"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">Onboarding</DialogTitle>
        <OnboardingBackdrop />
        <div className="relative z-10 flex min-h-full items-start justify-center px-4 py-8 sm:items-center sm:px-8 sm:py-20">
          {step === 'identity' ? <StepIdentity onContinue={goNext} onPatch={patchProfile} profile={profile} /> : null}
          {step === 'context' ? (
            <StepContext onContinue={goNext} onPatch={patchProfile} onSkip={goNext} profile={profile} />
          ) : null}
          {step === 'personality' ? (
            <StepPersonality onContinue={goNext} onPatch={patchProfile} profile={profile} />
          ) : null}
          {step === 'messaging' ? <StepMessaging onFinish={finish} onPatch={patchProfile} profile={profile} /> : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
