/**
 * Sidebar component with resizable desktop layout and collapsible mobile sheet.
 *
 * Provides a flexible sidebar container with support for desktop resizing via drag handle,
 * persistent width storage, mobile sheet overlay, and keyboard shortcuts. Includes nested
 * header/content/footer sections and integrates with ResizablePanel for desktop layouts.
 *
 * @fileoverview Collapsible sidebar with desktop resize and mobile sheet support
 */

'use client';

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from '@hugeicons/core-free-icons';
import { HugeiconsIcon } from '@hugeicons/react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';
import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { TopBarButton } from '@/components/ui/top-bar-button';
import { useIsMobile } from '@/hooks/use-mobile';
import { SIDEBAR_STORAGE_KEYS } from '@/lib/storage-keys';
import { cn } from '@/lib/utils';

export const SIDEBAR_DEFAULT_WIDTH = 300;
export const SIDEBAR_MIN_WIDTH = 240;
export const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_WIDTH_MOBILE = '18rem';
const SIDEBAR_WIDTH_ICON = '3rem';
const SIDEBAR_KEYBOARD_SHORTCUT = 'b';

/**
 * Clamp sidebar width to valid range.
 * Ensures the width stays between SIDEBAR_MIN_WIDTH and SIDEBAR_MAX_WIDTH.
 */
function clampSidebarWidth(width: number): number {
	return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));
}

/**
 * Load the persisted desktop sidebar width from localStorage.
 * Returns SIDEBAR_DEFAULT_WIDTH if no valid stored value is found.
 */
function loadDesktopSidebarWidth(): number {
	if (typeof window === 'undefined') return SIDEBAR_DEFAULT_WIDTH;

	try {
		const storedWidth = window.localStorage.getItem(SIDEBAR_STORAGE_KEYS.width);
		if (!storedWidth) return SIDEBAR_DEFAULT_WIDTH;

		const parsedWidth = Number.parseInt(storedWidth, 10);
		if (!Number.isFinite(parsedWidth)) return SIDEBAR_DEFAULT_WIDTH;

		return clampSidebarWidth(parsedWidth);
	} catch {
		// Storage reads can throw in private browsing or blocked storage.
		return SIDEBAR_DEFAULT_WIDTH;
	}
}

function persistDesktopSidebarWidth(width: number): void {
	try {
		window.localStorage.setItem(SIDEBAR_STORAGE_KEYS.width, String(width));
	} catch {
		// Storage writes are best-effort only for this UI preference.
	}
}

type SidebarContextProps = {
	/** Current sidebar state ("expanded" or "collapsed"). */
	state: 'expanded' | 'collapsed';
	/** Set the sidebar state (desktop). */
	setState: (state: 'expanded' | 'collapsed') => void;
	/** Whether the mobile sidebar sheet is open. */
	openMobile: boolean;
	/** Set the mobile sidebar sheet open state. */
	setOpenMobile: (open: boolean) => void;
	/** Whether the current viewport is mobile. */
	isMobile: boolean;
	/** Toggle the sidebar (mobile or desktop depending on viewport). */
	toggleSidebar: () => void;
	/** Current desktop sidebar width in pixels. */
	desktopWidth: number;
	/** Whether the desktop sidebar width has been hydrated from local storage. */
	isDesktopWidthReady: boolean;
	/** Set the desktop sidebar width in pixels (clamped to valid range). */
	setDesktopWidth: (width: number) => void;
	/** Reset the desktop sidebar width to default. */
	resetDesktopWidth: () => void;
};

const SidebarContext = React.createContext<SidebarContextProps | null>(null);

function useSidebar() {
	const context = React.use(SidebarContext);
	if (!context) {
		throw new Error('useSidebar must be used within a SidebarProvider.');
	}

	return context;
}

