/**
 * Action to open referenced content in the chat surface.
 *
 * @fileoverview AI Elements — `open-in-chat`.
 *
 * Compound component built on top of `DropdownPanelMenu`. The classic Radix
 * compound API (Root + Trigger + Content) is preserved by collecting the
 * trigger and content children at the OpenIn level, then routing them into a
 * single `DropdownPanelMenu` (which exposes a `trigger` prop + JSX children
 * for the content).
 */

'use client';

import { DropdownMenuItem, DropdownPanelMenu } from '@octavian-tocan/react-dropdown';
import { ChevronDownIcon, ExternalLinkIcon, MessageCircleIcon } from 'lucide-react';
import {
	Children,
	type ComponentProps,
	createContext,
	isValidElement,
	type ReactNode,
	use,
	useMemo,
} from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const DEFAULT_OPEN_IN_TRIGGER = (
	<Button type="button" variant="outline">
		Open in chat
		<ChevronDownIcon className="size-4" />
	</Button>
);

const providers = {
	github: {
		title: 'Open in GitHub',
		createUrl: (url: string) => url,
		icon: (
			<svg fill="currentColor" role="img" viewBox="0 0 24 24">
				<title>GitHub</title>
				<path d="M12 .297c-6.63 0-12 5.37-12 12 0 5 3.44 9.8 8.21 11.38.6.11.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.34.724-4.04-1.61-4.04-1.61C4.42 18.07 3.63 17.7 3.63 17.7c-1.09-.744.08-.729.08-.729 1.21.084 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1 3.998.11-.776.42-1.76-1-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.46-2.38 1.24-3.22-.135-.303-.54-1.52.105-3.18 0 0 1-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.2.01 2.4.14 3 .405 2.28-1.55 3.29-1.23 3.29-1.23.64 1.65.24 2.87.12 3.18.765.84 1.23 1.91 1.23 3.22 0 4.61-2.81 5.63-5.47 5.92.42.36.81 1.81 2.22 0 1.61-.015 2-.015 3.29 0 .315.21.69.83.57C20.57 22.09 24 17.59 24 12c0-6.63-5.37-12-12-12" />
			</svg>
		),
	},
	scira: {
		title: 'Open in Scira',
		createUrl: (q: string) =>
			`https://scira.ai/?${new URLSearchParams({
				q,
			})}`,
		icon: (
			<svg
				fill="none"
				height="934"
				viewBox="0 0 910 934"
				width="910"
				xmlns="http://www.w3.org/2000/svg"
			>
				<title>Scira AI</title>
				<path
					d="M647.66 197.78C569.13 189.05 525.5 145.42 516.77 66.88C508.05 145.42 464.42 189.05 385.88 197.78C464.42 206 508.05 250.13 516.77 328.67C525.5 250.13 569.13 206 647.66 197.78Z"
					fill="currentColor"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="8"
				/>
				<path
					d="M516.77 304.22C510 275.49 498.21 252.09 480.33 234.21C462.46 216.34 439.06 204.25 410.33 197.78C439.06 191.3 462.46 179.21 480.33 161.34C498.21 143.46 510 120.06 516.77 91.33C523.25 120.06 535.34 143.46 553.21 161.34C571.09 179.21 594.49 191.3 623.22 197.78C594.49 204.25 571.09 216.34 553.21 234.21C535.34 252.09 523.25 275.49 516.77 304.22Z"
					fill="currentColor"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="8"
				/>
				<path
					d="M857.5 508.12C763.26 497.64 710 445.29 700.43 351.05C689.96 445.29 637.61 497.64 543.36 508.12C637.61 518.59 689.96 570.94 700.43 665.18C710 570.94 763.26 518.59 857.5 508.12Z"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="20"
				/>
				<path
					d="M700.43 615.96C691.85 589.05 678.58 566.36 660.38 548.16C642.19 529.97 619 516.7 592.59 508.12C619 499.53 642.19 486.26 660.38 468.07C678.58 449.87 691.85 427.18 700.43 400.27C709.01 427.18 722.29 449.87 740.48 468.07C758.67 486.26 781.37 499.53 808.27 508.12C781.37 516.7 758.67 529.97 740.48 548.16C722.29 566.36 709.01 589.05 700.43 615.96Z"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="20"
				/>
				<path
					d="M889.95 121.24C831.05 114.69 798.33 81.97 791.78 23.07C785.24 81.97 752.51 114.69 693.61 121.24C752.51 127.78 785.24 160 791.78 219C798.33 160 831.05 127.78 889.95 121.24Z"
					fill="currentColor"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="8"
				/>
				<path
					d="M791.78 196.79C786 176.94 777.87 160.57 765.16 147.86C752.45 135.15 736.08 126.32 716.23 121.24C736.08 116.15 752.45 107.32 765.16 94.62C777.87 81.91 786 65.54 791.78 45.68C796.87 65.54 805 81.91 818 94.62C831.11 107.32 847.48 116.15 867.34 121.24C847.48 126.32 831.11 135.15 818 147.86C805.69 160.57 796.87 176.94 791.78 196.79Z"
					fill="currentColor"
					stroke="currentColor"
					strokeLinejoin="round"
					strokeWidth="8"
				/>
				<path
					d="M760.63 764.34C720.72 814.62 669.84 855.1 611.87 882.69C553.91 910.28 490 924.25 426.21 923.53C362.02 922.81 298.85 907.42 241.52 878.53C184.19 849.64 134.23 808.03 95.45 756.86C56.68 705.7 30.12 646.35 17.81 583.34C5 520.34 7.76 455.35 24.43 393.36C41.09 331.36 71.71 274 113.95 225.66C156.18 177.31 208.92 139.27 268.12 114.44"
					stroke="currentColor"
					strokeLinecap="round"
					strokeLinejoin="round"
					strokeWidth="30"
				/>
			</svg>
		),
	},
	chatgpt: {
		title: 'Open in ChatGPT',
		createUrl: (prompt: string) =>
			`https://chatgpt.com/?${new URLSearchParams({
				hints: 'search',
				prompt,
			})}`,
		icon: (
			<svg
				fill="currentColor"
				role="img"
				viewBox="0 0 24 24"
				xmlns="http://www.w3.org/2000/svg"
			>
				<title>OpenAI</title>
				<path d="M22.28 9.82a5.98 5.98 0 0 0-.5157-4.91 6.05 6.05 0 0 0-6.51-2.9A6.07 6.07 0 0 0 4.98 4.18a5.98 5.98 0 0 0-4 2.9 6.05 6.05 0 0 0 .7427 7 5.98 5.98 0 0 0 .511 4.91 6.05 6.05 0 0 0 6.51 2A5.98 5.98 0 0 0 13.26 24a6.06 6.06 0 0 0 5.77-4.21 5.99 5.99 0 0 0 4-2 6.06 6.06 0 0 0-.7475-7.07zm-9.02 12.61a4.48 4.48 0 0 1-2.88-1.04l.1419-.0804 4.78-2.76a.7948.79 0 0 0 .3927-.6813v-6.74l2.02 1.17a.71.07 0 0 1 .38.05v5.58a4 4 0 0 1-4.49 4.49zm-9.66-4.13a4.47 4.47 0 0 1-.5346-3.01l.142.09 4.78 2.76a.7712.77 0 0 0 .7806 0l5.84-3.37v2.33a.804.08 0 0 1-.332.06L9.74 19.95a4 4 0 0 1-6.14-1.65zM2.34 7a4.49 4.49 0 0 1 2.37-1.97V11.6a.7664.77 0 0 0 .3879.68l5.81 3.35-2.02 1.17a.757.08 0 0 1-.071 0l-4.83-2.79A4 4 0 0 1 2.34 7.87zm16 3.86L13 8.36 15.12 7.2a.757.08 0 0 1 .071 0l4.83 2.79a4.49 4.49 0 0 1-.6765 8v-5.68a.79.79 0 0 0-.407-.667zm2.01-3.02l-.142-.0852-4.77-2.78a.7759.78 0 0 0-.7854 0L9.41 9.23V6a.662.07 0 0 1 .0284-.0615l4.83-2.79a4 4 0 0 1 6.68 4.66zM8.31 12.86l-2.02-1.16a.804.08 0 0 1-.038-.0567V6.07a4 4 0 0 1 7.38-3.45l-.142.08L8 5.46a.7948.79 0 0 0-.3927.68zm1-2.37l2-1 2.61 1v3l-2 1-2.61-1Z" />
			</svg>
		),
	},
	claude: {
		title: 'Open in Claude',
		createUrl: (q: string) =>
			`https://claude.ai/new?${new URLSearchParams({
				q,
			})}`,
		icon: (
			<svg
				fill="currentColor"
				role="img"
				viewBox="0 0 12 12"
				xmlns="http://www.w3.org/2000/svg"
			>
				<title>Claude</title>
				<path
					clipRule="evenodd"
					d="M2.35 7.98L4.71 6.65L4.75 6.54L4.71 6.47H4.6L4.21 6.45L2.86 6.41L1.69 6.37L0.55 6L0.27 6.24L0 5.89L0.03 5.72L0.27 5.56L0.61 5.59L1.37 5.64L2.51 5.72L3.34 5.76L4.56 5.89H4.75L4.78 5.81L4.71 5.76L4.66 5.72L3.48 4.92L2.21 4.07L1.54 3.59L1.18 3.34L1 3.11L0.92 2.61L1.25 2.25L1.69 2.28L1 2.31L2.25 2.65L3 3.39L4.44 4L4.63 4.46L4 4.41L4.71 4.37L4.63 4.23L3.95 3.01L3.23 1.76L2 1.25L2.82 0.94C2.79 0.82 2.77 0 2.77 0.57L3.14 0.07L3.35 0L3.85 0.07L4.06 0.25L4.37 0.96L4.87 2.07L5.64 3.59L5.87 4.03L5.99 4.45L6.04 4.58H6.12V4L6.18 3.65L6 2L6.42 1.26L6.46 0.88L6.64 0.42L7.02 0.18L7.31 0.32L7.55 0.66L7.52 0.88L7.37 1.81L7.09 3.26L6.91 4.23H7.02L7.14 4.11L7.63 3.45L8.46 2.42L8.82 2.01L9.25 1.56L9.52 1.34H10.04L10.42 1.91L10.25 2.49L9.72 3.17L9.28 3.74L8.64 4.59L8.25 5.27L8.28 5.32L8.38 5.31L9.81 5.01L10.58 4.87L11 4.71L11.91 4.91L11.96 5L11 5.51L10.81 5.75L9.66 5.98L7.94 6.39L7.92 6L7.94 6.43L8.72 6.51L9.05 6.52H9.86L11.37 6.64L11.76 6L12 7.22L11.96 7.46L11.35 7.77L10.53 7.57L8.62 7.12L7.96 6.95H7.87V7.01L8.42 7.54L9.42 8.45L10.68 9.61L10.74 9L10.58 10.13L10.41 10.11L9.31 9.28L8.88 8L7.92 8.09H7.85V8.18L8.07 8L9.25 10.26L9.31 10L9.22 10.98L8.92 11.09L8.59 11.03L7 10.06L7.19 8.98L6.62 8.01L6.55 8.05L6.21 11.68L6.05 11.86L5.69 12L5.39 11.77L5.23 11L5.39 10.66L5.58 9L5.74 8.93L5.88 7.98L5.97 7.67L5.96 7.64L5.89 7.65L5.17 8.64L4.08 10.11L3.22 11.03L3.01 11.11L2.65 10.93L2.69 10L2.89 10L4.08 8.79L4 7.84L5.27 7L5.26 7.22H5.24L2.07 9.28L1 9.35L1.26 9.13L1.29 8.75L1 8.63L2.36 7.97L2.35 7.98Z"
					fillRule="evenodd"
				/>
			</svg>
		),
	},
	t3: {
		title: 'Open in T3 Chat',
		createUrl: (q: string) =>
			`https://t3.chat/new?${new URLSearchParams({
				q,
			})}`,
		icon: <MessageCircleIcon />,
	},
	v0: {
		title: 'Open in v0',
		createUrl: (q: string) =>
			`https://v0.app?${new URLSearchParams({
				q,
			})}`,
		icon: (
			<svg fill="currentColor" viewBox="0 0 147 70" xmlns="http://www.w3.org/2000/svg">
				<title>v0</title>
				<path d="M56 50V14H70V60.16C70 65.59 65.59 70 60.16 70C57.56 70 55 69 53.16 67.16L0 14H19L56 50Z" />
				<path d="M147 56H133V23.95L100.95 56H133V70H96.69C85.81 70 77 61.19 77 50.31V14H91V46.16L123.16 14H91V0H127.31C138.19 0 147 8.81 147 19.69V56Z" />
			</svg>
		),
	},
	cursor: {
		title: 'Open in Cursor',
		createUrl: (text: string) => {
			const url = new URL('https://cursor.com/link/prompt');
			url.searchParams.set('text', text);
			return url.toString();
		},
		icon: (
			<svg version="1.1" viewBox="0 0 466.73 532.09" xmlns="http://www.w3.org/2000/svg">
				<title>Cursor</title>
				<path
					d="M457.43,125.94L244.42,2.96c-6.84-3.95-15.28-3.95-22.12,0L9.3,125.94c-5.75,3.32-9.3,9.46-9.3,16.11v247.99c0,6.65,3.55,12.79,9.3,16.11l213.01,122.98c6.84,3.95,15.28,3.95,22.12,0l213.01-122.98c5.75-3.32,9.3-9.46,9.3-16.11v-247.99c0-6.65-3.55-12.79-9.3-16.11h-.01ZM444.05,151.99l-205.63,356.16c-1.39,2.4-5.06,1.42-5.06-1.36v-233.21c0-4.66-2.49-8.97-6.53-11.31L24.87,145.67c-2.4-1.39-1.42-5.06,1.36-5.06h411.26c5.84,0,9.49,6.33,6.57,11.39h-.01Z"
					fill="currentColor"
				/>
			</svg>
		),
	},
};

