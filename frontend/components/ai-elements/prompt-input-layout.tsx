/**
 * Presentational prompt input primitives.
 *
 * @fileoverview Small wrappers around shared UI primitives used to compose prompt inputs.
 */

'use client';

import { DropdownMenuItem, DropdownPanelMenu } from '@octavian-tocan/react-dropdown';
import type { ChatStatus } from 'ai';
import { CornerDownLeftIcon, Loader2Icon, PlusIcon, SquareIcon, XIcon } from 'lucide-react';
import {
	Children,
	type ComponentProps,
	type HTMLAttributes,
	isValidElement,
	type ReactNode,
} from 'react';
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
	CommandSeparator,
} from '@/components/ui/command';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { InputGroupAddon, InputGroupButton } from '@/components/ui/input-group';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

/** Props for the prompt input body slot. */
type PromptInputBodyProps = HTMLAttributes<HTMLDivElement>;

/** Body slot for prompt input content. */
const _PromptInputBody = ({ className, ...props }: PromptInputBodyProps) => (
	<div className={cn('contents', className)} {...props} />
);

/** Props for the prompt input header slot. */
type PromptInputHeaderProps = Omit<ComponentProps<typeof InputGroupAddon>, 'align'>;

/** Header slot rendered at the block start of the input group. */
const _PromptInputHeader = ({ className, ...props }: PromptInputHeaderProps) => (
	<InputGroupAddon
		align="block-end"
		className={cn('order-first flex-wrap gap-1', className)}
		{...props}
	/>
);

/** Props for the prompt input footer slot. */
export type PromptInputFooterProps = Omit<ComponentProps<typeof InputGroupAddon>, 'align'>;

/** Footer slot rendered at the block end of the input group. */
export const PromptInputFooter = ({ className, ...props }: PromptInputFooterProps) => (
	<InputGroupAddon
		align="block-end"
		// Tighter vertical padding than the InputGroupAddon `block-end` default
		// (`pb-3`); the composer footer was reading visually too tall against
		// the textarea above it.
		className={cn('justify-between gap-1 py-1.5 pb-1.5', className)}
		{...props}
	/>
);

/** Props for tool groups in the prompt input footer. */
type PromptInputToolsProps = HTMLAttributes<HTMLDivElement>;

/** Horizontal tool group for prompt input actions. */
const _PromptInputTools = ({ className, ...props }: PromptInputToolsProps) => (
	<div className={cn('flex items-center gap-1', className)} {...props} />
);

/** Props for prompt input toolbar buttons. */
export type PromptInputButtonProps = ComponentProps<typeof InputGroupButton>;

/** Toolbar button with prompt-input defaults. */
export const PromptInputButton = ({
	variant = 'ghost',
	className,
	size,
	...props
}: PromptInputButtonProps) => {
	const newSize = size ?? (Children.count(props.children) > 1 ? 'sm' : 'icon-sm');

	return (
		<InputGroupButton
			className={cn(className)}
			size={newSize}
			type="button"
			variant={variant}
			{...props}
		/>
	);
};

/**
 * Internal slot sentinels used to identify which children of
 * `PromptInputActionMenu` represent the trigger vs. the content. This keeps
 * the existing compound API (`<PromptInputActionMenu><PromptInputActionMenuTrigger />
 * <PromptInputActionMenuContent>...</PromptInputActionMenuContent></PromptInputActionMenu>`)
 * intact while delegating to a single `DropdownPanelMenu` underneath.
 */
function PromptInputActionMenuTriggerSlot({
	children,
}: {
	children: ReactNode;
}): React.JSX.Element {
	return <>{children}</>;
}
PromptInputActionMenuTriggerSlot.displayName = 'PromptInputActionMenuTriggerSlot';

function PromptInputActionMenuContentSlot({
	children,
}: {
	children: ReactNode;
}): React.JSX.Element {
	return <>{children}</>;
}
PromptInputActionMenuContentSlot.displayName = 'PromptInputActionMenuContentSlot';

/** Props for the prompt input action dropdown menu. */
type PromptInputActionMenuProps = {
	children?: ReactNode;
	className?: string;
	onOpenChange?: (isOpen: boolean) => void;
};

/**
 * Dropdown menu root for prompt input actions.
 *
 * Scans children for the trigger and content slots and routes them into a
 * single `DropdownPanelMenu` so the compound API consumers expect keeps
 * working unchanged.
 */