function SidebarProvider({
	defaultOpen = true,
	open: openProp,
	onOpenChange: setOpenProp,
	className,
	style,
	children,
	...props
}: React.ComponentProps<'div'> & {
	defaultOpen?: boolean;
	open?: boolean;
	onOpenChange?: (open: boolean) => void;
}) {
	const isMobile = useIsMobile();
	const [openMobile, setOpenMobile] = React.useState(false);
	// SSR and the client's first render must match — never read localStorage in useState
	// initializers (server has no window; client would diverge). Hydrate width + collapsed
	// state from storage in useLayoutEffect before paint.
	const [desktopWidth, setDesktopWidthState] = React.useState(SIDEBAR_DEFAULT_WIDTH);
	const [isDesktopWidthReady, setIsDesktopWidthReady] = React.useState(false);

	const [_state, _setState] = React.useState<'expanded' | 'collapsed'>(() =>
		defaultOpen ? 'expanded' : 'collapsed'
	);

	React.useLayoutEffect(() => {
		setDesktopWidthState(loadDesktopSidebarWidth());
		setIsDesktopWidthReady(true);
		if (openProp !== undefined) {
			return;
		}
		try {
			const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEYS.state);
			if (stored === 'expanded' || stored === 'collapsed') {
				_setState(stored);
			}
		} catch {
			// Storage reads can throw in private browsing or blocked storage.
		}
	}, [openProp]);

	// Convert external boolean prop to internal state type
	const state = openProp !== undefined ? (openProp ? 'expanded' : 'collapsed') : _state;

	const setState = React.useCallback(
		(newState: 'expanded' | 'collapsed') => {
			if (setOpenProp) {
				setOpenProp(newState === 'expanded');
			} else {
				_setState(newState);
			}

			// Persist state to localStorage
			if (typeof window !== 'undefined') {
				try {
					window.localStorage.setItem(SIDEBAR_STORAGE_KEYS.state, newState);
				} catch {
					// Storage writes are best-effort only for this UI preference.
				}
			}
		},
		[setOpenProp]
	);

	// Helper to toggle the sidebar.
	const toggleSidebar = React.useCallback((): void => {
		if (isMobile) {
			setOpenMobile((open) => !open);
		} else {
			setState(state === 'expanded' ? 'collapsed' : 'expanded');
		}
	}, [isMobile, state, setState]);

	// Set the desktop sidebar width and clamp it to valid range.
	const setDesktopWidth = React.useCallback((width: number): void => {
		const nextWidth = clampSidebarWidth(width);
		setDesktopWidthState(nextWidth);
		persistDesktopSidebarWidth(nextWidth);
	}, []);

	// Reset the desktop sidebar width to default value.
	const resetDesktopWidth = React.useCallback((): void => {
		setDesktopWidthState(SIDEBAR_DEFAULT_WIDTH);
		persistDesktopSidebarWidth(SIDEBAR_DEFAULT_WIDTH);
	}, []);

	// Adds a keyboard shortcut to toggle the sidebar.
	React.useEffect(() => {
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
				event.preventDefault();
				toggleSidebar();
			}
		};

		window.addEventListener('keydown', handleKeyDown);
		return () => window.removeEventListener('keydown', handleKeyDown);
	}, [toggleSidebar]);

	const contextValue = React.useMemo<SidebarContextProps>(
		() => ({
			state,
			setState,
			isMobile,
			openMobile,
			setOpenMobile,
			toggleSidebar,
			desktopWidth,
			isDesktopWidthReady,
			setDesktopWidth,
			resetDesktopWidth,
		}),
		[
			state,
			setState,
			isMobile,
			openMobile,
			toggleSidebar,
			desktopWidth,
			isDesktopWidthReady,
			setDesktopWidth,
			resetDesktopWidth,
		]
	);

	return (
		<SidebarContext.Provider value={contextValue}>
			<div
				data-slot="sidebar-wrapper"
				style={
					{
						'--sidebar-width': `${desktopWidth}px`,
						'--sidebar-width-icon': SIDEBAR_WIDTH_ICON,
						...style,
					} as React.CSSProperties
				}
				className={cn(
					'group/sidebar-wrapper has-data-[variant=inset]:bg-sidebar flex min-h-svh w-full',
					className
				)}
				{...props}
			>
				{children}
			</div>
		</SidebarContext.Provider>
	);
}

