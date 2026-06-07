import { FolderAddIcon, FolderOpenIcon } from '@hugeicons/core-free-icons';
import { HugeiconsIcon } from '@hugeicons/react';
import type * as React from 'react';
import { DialogDescription, DialogHeader } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

const WORKSPACE_OPTIONS = [
	{
		icon: FolderAddIcon,
		title: 'Create new',
		description: 'Start fresh with an empty workspace.',
		status: 'upcoming' as const,
	},
	{
		icon: FolderOpenIcon,
		title: 'Open folder',
		description: 'Choose an existing folder as workspace.',
		status: 'enabled' as const,
	},
] as const;

/** Props for the workspace selection step. */
export interface OnboardingCreateWorkspaceStepProps {
	/** Opens the local folder selection step. */
	onPickLocal: () => void;
}

/** Workspace type selection; "Open folder" is interactive. */
export function OnboardingCreateWorkspaceStep({
	onPickLocal,
}: OnboardingCreateWorkspaceStepProps): React.JSX.Element {
	return (
		<section className="popover-styled onboarding-panel flex w-full max-w-[34rem] select-none flex-col gap-6 rounded-surface-lg border border-border bg-background/95 px-7 py-8 text-foreground shadow-modal-small sm:px-8 sm:py-9">
			<DialogHeader className="items-center gap-2 text-center">
				<div
					className="text-balance text-xl font-semibold tracking-tight text-foreground sm:text-[1.35rem]"
					aria-hidden="true"
				>
					Add Workspace&hellip;
				</div>
				<DialogDescription className="text-[0.9375rem] leading-relaxed text-muted-foreground">
					Where your ideas meet the tools to make them happen.
				</DialogDescription>
			</DialogHeader>

			<ul className="flex flex-col gap-2">
				{WORKSPACE_OPTIONS.map((option): React.JSX.Element => {
					const Icon = option.icon;
					const isEnabled = option.status === 'enabled';
					const chooseWorkspaceOption = isEnabled ? onPickLocal : undefined;

					return (
						<li key={option.title}>
							<button
								type="button"
								className={cn(
									'flex min-h-[4.75rem] w-full items-center gap-4 rounded-surface-lg px-4 text-left',
									'bg-foreground/[0.025] ring-1 ring-border transition-[background-color,box-shadow] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)]',
									isEnabled
										? 'cursor-pointer hover:bg-foreground/[0.045] hover:shadow-minimal active:bg-foreground/[0.035] focus-visible:ring-2 focus-visible:ring-ring/45'
										: 'cursor-not-allowed bg-foreground/[0.012] text-muted-foreground/55'
								)}
								onClick={chooseWorkspaceOption}
								aria-disabled={!isEnabled}
								disabled={!isEnabled}
								tabIndex={isEnabled ? 0 : -1}
							>
								<span
									className={cn(
										'flex size-10 shrink-0 items-center justify-center rounded-surface-lg ring-1',
										isEnabled
											? 'bg-foreground/[0.04] text-muted-foreground ring-border'
											: 'bg-foreground/[0.018] text-muted-foreground/45 ring-border'
									)}
									aria-hidden="true"
								>
									<HugeiconsIcon
										icon={Icon}
										size={20}
										strokeWidth={1.65}
										aria-hidden="true"
									/>
								</span>
								<span className="min-w-0 flex-1">
									<span
										className={cn(
											'block text-base font-semibold',
											isEnabled
												? 'text-foreground'
												: 'text-muted-foreground/65'
										)}
									>
										{option.title}
									</span>
									<span
										className={cn(
											'mt-0.5 block text-sm leading-snug',
											isEnabled
												? 'text-muted-foreground'
												: 'text-muted-foreground/55'
										)}
									>
										{option.description}
									</span>
								</span>
							</button>
						</li>
					);
				})}
			</ul>
		</section>
	);
}