const _PromptInputActionMenu = ({
	children,
	className,
	onOpenChange,
}: PromptInputActionMenuProps) => {
	let triggerNode: ReactNode = null;
	let contentNode: ReactNode = null;
	Children.forEach(children, (child) => {
		if (!isValidElement(child)) return;
		const type = child.type as { displayName?: string };
		if (type.displayName === 'PromptInputActionMenuTriggerSlot') {
			triggerNode = (child.props as { children?: ReactNode }).children ?? null;
		} else if (type.displayName === 'PromptInputActionMenuContentSlot') {
			contentNode = (child.props as { children?: ReactNode }).children ?? null;
		}
	});

	return (
		<DropdownPanelMenu
			asChild
			usePortal
			align="start"
			className={className}
			onOpenChange={onOpenChange}
			trigger={triggerNode ?? <PlusIcon className="size-4" />}
		>
			{contentNode}
		</DropdownPanelMenu>
	);
};

/** Props for the prompt input action menu trigger. */
type PromptInputActionMenuTriggerProps = PromptInputButtonProps;

/** Default trigger button for prompt input action menus. */
const _PromptInputActionMenuTrigger = ({
	className,
	children,
	...props
}: PromptInputActionMenuTriggerProps) => (
	<PromptInputActionMenuTriggerSlot>
		<PromptInputButton className={className} {...props}>
			{children ?? <PlusIcon className="size-4" />}
		</PromptInputButton>
	</PromptInputActionMenuTriggerSlot>
);

/** Props for the prompt input action menu content. */
type PromptInputActionMenuContentProps = {
	children?: ReactNode;
	className?: string;
};

/**
 * Menu content for prompt input actions. Children are forwarded into the
 * underlying `DropdownPanelMenu` panel via the slot sentinel pattern.
 */
const _PromptInputActionMenuContent = ({ children }: PromptInputActionMenuContentProps) => (
	<PromptInputActionMenuContentSlot>{children}</PromptInputActionMenuContentSlot>
);

/** Props for a prompt input action menu item. */
type PromptInputActionMenuItemProps = ComponentProps<typeof DropdownMenuItem>;

/** Menu item for prompt input actions. */
const _PromptInputActionMenuItem = ({ className, ...props }: PromptInputActionMenuItemProps) => (
	<DropdownMenuItem className={cn(className)} {...props} />
);

/** Props for the prompt input submit button. */
export type PromptInputSubmitProps = ComponentProps<typeof InputGroupButton> & {
	status?: ChatStatus;
};

/** Submit button that reflects chat status with a default icon. */
export const PromptInputSubmit = ({
	className,
	variant = 'default',
	size = 'icon-sm',
	status,
	children,
	...props
}: PromptInputSubmitProps) => {
	let Icon = <CornerDownLeftIcon className="size-4" />;

	if (status === 'submitted') {
		Icon = <Loader2Icon className="size-4 animate-spin" />;
	} else if (status === 'streaming') {
		Icon = <SquareIcon className="size-4" />;
	} else if (status === 'error') {
		Icon = <XIcon className="size-4" />;
	}

	return (
		<InputGroupButton
			aria-label="Submit"
			className={cn(className)}
			size={size}
			type="submit"
			variant={variant}
			{...props}
		>
			{children ?? Icon}
		</InputGroupButton>
	);
};

/** Props for prompt input select roots. */
type PromptInputSelectProps = ComponentProps<typeof Select>;

/** Select root for prompt input controls. */
const _PromptInputSelect = (props: PromptInputSelectProps) => <Select {...props} />;

/** Props for prompt input select triggers. */
type PromptInputSelectTriggerProps = ComponentProps<typeof SelectTrigger>;

/** Select trigger styled for prompt input toolbars. */
const _PromptInputSelectTrigger = ({ className, ...props }: PromptInputSelectTriggerProps) => (
	<SelectTrigger
		className={cn(
			'border-none bg-transparent font-medium text-muted-foreground shadow-none transition-colors',
			'hover:bg-accent hover:text-foreground aria-expanded:bg-accent aria-expanded:text-foreground',
			className
		)}
		{...props}
	/>
);

/** Props for prompt input select content. */
type PromptInputSelectContentProps = ComponentProps<typeof SelectContent>;

/** Select content for prompt input menus. */
const _PromptInputSelectContent = ({ className, ...props }: PromptInputSelectContentProps) => (
	<SelectContent className={cn(className)} {...props} />
);

/** Props for prompt input select items. */
type PromptInputSelectItemProps = ComponentProps<typeof SelectItem>;

/** Select item for prompt input menus. */
const _PromptInputSelectItem = ({ className, ...props }: PromptInputSelectItemProps) => (
	<SelectItem className={cn(className)} {...props} />
);

/** Props for prompt input select values. */
type PromptInputSelectValueProps = ComponentProps<typeof SelectValue>;

/** Select value display for prompt input controls. */
const _PromptInputSelectValue = ({ className, ...props }: PromptInputSelectValueProps) => (
	<SelectValue className={cn(className)} {...props} />
);

/** Props for prompt input hover cards. */
export type PromptInputHoverCardProps = ComponentProps<typeof HoverCard>;

