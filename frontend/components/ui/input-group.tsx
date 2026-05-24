'use client';

import { cva, type VariantProps } from 'class-variance-authority';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

function InputGroup({ className, ...props }: React.ComponentProps<'fieldset'>) {
	return (
		<fieldset
			data-slot="input-group"
			// `overflow-hidden` clips the `block-end` / `block-start` addons to
			// the InputGroup's rounded corners — without it, the footer's
			// background paints flat against the bottom edge while the parent
			// reads as rounded, leaving square bottom-left/bottom-right corners
			// underneath the rounded shell. The `ring`/`focus-visible` chrome
			// uses box-shadow so it isn't clipped by `overflow-hidden`.
			className={cn(
				'group/input-group relative flex h-9 w-full min-w-0 items-center overflow-hidden rounded-4xl border border-input bg-input/30 transition-colors outline-none in-data-[slot=combobox-content]:focus-within:border-inherit in-data-[slot=combobox-content]:focus-within:ring-0 has-data-[align=block-end]:rounded-2xl has-data-[align=block-start]:rounded-2xl has-[[data-slot=input-group-control]:focus-visible]:border-ring has-[[data-slot=input-group-control]:focus-visible]:ring-[3px] has-[[data-slot=input-group-control]:focus-visible]:ring-ring/50 has-[[data-slot][aria-invalid=true]]:border-destructive has-[[data-slot][aria-invalid=true]]:ring-[3px] has-[[data-slot][aria-invalid=true]]:ring-destructive/20 has-[textarea]:rounded-surface-lg has-[>[data-align=block-end]]:h-auto has-[>[data-align=block-end]]:flex-col has-[>[data-align=block-start]]:h-auto has-[>[data-align=block-start]]:flex-col has-[>textarea]:h-auto dark:has-[[data-slot][aria-invalid=true]]:ring-destructive/40 has-[>[data-align=block-end]]:[&>input]:pt-3 has-[>[data-align=block-start]]:[&>input]:pb-3 has-[>[data-align=inline-end]]:[&>input]:pr-1.5 has-[>[data-align=inline-start]]:[&>input]:pl-1.5',
				className
			)}
			{...props}
		/>
	);
}

const inputGroupAddonVariants = cva(
	"flex h-auto cursor-text items-center justify-center gap-2 py-2 text-sm font-medium text-muted-foreground select-none group-data-[disabled=true]/input-group:opacity-50 **:data-[slot=kbd]:rounded-4xl **:data-[slot=kbd]:bg-muted-foreground/10 **:data-[slot=kbd]:px-1.5 [&>svg:not([class*='size-'])]:size-4",
	{
		variants: {
			align: {
				'inline-start': 'order-first pl-3 has-[>button]:-ml-1 has-[>kbd]:ml-[-0.15rem]',
				'inline-end': 'order-last pr-3 has-[>button]:-mr-1 has-[>kbd]:mr-[-0.15rem]',
				// `rounded-t-surface-lg` / `rounded-b-surface-lg` make the addon's
				// own background paint with the parent shell's bottom/top corner
				// curve so the chat composer's footer (and any block-end strip
				// like the connect-apps band) reads as rounded even when an
				// ancestor's `overflow-hidden` doesn't end up clipping it (e.g.
				// when a stylesheet hot-reload skips the parent rule).
				'block-start':
					'order-first w-full justify-start rounded-t-surface-lg px-3 pt-3 group-has-[>input]/input-group:pt-3 [.border-b]:pb-3',
				'block-end':
					'order-last w-full justify-start rounded-b-surface-lg px-3 pb-3 group-has-[>input]/input-group:pb-3 [.border-t]:pt-3',
			},
		},
		defaultVariants: {
			align: 'inline-start',
		},
	}
);

function InputGroupAddon({
	className,
	align = 'inline-start',
	...props
}: React.ComponentProps<'div'> & VariantProps<typeof inputGroupAddonVariants>) {
	return (
		<div
			data-slot="input-group-addon"
			data-align={align}
			role="presentation"
			className={cn(inputGroupAddonVariants({ align }), className)}
			onClick={(e) => {
				if ((e.target as HTMLElement).closest('button')) {
					return;
				}
				e.currentTarget.parentElement?.querySelector('input')?.focus();
			}}
			onKeyDown={(event) => {
				if (event.key !== 'Enter' && event.key !== ' ') return;
				event.preventDefault();
				event.currentTarget.parentElement?.querySelector('input')?.focus();
			}}
			{...props}
		/>
	);
}

const inputGroupButtonVariants = cva('flex items-center gap-2 rounded-4xl text-sm shadow-none', {
	variants: {
		size: {
			xs: "h-6 gap-1 px-1.5 [&>svg:not([class*='size-'])]:size-3.5",
			sm: '',
			'icon-xs': 'size-6 p-0 has-[>svg]:p-0',
			'icon-sm': 'size-8 p-0 has-[>svg]:p-0',
		},
	},
	defaultVariants: {
		size: 'xs',
	},
});

/** Maps compact input-group sizes to `Button` sizes so height/padding stay in sync with toolbar icons. */
const INPUT_GROUP_TO_BUTTON_SIZE = {
	xs: 'xs',
	sm: 'sm',
	'icon-xs': 'icon-xs',
	'icon-sm': 'icon-sm',
} as const satisfies Record<
	NonNullable<VariantProps<typeof inputGroupButtonVariants>['size']>,
	NonNullable<React.ComponentProps<typeof Button>['size']>
>;

function InputGroupButton({
	className,
	type = 'button',
	variant = 'ghost',
	size = 'xs',
	...props
}: Omit<React.ComponentProps<typeof Button>, 'size'> &
	VariantProps<typeof inputGroupButtonVariants>) {
	const buttonSize = INPUT_GROUP_TO_BUTTON_SIZE[size ?? 'xs'];

	return (
		<Button
			type={type}
			data-size={size}
			size={buttonSize}
			variant={variant}
			className={cn(inputGroupButtonVariants({ size }), className)}
			{...props}
		/>
	);
}

function InputGroupText({ className, ...props }: React.ComponentProps<'span'>) {
	return (
		<span
			className={cn(
				"flex items-center gap-2 text-sm text-muted-foreground [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4",
				className
			)}
			{...props}
		/>
	);
}

function InputGroupInput({ className, ...props }: React.ComponentProps<'input'>) {
	return (
		<Input
			data-slot="input-group-control"
			className={cn(
				'flex-1 rounded-none border-0 bg-transparent shadow-none ring-0 focus-visible:ring-0 aria-invalid:ring-0 dark:bg-transparent',
				className
			)}
			{...props}
		/>
	);
}

function InputGroupTextarea({ className, ...props }: React.ComponentProps<'textarea'>) {
	return (
		<Textarea
			data-slot="input-group-control"
			className={cn(
				'flex-1 resize-none rounded-none border-0 bg-transparent py-2 shadow-none ring-0 focus-visible:ring-0 aria-invalid:ring-0 dark:bg-transparent',
				className
			)}
			{...props}
		/>
	);
}

export {
	InputGroup,
	InputGroupAddon,
	InputGroupButton,
	InputGroupText,
	InputGroupInput,
	InputGroupTextarea,
};