function Sidebar({
	side = 'left',
	variant = 'sidebar',
	collapsible = 'offcanvas',
	className,
	children,
	dir,
	...props
}: React.ComponentProps<'div'> & {
	side?: 'left' | 'right';
	variant?: 'sidebar' | 'floating' | 'inset';
	collapsible?: 'offcanvas' | 'icon' | 'none';
}) {
	const { isMobile, state, openMobile, setOpenMobile } = useSidebar();

	if (collapsible === 'none') {
		return (
			<div
				data-slot="sidebar"
				className={cn(
					'bg-sidebar text-sidebar-foreground flex h-full w-(--sidebar-width) flex-col',
					className
				)}
				{...props}
			>
				{children}
			</div>
		);
	}

	if (isMobile) {
		return (
			<Sheet open={openMobile} onOpenChange={setOpenMobile} {...props}>
				<SheetContent
					dir={dir}
					data-sidebar="sidebar"
					data-slot="sidebar"
					data-mobile="true"
					className="bg-sidebar text-sidebar-foreground w-(--sidebar-width) p-0 [&>button]:hidden"
					style={
						{
							'--sidebar-width': SIDEBAR_WIDTH_MOBILE,
						} as React.CSSProperties
					}
					side={side}
				>
					<SheetHeader className="sr-only">
						<SheetTitle>Sidebar</SheetTitle>
						<SheetDescription>Displays the mobile sidebar.</SheetDescription>
					</SheetHeader>
					<div className="flex size-full flex-col">{children}</div>
				</SheetContent>
			</Sheet>
		);
	}

	return (
		<div
			className="group peer text-sidebar-foreground hidden md:block"
			data-state={state}
			data-collapsible={state === 'collapsed' ? collapsible : ''}
			data-variant={variant}
			data-side={side}
			data-slot="sidebar"
		>
			{/* This is what handles the sidebar gap on desktop */}
			<div
				data-slot="sidebar-gap"
				className={cn(
					'transition-[width] duration-200 ease-out relative w-(--sidebar-width) bg-transparent',
					'group-data-[collapsible=offcanvas]:w-0',
					'group-data-[side=right]:rotate-180',
					variant === 'floating' || variant === 'inset'
						? 'group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))]'
						: 'group-data-[collapsible=icon]:w-(--sidebar-width-icon)'
				)}
			/>
			<div
				data-slot="sidebar-container"
				data-side={side}
				className={cn(
					'fixed inset-y-0 z-10 hidden h-svh w-(--sidebar-width) transition-[left,right,width] duration-200 ease-out data-[side=left]:left-0 data-[side=left]:group-data-[collapsible=offcanvas]:left-[calc(var(--sidebar-width)*-1)] data-[side=right]:right-0 data-[side=right]:group-data-[collapsible=offcanvas]:right-[calc(var(--sidebar-width)*-1)] md:flex',
					// Adjust the padding for floating and inset variants.
					variant === 'floating' || variant === 'inset'
						? 'p-2 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4))+2px)]'
						: 'group-data-[collapsible=icon]:w-(--sidebar-width-icon) group-data-[side=left]:border-r group-data-[side=right]:border-l',
					className
				)}
				{...props}
			>
				<div
					data-sidebar="sidebar"
					data-slot="sidebar-inner"
					className="bg-sidebar group-data-[variant=floating]:ring-sidebar-border group-data-[variant=floating]:rounded-lg group-data-[variant=floating]:shadow-sm group-data-[variant=floating]:ring-1 flex size-full flex-col"
				>
					{children}
				</div>
			</div>
		</div>
	);
}