/** Hover card root with immediate prompt input timings. */
export const PromptInputHoverCard = ({
	openDelay = 0,
	closeDelay = 0,
	...props
}: PromptInputHoverCardProps) => (
	<HoverCard closeDelay={closeDelay} openDelay={openDelay} {...props} />
);

/** Props for prompt input hover card triggers. */
export type PromptInputHoverCardTriggerProps = ComponentProps<typeof HoverCardTrigger>;

/** Hover card trigger for prompt input previews. */
export const PromptInputHoverCardTrigger = (props: PromptInputHoverCardTriggerProps) => (
	<HoverCardTrigger {...props} />
);

/** Props for prompt input hover card content. */
export type PromptInputHoverCardContentProps = ComponentProps<typeof HoverCardContent>;

/** Hover card content for prompt input previews. */
export const PromptInputHoverCardContent = ({
	align = 'start',
	...props
}: PromptInputHoverCardContentProps) => <HoverCardContent align={align} {...props} />;

/** Props for prompt input tab lists. */
type PromptInputTabsListProps = HTMLAttributes<HTMLDivElement>;

/** Container for prompt input tabs. */
const _PromptInputTabsList = ({ className, ...props }: PromptInputTabsListProps) => (
	<div className={cn(className)} {...props} />
);

/** Props for prompt input tab groups. */
type PromptInputTabProps = HTMLAttributes<HTMLDivElement>;

/** Tab group for prompt input menus. */
const _PromptInputTab = ({ className, ...props }: PromptInputTabProps) => (
	<div className={cn(className)} {...props} />
);

/** Props for prompt input tab labels. */
type PromptInputTabLabelProps = HTMLAttributes<HTMLHeadingElement>;

/** Label for a prompt input tab section. */
const _PromptInputTabLabel = ({
	children = 'Prompt input options',
	className,
	...props
}: PromptInputTabLabelProps) => (
	<h3 className={cn('mb-2 px-3 font-medium text-muted-foreground text-xs', className)} {...props}>
		{children}
	</h3>
);

/** Props for prompt input tab bodies. */
type PromptInputTabBodyProps = HTMLAttributes<HTMLDivElement>;

/** Body for a prompt input tab section. */
const _PromptInputTabBody = ({ className, ...props }: PromptInputTabBodyProps) => (
	<div className={cn('space-y-1', className)} {...props} />
);

/** Props for prompt input tab items. */
type PromptInputTabItemProps = HTMLAttributes<HTMLDivElement>;

/** Clickable row inside a prompt input tab section. */
const _PromptInputTabItem = ({ className, ...props }: PromptInputTabItemProps) => (
	<div
		className={cn('flex items-center gap-2 px-3 py-2 text-xs hover:bg-accent', className)}
		{...props}
	/>
);

/** Props for prompt input command roots. */
type PromptInputCommandProps = ComponentProps<typeof Command>;

/** Command root for prompt input search menus. */
const _PromptInputCommand = ({ className, ...props }: PromptInputCommandProps) => (
	<Command className={cn(className)} {...props} />
);

/** Props for prompt input command search fields. */
type PromptInputCommandInputProps = ComponentProps<typeof CommandInput>;

/** Command search field for prompt input menus. */
const _PromptInputCommandInput = ({ className, ...props }: PromptInputCommandInputProps) => (
	<CommandInput className={cn(className)} {...props} />
);

/** Props for prompt input command lists. */
type PromptInputCommandListProps = ComponentProps<typeof CommandList>;

/** Command list for prompt input menus. */
const _PromptInputCommandList = ({ className, ...props }: PromptInputCommandListProps) => (
	<CommandList className={cn(className)} {...props} />
);

/** Props for prompt input command empty states. */
type PromptInputCommandEmptyProps = ComponentProps<typeof CommandEmpty>;

/** Command empty state for prompt input menus. */
const _PromptInputCommandEmpty = ({ className, ...props }: PromptInputCommandEmptyProps) => (
	<CommandEmpty className={cn(className)} {...props} />
);

/** Props for prompt input command groups. */
type PromptInputCommandGroupProps = ComponentProps<typeof CommandGroup>;

/** Command group for prompt input menus. */
const _PromptInputCommandGroup = ({ className, ...props }: PromptInputCommandGroupProps) => (
	<CommandGroup className={cn(className)} {...props} />
);

/** Props for prompt input command items. */
type PromptInputCommandItemProps = ComponentProps<typeof CommandItem>;

/** Command item for prompt input menus. */
const _PromptInputCommandItem = ({ className, ...props }: PromptInputCommandItemProps) => (
	<CommandItem className={cn(className)} {...props} />
);

/** Props for prompt input command separators. */
type PromptInputCommandSeparatorProps = ComponentProps<typeof CommandSeparator>;

/** Command separator for prompt input menus. */
const _PromptInputCommandSeparator = ({
	className,
	...props
}: PromptInputCommandSeparatorProps) => <CommandSeparator className={cn(className)} {...props} />;
