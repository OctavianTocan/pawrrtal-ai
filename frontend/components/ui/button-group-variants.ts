/**
 * ButtonGroup variant definitions.
 *
 * @fileoverview Extracted from `button-group.tsx` so the component file only
 * exports React components (react-doctor `only-export-components`).
 */

import { cva } from 'class-variance-authority';

export const buttonGroupVariants = cva(
	"has-[>[data-slot=button-group]]:gap-2 has-[select[aria-hidden=true]:last-child]:[&>[data-slot=select-trigger]:last-of-type]:rounded-r-4xl flex w-fit items-stretch *:focus-visible:z-10 *:focus-visible:relative [&>[data-slot=select-trigger]:not([class*='w-'])]:w-fit [&>input]:flex-1",
	{
		variants: {
			orientation: {
				horizontal:
					'[&>[data-slot]:not(:has(~[data-slot]))]:rounded-r-4xl! [&>*:not(:first-child)]:rounded-l-none [&>*:not(:first-child)]:border-l-0 [&>*:not(:last-child)]:rounded-r-none',
				vertical:
					'[&>[data-slot]:not(:has(~[data-slot]))]:rounded-b-4xl! flex-col [&>*:not(:first-child)]:rounded-t-none [&>*:not(:first-child)]:border-t-0 [&>*:not(:last-child)]:rounded-b-none',
			},
		},
		defaultVariants: {
			orientation: 'horizontal',
		},
	}
);