function SidebarTrigger({
	className,
	onClick,
	...props
}: React.ComponentProps<typeof TopBarButton>) {
	const { isMobile, openMobile, state, toggleSidebar } = useSidebar();
	const willCloseSidebar = isMobile ? openMobile : state === 'expanded';
	const SidebarActionIcon = willCloseSidebar ? PanelLeftCloseIcon : PanelLeftOpenIcon;

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<TopBarButton
					data-sidebar="trigger"
					data-slot="sidebar-trigger"
					aria-label="Toggle Sidebar"
					className={cn('[&_svg]:size-4', className)}
					onClick={(event) => {
						onClick?.(event);
						toggleSidebar();
					}}
					{...props}
				>
					<HugeiconsIcon
						icon={SidebarActionIcon}
						size={16}
						strokeWidth={1.7}
						aria-hidden="true"
					/>
					<span className="sr-only">Toggle Sidebar</span>
				</TopBarButton>
			</TooltipTrigger>
			<TooltipContent side="right">Toggle Sidebar</TooltipContent>
		</Tooltip>
	);
}

function SidebarInset({ className, ...props }: React.ComponentProps<'main'>) {
	return (
		<main
			data-slot="sidebar-inset"
			className={cn(
				'bg-background md:peer-data-[variant=inset]:m-2 md:peer-data-[variant=inset]:ml-0 md:peer-data-[variant=inset]:rounded-xl md:peer-data-[variant=inset]:shadow-sm md:peer-data-[variant=inset]:peer-data-[state=collapsed]:ml-2 relative flex w-full flex-1 flex-col',
				className
			)}
			{...props}
		/>
	);
}

function SidebarInput({ className, ...props }: React.ComponentProps<typeof Input>) {
	return (
		<Input
			data-slot="sidebar-input"
			data-sidebar="input"
			className={cn('bg-background h-8 w-full shadow-none', className)}
			{...props}
		/>
	);
}

function SidebarHeader({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-header"
			data-sidebar="header"
			className={cn('gap-2 p-2 [--radius:var(--radius-xl)] flex flex-col', className)}
			{...props}
		/>
	);
}

function SidebarFooter({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-footer"
			data-sidebar="footer"
			className={cn('gap-2 p-2 flex flex-col', className)}
			{...props}
		/>
	);
}

function SidebarSeparator({ className, ...props }: React.ComponentProps<typeof Separator>) {
	return (
		<Separator
			data-slot="sidebar-separator"
			data-sidebar="separator"
			className={cn('bg-sidebar-border mx-2 w-auto', className)}
			{...props}
		/>
	);
}

function SidebarContent({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-content"
			data-sidebar="content"
			className={cn(
				'no-scrollbar gap-2 [--radius:var(--radius-xl)] flex min-h-0 flex-1 flex-col overflow-auto group-data-[collapsible=icon]:overflow-hidden',
				className
			)}
			{...props}
		/>
	);
}

function SidebarGroup({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-group"
			data-sidebar="group"
			className={cn('relative flex w-full min-w-0 flex-col px-2 pt-1 pb-1', className)}
			{...props}
		/>
	);
}

function SidebarGroupLabel({
	className,
	asChild = false,
	...props
}: React.ComponentProps<'div'> & { asChild?: boolean }) {
	const Comp = asChild ? Slot.Root : 'div';

	return (
		<Comp
			data-slot="sidebar-group-label"
			data-sidebar="group-label"
			className={cn(
				'text-sidebar-foreground/45 h-5 px-2.5 pb-[5px] pt-[3px] text-[10px] font-medium uppercase tracking-[0.16em] transition-[margin,opacity] duration-200 ease-out group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0 [&>svg]:size-3.5 flex shrink-0 items-center outline-hidden [&>svg]:shrink-0',
				className
			)}
			{...props}
		/>
	);
}

function SidebarGroupAction({
	className,
	asChild = false,
	...props
}: React.ComponentProps<'button'> & { asChild?: boolean }) {
	const Comp = asChild ? Slot.Root : 'button';

	return (
		<Comp
			data-slot="sidebar-group-action"
			data-sidebar="group-action"
			className={cn(
				'text-sidebar-foreground ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground absolute top-3.5 right-3 w-5 rounded-md p-0 focus-visible:ring-2 [&>svg]:size-4 flex aspect-square items-center justify-center outline-hidden transition-transform group-data-[collapsible=icon]:hidden after:absolute after:-inset-2 md:after:hidden [&>svg]:shrink-0',
				className
			)}
			{...props}
		/>
	);
}

