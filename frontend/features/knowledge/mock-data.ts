/**
 * Mock data for the Knowledge surface.
 *
 * The shape mirrors what a real backend would eventually return; only the
 * source is fake. When the backend lands, swap `KNOWLEDGE_FILE_TREE` and
 * `KNOWLEDGE_MEMORY_CARDS` for the corresponding query hooks — none of the
 * consuming components need to change.
 */

import type { FileTreeNode, MemoryCardData } from './types';

const DAILY_BRIEF_2026_05_06 = `# Daily Briefing — 2026-05-06

Madrid, 06:31. Cool morning, midweek.

## Status

- Working on the Knowledge view rebuild.
- Sidebar resize bug closed.
- Two PRs awaiting review.

## What I'd do first

- [ ] Read the open review queue before opening anything new.
- [ ] Land the Knowledge route behind a feature flag.
- [ ] Verify mobile bottom-sheet still respects the new pane.

## My Take

The Knowledge view is the second-most opened surface after Chat. Iterate
on the empty state copy — "Nothing shared with you yet" reads cold, and
"Start sharing →" lands in a flow that's not quite finished. Soften the
language and ship the share invite in the same release.
`;

const DAILY_BRIEF_2026_05_07 = `# Daily Briefing — 2026-05-07

Madrid, 06:48. Lighter rain than yesterday, traffic the same.

## Status

- Knowledge route landed on \`development\`.
- Memory cards still rendering with placeholder counts.
- Onboarding doc in review.

## What I'd do first

- [ ] Hook the memory cards to real observation counts.
- [ ] Pull the Assistant Identity card above User Profile.
- [ ] Confirm the document viewer scroll restoration works on reload.

## My Take

You're shipping faster on UI than on the backend. That's fine for now —
the empty states absorb the gap — but plan a backend sprint before the
Memory view becomes actively misleading.
`;

const ONBOARDING_WELCOME = `# Welcome

Welcome to Pawrrtal. This Knowledge folder is your scratch space —
anything you save here becomes context for future conversations.

## What lives here

- **Daily Briefs** — generated each morning.
- **Onboarding** — the docs you're reading now.
- **Misc** — anything that doesn't fit neatly elsewhere.

## What's next

- [ ] Read the setup guide.
- [ ] Pick a model.
- [ ] Try a first chat.
`;

const ONBOARDING_SETUP = `# Setup

A short tour of the moving parts.

## Sidebar

The left rail holds your conversations grouped by date. Pin chats to the
top. Drag the right edge of the sidebar to resize.

## Knowledge

This view. Files on the left, content on the right. Right-click any row
for the row menu (rename, share, download, delete).

## Models

The composer's right cluster picks the model. Defaults to whatever you
last used.
`;

/**
 * Root file tree backing the Knowledge → My Files sub-view.
 *
 * Two top-level folders mirror the screenshots from the design reference:
 * `Misc` (long-running scratchpad) and `onboarding` (introductory docs).
 */
const _KNOWLEDGE_FILE_TREE: FileTreeNode = {
	kind: 'folder',
	name: 'My Files',
	updatedLabel: 'Today',
	children: [
		{
			kind: 'folder',
			name: 'Misc',
			updatedLabel: 'Today',
			children: [
				{
					kind: 'folder',
					name: 'Daily Briefs',
					updatedLabel: 'Today',
					children: [
						{
							kind: 'file',
							name: '2026-05-06_Daily_Briefing.md',
							updatedLabel: 'Yesterday',
							markdown: DAILY_BRIEF_2026_05_06,
						},
						{
							kind: 'file',
							name: '2026-05-07_Daily_Briefing.md',
							updatedLabel: 'Today',
							markdown: DAILY_BRIEF_2026_05_07,
						},
					],
				},
			],
		},
		{
			kind: 'folder',
			name: 'onboarding',
			updatedLabel: 'Today',
			children: [
				{
					kind: 'file',
					name: 'welcome.md',
					updatedLabel: 'Today',
					markdown: ONBOARDING_WELCOME,
				},
				{
					kind: 'file',
					name: 'setup.md',
					updatedLabel: 'Today',
					markdown: ONBOARDING_SETUP,
				},
			],
		},
	],
};

/**
 * Cards rendered on the Memory sub-view.
 *
 * Tone selection deliberately reuses the project's semantic tokens
 * (info / success / accent / destructive / foreground) rather than
 * introducing literal palette entries — see `DESIGN.md` § Colors.
 */
export const KNOWLEDGE_MEMORY_CARDS: readonly MemoryCardData[] = [
	{
		id: 'preferences',
		title: 'User Preferences',
		description: 'Tone, length, formatting defaults Pawrrtal picked up over time.',
		tone: 'accent',
		count: '24 entries',
	},
	{
		id: 'rules',
		title: 'Rules',
		description: 'Hard constraints — never email contacts unless explicitly asked.',
		tone: 'destructive',
		count: '8 entries',
	},
	{
		id: 'profile',
		title: 'User Profile',
		description: 'Name, role, working hours, time zone, and other long-lived facts.',
		tone: 'success',
		count: '12 entries',
	},
	{
		id: 'tools',
		title: 'Your Tools',
		description: 'Connected integrations and the scopes the assistant may use.',
		tone: 'info',
		count: '6 entries',
	},
	{
		id: 'identity',
		title: 'Assistant Identity',
		description: "the assistant's voice, tone, and persona traits as you've shaped them.",
		tone: 'accent',
		count: '5 entries',
	},
	{
		id: 'relationships',
		title: 'User Relationships',
		description: 'People in your orbit — names, context, ongoing threads.',
		tone: 'info',
		count: '18 entries',
	},
	{
		id: 'activity',
		title: 'Recent Activity',
		description: 'A rolling buffer of the last few days of conversations.',
		tone: 'foreground',
		count: 'Live',
	},
];
