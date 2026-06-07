/**
 * Application shell with resizable sidebar.
 *
 * Provides the main app shell with a resizable sidebar on desktop and
 * a mobile-friendly sheet overlay. Integrates SidebarProvider, navigation,
 * and content area with proper responsive behavior. Lives under
 * `features/app-shell/` (fe-features) rather than `components/` because
 * it composes nav-chats, onboarding, and chat-activity context providers;
 * keeping it in fe-shell forced same-order edges into 5 separate features.
 *
 * The header (workspace selector, help menu, history controls) is split
 * out into `AppShellHeader.tsx` to keep this file under the 500-LOC budget.
 *
 * @fileoverview Main app shell composition.
 */

'use client';

import React from 'react';
import { NavUser, type NavUserIdentity } from '@/components/nav-user';
import { NewSessionButton } from '@/components/new-session-button';
import { Button } from '@/components/ui/button';
import {
	Sidebar,
	SidebarContent,
	SidebarHeader,
	SidebarInset,
	SidebarProvider,
	useSidebar,
} from '@/components/ui/sidebar';
import { Skeleton } from '@/components/ui/skeleton';
import { ChatActivityProvider } from '@/features/nav-chats/context/chat-activity-context';
import { SidebarFocusProvider, useFocusZone } from '@/features/nav-chats/context/sidebar-focus';
import { NavChats } from '@/features/nav-chats/NavChats';
import { useOnboardingReadiness } from '@/features/onboarding/hooks/use-onboarding-readiness';
import { OnboardingModal } from '@/features/onboarding/OnboardingModal';
import {
	E2E_SKIP_ONBOARDING_STORAGE_KEY,
	OnboardingFlow,
	OPEN_ONBOARDING_FLOW_EVENT,
} from '@/features/onboarding/v2/OnboardingFlow';
import { useCurrentUser } from '@/hooks/use-current-user';
import { useGetPersonalization } from '@/lib/personalization/use-personalization';
import { cn } from '@/lib/utils';
import { AppShellHeader } from './AppShellHeader';

/**
 * Sidebar footer profile row — resolves the authenticated user's identity
 * from `GET /api/v1/users/me` + the personalization profile and renders `NavUser`.
 * Shows a skeleton placeholder while the user query is loading.
 */
function SidebarFooterUser(): React.JSX.Element {
	const { data: currentUser, isLoading: isUserLoading } = useCurrentUser();
	const { data: personalization } = useGetPersonalization();

	if (isUserLoading) {
		return <Skeleton className="mx-2 h-12 rounded-lg" />;
	}

	const sidebarUser: NavUserIdentity = {
		name: personalization?.name ?? currentUser?.email ?? '',
		email: currentUser?.email ?? '',
		plan: 'Pawrrtal',
	};

	return <NavUser user={sidebarUser} />;
}

function AppShellReadinessError({
	isRetrying,
	onRetry,
}: {
	isRetrying: boolean;
	onRetry: () => void;
}): React.JSX.Element {
	return (
		<div className="flex min-h-0 flex-1 items-center justify-center bg-background p-6">
			<div className="flex w-full max-w-sm flex-col gap-3 text-center">
				<h1 className="font-semibold text-lg text-foreground">Backend unavailable</h1>
				<p className="text-muted-foreground text-sm">
					Pawrrtal could not confirm workspace readiness. Check the service and try again.
				</p>
				<Button className="mx-auto" disabled={isRetrying} onClick={onRetry} type="button">
					{isRetrying ? 'Retrying' : 'Retry'}
				</Button>
			</div>
		</div>
	);
}

/**
 * Wraps sidebar content in a focus zone so keyboard navigation (Tab/Shift+Tab)
 * can jump directly to the sidebar region instead of walking every focusable element.
 * Focuses the first interactive child (input or button) when the zone receives focus.
 */
function SidebarFocusShell({
	children,
	className,
}: {
	children: React.ReactNode;
	className?: string;
}): React.JSX.Element {
	const { zoneRef } = useFocusZone({
		zoneId: 'sidebar',
		focusFirst: () => {
			const root = zoneRef.current;
			const target = root?.querySelector<HTMLElement>(
				'input, button, [tabindex]:not([tabindex="-1"])'
			);
			target?.focus();
		},
	});

	return (
		// No tabIndex needed: focus-zone entry delegates to the first interactive
		// child (input or button) via focusFirst, so the shell itself is never a
		// focus target. ChatFocusShell uses tabIndex={-1} because its focusFirst
		// targets a specific textarea/textbox — the shell div is the fallback.
		<div ref={zoneRef} className={className} data-focus-zone="sidebar">
			{children}
		</div>
	);
}

/**
 * Wraps the chat panel in a focus zone so keyboard navigation can jump
 * directly into the chat area. Targets the textarea or textbox first,
 * falling back to any focusable element.
 */
