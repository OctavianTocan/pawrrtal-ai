/**
 * Syntax-highlighted code fence with copy affordances.
 *
 * @fileoverview AI Elements — `code-block`.
 */

'use client';

import { CheckIcon, CopyIcon } from 'lucide-react';
import {
	type ComponentProps,
	type CSSProperties,
	createContext,
	type HTMLAttributes,
	use,
	useEffect,
	useMemo,
	useRef,
	useState,
} from 'react';
import { type BundledLanguage, codeToTokens } from 'shiki';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
	code: string;
	language: BundledLanguage;
	showLineNumbers?: boolean;
};

type CodeBlockContextType = {
	code: string;
};

type HighlightedToken = {
	content: string;
	color?: string;
	bgColor?: string;
	fontStyle?: number;
};

type HighlightedCode = {
	tokens: HighlightedToken[][];
};

const CodeBlockContext = createContext<CodeBlockContextType>({
	code: '',
});

async function highlightCode(
	code: string,
	language: BundledLanguage
): Promise<[HighlightedCode, HighlightedCode]> {
	return await Promise.all([
		codeToTokens(code, {
			lang: language,
			theme: 'one-light',
		}),
		codeToTokens(code, {
			lang: language,
			theme: 'one-dark-pro',
		}),
	]);
}

const FONT_STYLE_ITALIC = 1;
const FONT_STYLE_BOLD = 2;
const FONT_STYLE_UNDERLINE = 4;

const tokenStyle = (token: HighlightedToken): CSSProperties => {
	const style: CSSProperties = {};
	if (token.color) {
		style.color = token.color;
	}
	if (token.bgColor) {
		style.backgroundColor = token.bgColor;
	}
	if (token.fontStyle) {
		if ((token.fontStyle & FONT_STYLE_ITALIC) !== 0) {
			style.fontStyle = 'italic';
		}
		if ((token.fontStyle & FONT_STYLE_BOLD) !== 0) {
			style.fontWeight = 700;
		}
		if ((token.fontStyle & FONT_STYLE_UNDERLINE) !== 0) {
			style.textDecoration = 'underline';
		}
	}
	return style;
};

interface HighlightedCodeViewProps {
	className: string;
	highlighted: HighlightedCode | null;
	showLineNumbers: boolean;
}

function HighlightedCodeView({
	className,
	highlighted,
	showLineNumbers,
}: HighlightedCodeViewProps): React.JSX.Element {
	return (
		<div className={className}>
			<pre className="m-0 bg-background! p-4 text-foreground! text-sm">
				<code className="font-mono text-sm">
					{highlighted?.tokens.map((line, lineIndex) => (
						<span
							className="block min-h-[1lh]"
							key={`line-${lineIndex}-${line.map((t) => t.content).join('')}`}
						>
							{showLineNumbers ? (
								<span className="mr-4 inline-block min-w-10 select-none text-right text-muted-foreground">
									{lineIndex + 1}
								</span>
							) : null}
							{line.map((token) => (
								<span
									key={`${token.content}-${token.color ?? ''}`}
									style={tokenStyle(token)}
								>
									{token.content}
								</span>
							))}
						</span>
					))}
				</code>
			</pre>
		</div>
	);
}

export const CodeBlock = ({
	code,
	language,
	showLineNumbers = false,
	className,
	children,
	...props
}: CodeBlockProps) => {
	const [highlighted, setHighlighted] = useState<{
		dark: HighlightedCode | null;
		light: HighlightedCode | null;
	}>({
		dark: null,
		light: null,
	});

	useEffect(() => {
		let cancelled = false;
		highlightCode(code, language).then(([light, dark]) => {
			if (!cancelled) {
				setHighlighted({ dark, light });
			}
		});

		return () => {
			cancelled = true;
		};
	}, [code, language]);

	const contextValue = useMemo(() => ({ code }), [code]);

	return (
		<CodeBlockContext.Provider value={contextValue}>
			<div
				className={cn(
					'group relative w-full overflow-hidden rounded-md border bg-background text-foreground',
					className
				)}
				{...props}
			>
				<div className="relative">
					<HighlightedCodeView
						className="overflow-auto dark:hidden"
						highlighted={highlighted.light}
						showLineNumbers={showLineNumbers}
					/>
					<HighlightedCodeView
						className="hidden overflow-auto dark:block"
						highlighted={highlighted.dark}
						showLineNumbers={showLineNumbers}
					/>
					{children && (
						<div className="absolute top-2 right-2 flex items-center gap-2">
							{children}
						</div>
					)}
				</div>
			</div>
		</CodeBlockContext.Provider>
	);
};

export type CodeBlockCopyButtonProps = ComponentProps<typeof Button> & {
	onCopy?: () => void;
	onError?: (error: Error) => void;
	timeout?: number;
};

export const CodeBlockCopyButton = ({
	onCopy,
	onError,
	timeout = 2000,
	children,
	className,
	...props
}: CodeBlockCopyButtonProps) => {
	const [isCopied, setIsCopied] = useState(false);
	const { code } = use(CodeBlockContext);
	// Spam-resistant timer: ref-stored so the previous setTimeout can be
	// cleared before scheduling a new one. Without this, rapid clicking
	// schedules N concurrent revert-to-Copy calls; the earlier ones fire
	// while the user is still in success state, briefly flickering the
	// icon. See `.claude/rules/react/clear-timers-on-spam.md`.
	const revertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	useEffect(() => {
		const timerRef = revertTimerRef;
		return () => {
			if (timerRef.current !== null) clearTimeout(timerRef.current);
		};
	}, []);

	const copyToClipboard = async () => {
		if (typeof window === 'undefined' || !navigator?.clipboard?.writeText) {
			onError?.(new Error('Clipboard API not available'));
			return;
		}

		try {
			await navigator.clipboard.writeText(code);
			setIsCopied(true);
			onCopy?.();
			if (revertTimerRef.current !== null) clearTimeout(revertTimerRef.current);
			revertTimerRef.current = setTimeout(() => {
				setIsCopied(false);
				revertTimerRef.current = null;
			}, timeout);
		} catch (error) {
			onError?.(error as Error);
		}
	};

	return (
		<Button
			className={cn('shrink-0', className)}
			onClick={copyToClipboard}
			size="icon"
			variant="ghost"
			{...props}
		>
			{children ??
				(isCopied ? (
					<CheckIcon aria-hidden="true" size={14} />
				) : (
					<CopyIcon aria-hidden="true" size={14} />
				))}
		</Button>
	);
};