const OpenInContext = createContext<{ query: string } | undefined>(undefined);

const useOpenInContext = () => {
	const context = use(OpenInContext);
	if (!context) {
		throw new Error('OpenIn components must be used within an OpenIn provider');
	}
	return context;
};

/**
 * Internal sentinel components used to identify which children represent the
 * trigger versus the content. The OpenIn root scans its children, finds the
 * first OpenInTrigger and OpenInContent, and routes them into the underlying
 * `DropdownPanelMenu` `trigger` prop and content children respectively.
 *
 * This keeps the public compound API (`<OpenIn><OpenInTrigger /><OpenInContent>...</OpenInContent></OpenIn>`)
 * unchanged while delegating to a `DropdownPanelMenu` internally.
 */
function OpenInTriggerSlot({ children }: { children: ReactNode }): React.JSX.Element {
	return <>{children}</>;
}
OpenInTriggerSlot.displayName = 'OpenInTriggerSlot';

function OpenInContentSlot({ children }: { children: ReactNode }): React.JSX.Element {
	return <>{children}</>;
}
OpenInContentSlot.displayName = 'OpenInContentSlot';

/**
 * Compound component props.
 *
 * Accepts arbitrary children, but the children are expected to be one
 * `OpenInTrigger` and one `OpenInContent` (in any order).
 */
