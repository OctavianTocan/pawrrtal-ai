'use client';

import type * as React from 'react';
import { useState } from 'react';
import { MoreHorizontal } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import {
	DropdownPanelMenu,
	DropdownContextMenu,
	DropdownContextMenuTrigger,
	DropdownContextMenuContent,
} from '@octavian-tocan/react-dropdown';
import { DropdownMenuProvider, ContextMenuProvider } from '@/components/ui/menu-context';
import { sidebarNavRowSurfaceClassName } from '@/components/ui/sidebar-nav-row-surface';
import { cn } from '@/lib/utils';

export interface EntityRowProps {
	icon?: React.ReactNode;
	title: React.ReactNode;
	titleClassName?: string;
	titleTrailing?: React.ReactNode;
	badges?: React.ReactNode;
	trailing?: React.ReactNode;
	children?: React.ReactNode;
	state?: EntityRowState;
	className?: string;
	separatorClassName?: string;
	onClick?: () => void;
	/** Menu content rendered in both dropdown and context menu via providers */
	menuContent?: React.ReactNode;
	/** Override context menu content (defaults to menuContent) */
	contextMenuContent?: React.ReactNode;
	/** Mouse down handler for modifier key detection */
	onMouseDown?: (e: React.MouseEvent) => void;
	/** Fires on drag start — the row sets up the dataTransfer payload here. */
	onDragStart?: (e: React.DragEvent<HTMLDivElement>) => void;
	/** Fires on drag end — used to clean up local "is dragging" state. */
	onDragEnd?: (e: React.DragEvent<HTMLDivElement>) => void;
	/** Props spread onto the row's clickable div (role="button") element */
	buttonProps?: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> };
	/** Data attributes on outer wrapper */
	dataAttributes?: Record<string, string | undefined>;
	/** Hide the "..." more button */
	hideMoreButton?: boolean;
}

export interface EntityRowState {
	isDraggable?: boolean;
	isInMultiSelect?: boolean;
	isSelected?: boolean;
	showSeparator?: boolean;
}

/**
 * Generic interactive row used throughout the sidebar.
 *
 * Supports an icon, title, trailing content, badges, dropdown menu,
 * context menu, multi-select, and separator. Both the `titleTrailing`
 * and default layout variants provide a "..." overflow menu that
 * appears on hover and is keyboard-accessible.
 */