function SidebarGroupContent({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-group-content"
			data-sidebar="group-content"
			className={cn('text-sm w-full', className)}
			{...props}
		/>
	);
}

function SidebarMenu({ className, ...props }: React.ComponentProps<'ul'>) {
	return (
		<ul
			data-slot="sidebar-menu"
			data-sidebar="menu"
			className={cn('gap-1 flex w-full min-w-0 flex-col', className)}
			{...props}
		/>
	);
}

function SidebarMenuItem({ className, ...props }: React.ComponentProps<'li'>) {
	return (
		<li
			data-slot="sidebar-menu-item"
			data-sidebar="menu-item"
			className={cn('group/menu-item relative', className)}
			{...props}
		/>
	);
}

const sidebarMenuButtonVariants = cva(
	'ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground data-active:bg-sidebar-accent data-active:text-sidebar-accent-foreground data-open:hover:bg-sidebar-accent data-open:hover:text-sidebar-accent-foreground gap-2 rounded-lg px-3 py-2 text-left text-sm transition-[width,height,padding] group-has-data-[sidebar=menu-action]/menu-item:pr-8 group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:p-2! focus-visible:ring-2 data-active:font-medium peer/menu-button flex w-full cursor-pointer items-center overflow-hidden outline-hidden group/menu-button disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&>span:last-child]:truncate [&_svg]:size-4 [&_svg]:shrink-0',
	{
		variants: {
			variant: {
				default: 'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
				outline:
					'bg-background hover:bg-sidebar-accent hover:text-sidebar-accent-foreground shadow-[0_0_0_1px_hsl(var(--sidebar-border))] hover:shadow-[0_0_0_1px_hsl(var(--sidebar-accent))]',
			},
			size: {
				default: 'h-9 text-sm',
				sm: 'h-8 text-xs',
				lg: 'h-14 px-3 text-sm group-data-[collapsible=icon]:p-0!',
			},
		},
		defaultVariants: {
			variant: 'default',
			size: 'default',
		},
	}
);

function SidebarMenuButton({
	asChild = false,
	isActive = false,
	variant = 'default',
	size = 'default',
	tooltip,
	className,
	...props
}: React.ComponentProps<'button'> & {
	asChild?: boolean;
	isActive?: boolean;
	tooltip?: string | React.ComponentProps<typeof TooltipContent>;
} & VariantProps<typeof sidebarMenuButtonVariants>) {
	const Comp = asChild ? Slot.Root : 'button';
	const { isMobile, state } = useSidebar();

	const button = (
		<Comp
			data-slot="sidebar-menu-button"
			data-sidebar="menu-button"
			data-size={size}
			data-active={isActive}
			className={cn(sidebarMenuButtonVariants({ variant, size }), className)}
			{...props}
		/>
	);

	if (!tooltip) {
		return button;
	}

	if (typeof tooltip === 'string') {
		tooltip = {
			children: tooltip,
		};
	}

	return (
		<Tooltip>
			<TooltipTrigger asChild>{button}</TooltipTrigger>
			<TooltipContent
				side="right"
				align="center"
				hidden={state !== 'collapsed' || isMobile}
				{...tooltip}
			/>
		</Tooltip>
	);
}

function SidebarMenuAction({
	className,
	asChild = false,
	showOnHover = false,
	...props
}: React.ComponentProps<'button'> & {
	asChild?: boolean;
	showOnHover?: boolean;
}) {
	const Comp = asChild ? Slot.Root : 'button';

	return (
		<Comp
			data-slot="sidebar-menu-action"
			data-sidebar="menu-action"
			className={cn(
				'text-sidebar-foreground ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground peer-hover/menu-button:text-sidebar-accent-foreground absolute top-1.5 right-1 aspect-square w-5 rounded-md p-0 peer-data-[size=default]/menu-button:top-2 peer-data-[size=lg]/menu-button:top-2.5 peer-data-[size=sm]/menu-button:top-1 focus-visible:ring-2 [&>svg]:size-4 flex items-center justify-center outline-hidden transition-transform group-data-[collapsible=icon]:hidden after:absolute after:-inset-2 md:after:hidden [&>svg]:shrink-0',
				showOnHover &&
					'peer-data-active/menu-button:text-sidebar-accent-foreground group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 aria-expanded:opacity-100 md:opacity-0',
				className
			)}
			{...props}
		/>
	);
}