export type OpenInProps = {
	query: string;
	children?: ReactNode;
	className?: string;
};

/**
 * Root of the OpenIn compound component. Provides the query context and
 * routes children into a `DropdownPanelMenu`.
 */
export const OpenIn = ({ query, children, className }: OpenInProps) => {
	let triggerNode: ReactNode = null;
	let contentNode: ReactNode = null;
	Children.forEach(children, (child) => {
		if (!isValidElement(child)) return;
		const type = child.type as { displayName?: string };
		if (type.displayName === 'OpenInTriggerSlot') {
			triggerNode = (child.props as { children?: ReactNode }).children ?? null;
		} else if (type.displayName === 'OpenInContentSlot') {
			contentNode = (child.props as { children?: ReactNode }).children ?? null;
		}
	});

	const contextValue = useMemo(() => ({ query }), [query]);

	return (
		<OpenInContext.Provider value={contextValue}>
			<DropdownPanelMenu
				asChild
				usePortal
				align="start"
				className={className}
				contentClassName={cn('popover-styled p-1 w-[240px]')}
				trigger={triggerNode ?? DEFAULT_OPEN_IN_TRIGGER}
			>
				{contentNode}
			</DropdownPanelMenu>
		</OpenInContext.Provider>
	);
};

/**
 * Slot for the trigger element. Renders nothing on its own — the parent
 * `OpenIn` extracts its child and routes it into `DropdownPanelMenu.trigger`.
 */