export function EntityRow({
	icon,
	title,
	titleClassName,
	titleTrailing,
	badges,
	trailing,
	children,
	state,
	className,
	separatorClassName = 'pl-[38px] pr-4',
	onClick,
	menuContent,
	contextMenuContent,
	onMouseDown,
	onDragStart,
	onDragEnd,
	buttonProps,
	dataAttributes,
	hideMoreButton = false,
}: EntityRowProps): React.JSX.Element {
	const {
		isDraggable = false,
		isInMultiSelect = false,
		isSelected = false,
		showSeparator = false,
	} = state ?? {};
	const [menuOpen, setMenuOpen] = useState(false);
	const [contextMenuOpen, setContextMenuOpen] = useState(false);
	const resolvedContextMenu = contextMenuContent ?? menuContent;

	const InnerContent = (
		<div className="relative group/row select-none pl-2 mr-2">
			{(isSelected || isInMultiSelect) && (
				<div className="absolute left-0 inset-y-0 w-[2px] bg-accent" />
			)}
			{/* Uses div+role instead of <button> to avoid nested-button HTML violation
			    when the dropdown trigger renders its own <button> inside. */}
			<div
				role="button"
				tabIndex={0}
				{...buttonProps}
				draggable={isDraggable}
				onClick={onClick}
				onDragEnd={onDragEnd}
				onDragStart={onDragStart}
				onMouseDown={onMouseDown}
				onKeyDown={(e) => {
					// Activate on Enter/Space like a native button
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						onClick?.();
					}
				}}
				className={cn(
					sidebarNavRowSurfaceClassName({
						selected: isSelected || isInMultiSelect,
						density: 'comfortable',
						align: 'start',
					}),
					'cursor-pointer',
					buttonProps?.className
				)}
			>
				<div className="flex flex-col gap-1.5 min-w-0 flex-1">
					{titleTrailing ? (
						<div className="flex items-center gap-[10px] w-full min-w-0">
							{icon && (
								<div className="shrink-0 flex items-center gap-[10px] [&>*]:w-3 [&>*]:h-3">
									{icon}
								</div>
							)}
							<div
								className={cn('font-sans truncate min-w-0 flex-1', titleClassName)}
							>
								{title}
							</div>
							<div className="shrink-0 ml-auto relative -mr-1">
								<span
									className={cn(
										menuOpen || contextMenuOpen
											? 'invisible'
											: 'group-hover/row:invisible'
									)}
								>
									{titleTrailing}
								</span>
								{menuContent && !hideMoreButton && (
									<div
										className={cn(
											'absolute inset-0 flex items-center justify-end overflow-visible',
											menuOpen || contextMenuOpen
												? 'opacity-100'
												: 'opacity-0 pointer-events-none group-hover/row:opacity-100 group-hover/row:pointer-events-auto'
										)}
									>
										<DropdownPanelMenu
											asChild
											usePortal
											contentClassName="popover-styled p-1 min-w-44"
											onOpenChange={setMenuOpen}
											trigger={
												<button
													type="button"
													className="p-1 rounded-[6px] hover:bg-foreground/10 data-[state=open]:bg-foreground/10 cursor-pointer"
													onPointerDown={(e) => e.stopPropagation()}
													onClick={(e) => e.stopPropagation()}
													aria-label="More actions"
												>
													<MoreHorizontal className="size-3.5 text-muted-foreground" />
												</button>
											}
										>
											<DropdownMenuProvider>
												{menuContent}
											</DropdownMenuProvider>
										</DropdownPanelMenu>
									</div>
								)}
							</div>
						</div>
					) : (
						<div
							className={cn(
								'flex items-center gap-[10px] w-full min-w-0',
								icon && 'pr-6'
							)}
						>
							{icon && (
								<div className="shrink-0 flex items-center gap-[10px] [&>*]:w-3 [&>*]:h-3">
									{icon}
								</div>
							)}
							<div
								className={cn(
									'font-medium font-sans line-clamp-2 min-w-0 -mb-[2px]',
									titleClassName
								)}
							>
								{title}
							</div>
						</div>
					)}
					{(badges || trailing) && (
						<div className="flex items-center gap-[10px] text-xs text-foreground/70 w-full -mb-[2px] min-w-0">
							{icon && (
								<div
									className="shrink-0 flex items-center gap-[10px] [&>*]:w-3 [&>*]:h-3 invisible"
									aria-hidden="true"
								>
									{icon}
								</div>
							)}
							{badges && (
								<div
									className="flex-1 flex items-center gap-1 min-w-0 overflow-x-auto scrollbar-hide"
									style={{
										maskImage:
											'linear-gradient(to right, black calc(100% - 16px), transparent 100%)',
										WebkitMaskImage:
											'linear-gradient(to right, black calc(100% - 16px), transparent 100%)',
									}}
								>
									{badges}
								</div>
							)}
							{trailing && (
								<div className="shrink-0 flex items-center gap-1 ml-auto">
									{trailing}
								</div>
							)}
						</div>
					)}
				</div>
			</div>
			{children}
			{menuContent && !hideMoreButton && !titleTrailing && (
				<div
					className={cn(
						'absolute right-2 top-2 transition-opacity z-10',
						menuOpen || contextMenuOpen
							? 'opacity-100'
							: 'opacity-0 pointer-events-none group-hover/row:opacity-100 group-hover/row:pointer-events-auto'
					)}
				>
					<div className="flex items-center rounded-[8px] overflow-hidden border border-transparent hover:border-border/50">
						<DropdownPanelMenu
							asChild
							usePortal
							contentClassName="popover-styled p-1 min-w-44"
							onOpenChange={setMenuOpen}
							trigger={
								<button
									type="button"
									className="p-1.5 hover:bg-foreground/10 data-[state=open]:bg-foreground/10 cursor-pointer"
									onPointerDown={(e) => e.stopPropagation()}
									onClick={(e) => e.stopPropagation()}
									aria-label="More actions"
								>
									<MoreHorizontal className="size-4 text-muted-foreground" />
								</button>
							}
						>
							<DropdownMenuProvider>{menuContent}</DropdownMenuProvider>
						</DropdownPanelMenu>
					</div>
				</div>
			)}
		</div>
	);

	return (
		<div className={className} data-selected={isSelected || undefined} {...dataAttributes}>
			{showSeparator && (
				<div className={separatorClassName}>
					<Separator />
				</div>
			)}
			{resolvedContextMenu ? (
				<DropdownContextMenu onOpenChange={setContextMenuOpen}>
					<DropdownContextMenuTrigger asChild>{InnerContent}</DropdownContextMenuTrigger>
					<DropdownContextMenuContent>
						<ContextMenuProvider>{resolvedContextMenu}</ContextMenuProvider>
					</DropdownContextMenuContent>
				</DropdownContextMenu>
			) : (
				InnerContent
			)}
		</div>
	);
}