function SidebarMenuBadge({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			data-slot="sidebar-menu-badge"
			data-sidebar="menu-badge"
			className={cn(
				'text-sidebar-foreground peer-hover/menu-button:text-sidebar-accent-foreground peer-data-active/menu-button:text-sidebar-accent-foreground pointer-events-none absolute right-1 h-5 min-w-5 rounded-md px-1 text-xs font-medium peer-data-[size=default]/menu-button:top-1.5 peer-data-[size=lg]/menu-button:top-2.5 peer-data-[size=sm]/menu-button:top-1 flex items-center justify-center tabular-nums select-none group-data-[collapsible=icon]:hidden',
				className
			)}
			{...props}
		/>
	);
}

function SidebarMenuSkeleton({
	className,
	showIcon = false,
	...props
}: React.ComponentProps<'div'> & {
	showIcon?: boolean;
}) {
	const [width] = React.useState(() => {
		return `${Math.floor(Math.random() * 40) + 50}%`;
	});

	return (
		<div
			data-slot="sidebar-menu-skeleton"
			data-sidebar="menu-skeleton"
			className={cn('h-8 gap-2 rounded-md px-2 flex animate-pulse items-center', className)}
			{...props}
		>
			{showIcon && (
				<Skeleton className="size-4 rounded-md" data-sidebar="menu-skeleton-icon" />
			)}
			<Skeleton
				className="h-4 flex-1 rounded-md"
				data-sidebar="menu-skeleton-text"
				style={{ maxWidth: width }}
			/>
		</div>
	);
}

function SidebarMenuSub({ className, ...props }: React.ComponentProps<'ul'>) {
	return (
		<ul
			data-slot="sidebar-menu-sub"
			data-sidebar="menu-sub"
			className={cn(
				'border-sidebar-border mx-3.5 translate-x-px gap-1 border-l px-2.5 py-0.5 group-data-[collapsible=icon]:hidden flex min-w-0 flex-col',
				className
			)}
			{...props}
		/>
	);
}

function SidebarMenuSubItem({ className, ...props }: React.ComponentProps<'li'>) {
	return (
		<li
			data-slot="sidebar-menu-sub-item"
			data-sidebar="menu-sub-item"
			className={cn('group/menu-sub-item relative', className)}
			{...props}
		/>
	);
}

function SidebarMenuSubButton({
	asChild = false,
	size = 'md',
	isActive = false,
	className,
	...props
}: React.ComponentProps<'a'> & {
	asChild?: boolean;
	size?: 'sm' | 'md';
	isActive?: boolean;
}) {
	const Comp = asChild ? Slot.Root : 'a';

	return (
		<Comp
			data-slot="sidebar-menu-sub-button"
			data-sidebar="menu-sub-button"
			data-size={size}
			data-active={isActive}
			className={cn(
				'text-sidebar-foreground ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground [&>svg]:text-sidebar-accent-foreground data-active:bg-sidebar-accent data-active:text-sidebar-accent-foreground h-7 gap-2 rounded-md px-2 focus-visible:ring-2 data-[size=md]:text-sm data-[size=sm]:text-xs [&>svg]:size-4 flex min-w-0 -translate-x-px items-center overflow-hidden outline-hidden group-data-[collapsible=icon]:hidden disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&>span:last-child]:truncate [&>svg]:shrink-0',
				className
			)}
			{...props}
		/>
	);
}

export {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupAction,
	SidebarGroupContent,
	SidebarGroupLabel,
	SidebarHeader,
	SidebarInput,
	SidebarInset,
	SidebarMenu,
	SidebarMenuAction,
	SidebarMenuBadge,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarMenuSkeleton,
	SidebarMenuSub,
	SidebarMenuSubButton,
	SidebarMenuSubItem,
	SidebarProvider,
	SidebarSeparator,
	SidebarTrigger,
	useSidebar,
};