export type OpenInContentProps = {
	className?: string;
	children?: ReactNode;
};

export const OpenInContent = ({ className: _className, children }: OpenInContentProps) => (
	<OpenInContentSlot>{children}</OpenInContentSlot>
);

export type OpenInTriggerProps = {
	children?: ReactNode;
};

export const OpenInTrigger = ({ children }: OpenInTriggerProps) => (
	<OpenInTriggerSlot>{children}</OpenInTriggerSlot>
);

export type OpenInChatGPTProps = ComponentProps<typeof DropdownMenuItem>;

export const OpenInChatGPT = (props: OpenInChatGPTProps) => {
	const { query } = useOpenInContext();
	return (
		<DropdownMenuItem asChild {...props}>
			<a
				className="flex items-center gap-2"
				href={providers.chatgpt.createUrl(query)}
				rel="noopener"
				target="_blank"
			>
				<span className="shrink-0">{providers.chatgpt.icon}</span>
				<span className="flex-1">{providers.chatgpt.title}</span>
				<ExternalLinkIcon className="size-4 shrink-0" />
			</a>
		</DropdownMenuItem>
	);
};

export type OpenInClaudeProps = ComponentProps<typeof DropdownMenuItem>;

export const OpenInClaude = (props: OpenInClaudeProps) => {
	const { query } = useOpenInContext();
	return (
		<DropdownMenuItem asChild {...props}>
			<a
				className="flex items-center gap-2"
				href={providers.claude.createUrl(query)}
				rel="noopener"
				target="_blank"
			>
				<span className="shrink-0">{providers.claude.icon}</span>
				<span className="flex-1">{providers.claude.title}</span>
				<ExternalLinkIcon className="size-4 shrink-0" />
			</a>
		</DropdownMenuItem>
	);
};