function ChatFocusShell({ children }: { children: React.ReactNode }): React.JSX.Element {
	const { zoneRef } = useFocusZone({
		zoneId: 'chat',
		focusFirst: () => {
			const root = zoneRef.current;
			const target = root?.querySelector<HTMLElement>(
				'textarea, [role="textbox"], button, [tabindex]:not([tabindex="-1"])'
			);
			target?.focus();
		},
	});

	return (
		// outline-none is safe: this div only receives focus programmatically via
		// focusZone('chat'), which immediately forwards to the textarea/textbox child.
		// Users never see keyboard focus land here.
		<div
			ref={zoneRef}
			className="h-full min-w-0 outline-none"
			data-focus-zone="chat"
			tabIndex={-1}
		>
			{children}
		</div>
	);
}

/**
 * Sidebar content wrapper with conditional resizable layout.
 * Renders the DESIGN.md-mandated translate-X slide on desktop and a Sheet
 * overlay on mobile.
 *
 * Desktop architecture (DESIGN.md L525-545):
 *
 * - Outer wrapper has `width: <desktopWidth>` always (when expanded), shrinks
 *   to `0` when collapsed; the chat panel occupies the freed layout space.
 * - Inner panel (absolutely positioned inside the wrapper) translates
 *   `translate-x-0` (open) ↔ `-translate-x-full` (closed) with
 *   `transition-transform duration-200 ease-out`.
 * - Chat panel shifts via the same width transition on the wrapper —
 *   `flex-1` consumes the freed space — so panel + sidebar move together.
 * - Resize handle is hidden / disabled while the panel is closed.
 * - The `--sidebar-width` CSS variable is the single source of truth: the
 *   drag handler writes to it, the wrapper reads from it for layout width.
 */
function ResizableSidebarContent({ children }: { children: React.ReactNode }): React.JSX.Element {
	const { isMobile, state, desktopWidth, isDesktopWidthReady, setDesktopWidth } = useSidebar();

	// Live layout width: when expanded → CSS variable; when collapsed → 0.
	// Setting `--sidebar-width` once on the documentElement lets descendants
	// (chat margin, etc.) read it without prop drilling, and lets the drag
	// handler animate it directly without re-rendering React on every frame.
	React.useLayoutEffect(() => {
		if (!isDesktopWidthReady) return;
		document.documentElement.style.setProperty('--sidebar-width', `${desktopWidth}px`);
	}, [desktopWidth, isDesktopWidthReady]);

	const isExpanded = state === 'expanded';
	// Drag-handle resize was removed in 2026-05; the previous implementation
	// caused jank under fast cursor moves. Will be reintroduced as part of
	// a dedicated rewrite. `setDesktopWidth` from `useSidebar` stays available
	// for any future re-introduction (e.g. via keyboard or settings).
	void setDesktopWidth;

	// Mobile: Sidebar renders as a Sheet overlay alongside main content.
	// The Sheet portals above the absolute AppHeader, so its content does not
	// need a header offset — only the chat surface does.
	if (isMobile) {
		return (
			<>
				<Sidebar>
					<SidebarFocusShell className="group flex h-full flex-col">
						<SidebarHeader className="px-2 pt-0 pb-1 shrink-0">
							<NewSessionButton />
						</SidebarHeader>
						<SidebarContent>
							<NavChats />
						</SidebarContent>
						<SidebarFooterUser />
					</SidebarFocusShell>
				</Sidebar>
				<div className="size-full min-w-0 pt-10">
					<ChatFocusShell>{children}</ChatFocusShell>
				</div>
			</>
		);
	}

	const transformTransition =
		'transition-transform duration-200 ease-out motion-reduce:transition-none';
	const widthTransition =
		'transition-[width] duration-200 ease-out motion-reduce:transition-none';

	// Outer wrapper occupies the open width when expanded; collapses to 0 when
	// closed so the chat panel can slide left into the freed space.
	const outerWidth = isExpanded ? `${desktopWidth}px` : '0px';

	return (
		<div className="relative flex min-h-0 min-w-0 flex-1">
			{/*
			 * Outer wrapper: always laid out at the sidebar's open width while
			 * expanded; shrinks to 0 when collapsed. Width transitions in
			 * lockstep with the inner panel's translate, so the chat panel
			 * (flex-1, occupies whatever's left) glides in sync.
			 */}
			<div
				className={cn('relative h-full overflow-hidden', widthTransition)}
				style={{ width: outerWidth }}
			>
				{/*
				 * Inner panel: full open width, translates X axis from 0 → -100%
				 * on close. Anchored absolutely so the translate doesn't fight
				 * the outer wrapper's flex sizing. `group` for descendants that
				 * opt into the hover-only scrollbar rule in `globals.css`. The
				 * `pt-10` offsets sidebar contents below the absolute AppHeader.
				 */}
				<SidebarFocusShell
					className={cn(
						'group sidepanel-text-scope bg-sidebar text-sidebar-foreground absolute inset-y-0 left-0 flex flex-col overflow-hidden pt-10',
						transformTransition,
						isExpanded ? 'translate-x-0' : '-translate-x-full'
					)}
				>
					{/*
					 * data-state on the inner div drives pointer-events so a
					 * (translated-out) sidebar can't capture clicks bleeding
					 * past it.
					 */}
					<div
						data-state={state}
						style={{ width: `${desktopWidth}px` }}
						className="flex h-full flex-col data-[state=collapsed]:pointer-events-none data-[state=expanded]:pointer-events-auto"
					>
						<SidebarHeader className="px-2 pt-0 pb-1 shrink-0">
							<NewSessionButton />
						</SidebarHeader>
						<SidebarContent>
							<NavChats />
						</SidebarContent>
						<SidebarFooterUser />
					</div>
				</SidebarFocusShell>

				{/*
				 * Resize handle removed (2026-05). The previous implementation
				 * felt rubbery under fast cursor moves and the visual divider
				 * confused users into trying to drag a panel that didn't yet
				 * have a usable handle. Width is fixed at the persisted value;
				 * a proper handle will return in a future rewrite.
				 */}
			</div>

			{/*
			 * Chat panel: flex-1 occupies whatever the outer sidebar wrapper
			 * doesn't, so as the wrapper transitions from W → 0 the chat panel
			 * widens in lockstep. Stacks above the sidebar via z-index so its
			 * left-edge shadow can paint over the sidebar surface.
			 * overflow:visible so the shadow escapes the panel container.
			 */}
			<div className="relative z-10 h-full min-w-0 flex-1" style={{ overflow: 'visible' }}>
				{/*
				 * pr-2 + pb-2 leave breathing room so the floating chat panel's
				 * right and bottom shadow layers actually paint. The left edge
				 * still butts up against the sidebar so the leftward shadow
				 * casts onto it.
				 */}
				<div className="h-full min-w-0 pt-10 pr-2 pb-2 pl-2">
					<ChatFocusShell>{children}</ChatFocusShell>
				</div>
			</div>
		</div>
	);
}

