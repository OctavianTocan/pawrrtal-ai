/**
 * Tool call result or error display.
 *
 * @fileoverview AI Elements — `tool` output subcomponent.
 */

'use client';

import type { ToolUIPart } from 'ai';
import type { ComponentProps, ReactNode } from 'react';
import { isValidElement } from 'react';
import { cn } from '@/lib/utils';
import { CodeBlock } from './code-block';

export type ToolOutputProps = ComponentProps<'div'> & {
	output: ToolUIPart['output'];
	errorText: ToolUIPart['errorText'];
};

export const ToolOutput = ({ className, output, errorText, ...props }: ToolOutputProps) => {
	if (!(output || errorText)) {
		return null;
	}

	let Output = <div>{output as ReactNode}</div>;

	if (typeof output === 'object' && !isValidElement(output)) {
		Output = <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />;
	} else if (typeof output === 'string') {
		Output = <CodeBlock code={output} language="json" />;
	}

	return (
		<div className={cn('space-y-2 p-4', className)} {...props}>
			<h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
				{errorText ? 'Error' : 'Result'}
			</h4>
			<div
				className={cn(
					'overflow-x-auto rounded-md text-xs [&_table]:w-full',
					errorText ? 'bg-destructive/10 text-destructive' : 'bg-muted/50 text-foreground'
				)}
			>
				{errorText && <div>{errorText}</div>}
				{Output}
			</div>
		</div>
	);
};
