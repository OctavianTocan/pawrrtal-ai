'use client';

import type * as React from 'react';
import { useCallback, useEffect, useId, useReducer, useRef } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { OnboardingBackdrop } from '@/features/onboarding/OnboardingBackdrop';
import { OnboardingCreateWorkspaceStep } from '@/features/onboarding/onboarding-create-workspace-step';
import { OnboardingLocalWorkspaceStep } from '@/features/onboarding/onboarding-local-workspace-step';
import { OnboardingWelcomeStep } from '@/features/onboarding/onboarding-welcome-step';

/** Wizard steps for the cosmetic onboarding dialog (no persisted workspace). */
type OnboardingStep = 'welcome' | 'create' | 'local';

/** Browser event used by app chrome to reopen the cosmetic onboarding flow. */
export const OPEN_ONBOARDING_EVENT = 'pawrrtal:open-onboarding';

type OnboardingModalState = {
	open: boolean;
	step: OnboardingStep;
	folderLabel: string | null;
};

type OnboardingModalAction =
	| { type: 'set-open'; open: boolean }
	| { type: 'set-step'; step: OnboardingStep }
	| { type: 'set-folder-label'; folderLabel: string }
	| { type: 'restart' };

const createInitialState = (open: boolean): OnboardingModalState => ({
	open,
	step: 'welcome',
	folderLabel: null,
});

const onboardingModalReducer = (
	state: OnboardingModalState,
	action: OnboardingModalAction
): OnboardingModalState => {
	switch (action.type) {
		case 'set-open':
			return { ...state, open: action.open };
		case 'set-step':
			return { ...state, step: action.step };
		case 'set-folder-label':
			return { ...state, folderLabel: action.folderLabel };
		case 'restart':
			return { open: true, step: 'welcome', folderLabel: null };
		default:
			return state;
	}
};

/** Props for the onboarding modal host. */
export interface OnboardingModalProps {
	/** Whether the modal should be open on first mount. */
	initialOpen?: boolean;
	/** Whether this instance should listen for app chrome requests to reopen onboarding. */
	listenForOpenEvent?: boolean;
}

/**
 * Three-step onboarding modal (Welcome → Create workspace → Local workspace).
 * Cosmetic only: no workspace or folder path is persisted (see future backend work).
 */
export function OnboardingModal({
	initialOpen = true,
	listenForOpenEvent = true,
}: OnboardingModalProps): React.JSX.Element {
	const folderInputRef = useRef<HTMLInputElement>(null);
	const folderInputId = useId();
	const [state, dispatch] = useReducer(onboardingModalReducer, initialOpen, createInitialState);
	const { open, step, folderLabel } = state;

	const handleOpenChange = useCallback((next: boolean) => {
		if (next) {
			dispatch({ type: 'set-open', open: true });
		}
	}, []);

	const handleFolderChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
		const files = event.target.files;
		const first = files?.[0];
		if (!first) {
			return;
		}
		const relative = first.webkitRelativePath;
		const nameFromPath = relative.includes('/') ? relative.split('/')[0] : null;
		dispatch({
			type: 'set-folder-label',
			folderLabel: nameFromPath ?? first.name ?? 'Selected folder',
		});
	}, []);

	const handleSelectFolderClick = useCallback(() => {
		folderInputRef.current?.click();
	}, []);

	const handleFinish = useCallback(() => {
		dispatch({ type: 'set-open', open: false });
	}, []);

	useEffect(() => {
		if (!listenForOpenEvent) {
			return undefined;
		}

		const handleOpenOnboarding = (): void => dispatch({ type: 'restart' });

		window.addEventListener(OPEN_ONBOARDING_EVENT, handleOpenOnboarding);

		return (): void => {
			window.removeEventListener(OPEN_ONBOARDING_EVENT, handleOpenOnboarding);
		};
	}, [listenForOpenEvent]);

	const accessibleTitle =
		step === 'welcome'
			? 'Welcome to Pawrrtal'
			: step === 'create'
				? 'Create workspace'
				: 'Local workspace';

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent
				showCloseButton={false}
				className="top-0 left-0 h-[100dvh] max-h-none w-screen max-w-none translate-x-0 translate-y-0 overflow-y-auto overscroll-contain rounded-none border-0 bg-background p-0 text-foreground shadow-none ring-0 sm:max-w-none sm:p-0 [&>button]:top-6 [&>button]:right-6 [&>button]:z-30 [&>button]:rounded-control [&>button]:bg-foreground/[0.035] [&>button]:text-muted-foreground [&>button]:ring-1 [&>button]:ring-border [&>button]:hover:bg-foreground/[0.07] [&>button]:hover:text-foreground"
			>
				{/*
          Radix requires DialogTitle inside DialogContent. Do not set aria-labelledby / id with
          useId() — Radix dev TitleWarning uses document.getElementById and can false-positive when
          ids are wired manually; DialogTitle wires aria-labelledby via context automatically.
        */}
				<DialogTitle className="sr-only">{accessibleTitle}</DialogTitle>
				<OnboardingBackdrop />
				<div className="relative z-10 flex min-h-full items-start justify-center px-4 py-8 sm:items-center sm:px-8 sm:py-20">
					{step === 'welcome' ? (
						<OnboardingWelcomeStep
							onContinue={() => dispatch({ type: 'set-step', step: 'create' })}
						/>
					) : null}
					{step === 'create' ? (
						<OnboardingCreateWorkspaceStep
							onPickLocal={() => dispatch({ type: 'set-step', step: 'local' })}
							onClose={() => dispatch({ type: 'set-open', open: false })}
						/>
					) : null}
					{step === 'local' ? (
						<OnboardingLocalWorkspaceStep
							folderInputId={folderInputId}
							folderInputRef={folderInputRef}
							folderLabel={folderLabel}
							onFolderChange={handleFolderChange}
							onSelectFolderClick={handleSelectFolderClick}
							onBack={() => dispatch({ type: 'set-step', step: 'create' })}
							onFinish={handleFinish}
						/>
					) : null}
				</div>
			</DialogContent>
		</Dialog>
	);
}