/**
 * Main application layout with resizable sidebar and content area.
 * Provides full-page structure with sidebar navigation and responsive behavior.
 * Wraps everything in focus-zone and chat-activity providers.
 */
export function AppShell({ children }: { children: React.ReactNode }): React.JSX.Element {
	const onboardingReadiness = useOnboardingReadiness();
	const e2eBypass = React.useSyncExternalStore(
		React.useCallback((cb: () => void) => {
			window.addEventListener('storage', cb);
			return () => window.removeEventListener('storage', cb);
		}, []),
		() => {
			try {
				return window.localStorage.getItem(E2E_SKIP_ONBOARDING_STORAGE_KEY) === '1';
			} catch {
				return false;
			}
		},
		() => false
	);

	const isAppReady =
		e2eBypass ||
		(!onboardingReadiness.isLoading &&
			!onboardingReadiness.isError &&
			onboardingReadiness.hasWorkspaceReady);
	const showReadinessError = !e2eBypass && onboardingReadiness.isError;

	React.useEffect(() => {
		if (e2eBypass) return;
		if (onboardingReadiness.isLoading) return;
		if (onboardingReadiness.isError) return;

		if (!onboardingReadiness.hasWorkspaceReady) {
			window.dispatchEvent(new Event(OPEN_ONBOARDING_FLOW_EVENT));
		}
	}, [
		e2eBypass,
		onboardingReadiness.isError,
		onboardingReadiness.hasWorkspaceReady,
		onboardingReadiness.isLoading,
	]);

	return (
		<SidebarProvider>
			<SidebarFocusProvider>
				<ChatActivityProvider>
					{/*
					 * Root chrome uses the sidebar surface color so the area
					 * around the floating chat panel — the AppHeader strip
					 * across the top, plus the pr-2/pb-2 gap framing the
					 * panel — visually reads as one continuous "outside"
					 * surface with the sidebar. The chat panel keeps its
					 * own bg-background, so the contrast stays.
					 */}
					<div className="relative flex h-svh min-h-0 w-full min-w-0 overflow-hidden bg-sidebar">
						{/*
						 * Personalization wizard fires on every fresh page load
						 * while the feature is WIP — see DESIGN.md →
						 * Components → personalization-modal. Dismissing closes
						 * for the session only; a browser refresh re-opens it.
						 */}
						<OnboardingFlow />
						{/*
						 * Workspace onboarding (Welcome → Create workspace →
						 * Local workspace) is event-driven only — opens when
						 * the user picks "Add Workspace..." in the workspace
						 * dropdown. Never opens automatically.
						 */}
						<OnboardingModal initialOpen={false} listenForOpenEvent />
						{showReadinessError ? (
							<AppShellReadinessError
								isRetrying={onboardingReadiness.isRefetching}
								onRetry={onboardingReadiness.refetch}
							/>
						) : null}
						{isAppReady ? (
							<>
								<ResizableSidebarContent>
									<SidebarInset className="h-full min-h-0 min-w-0">
										<div className="min-h-0 min-w-0 flex-1">{children}</div>
									</SidebarInset>
								</ResizableSidebarContent>
								<AppShellHeader />
							</>
						) : null}
					</div>
				</ChatActivityProvider>
			</SidebarFocusProvider>
		</SidebarProvider>
	);
}
