/**
 * Pure formatting helpers for the Tasks surface.
 *
 * Kept separate from `mock-data.ts` so the View tier (which only renders
 * pre-resolved props) can reuse them without picking up any mock-data
 * coupling. All helpers are deterministic given the inputs — no `Date.now()`
 * calls inside, callers pass `now` explicitly.
 */

import { TASK_PRIORITIES } from './constants';
import type { Task, TaskSectionData } from './types';

/**
 * Returns `true` if `date` falls strictly before the start of `now`'s
 * calendar day. Used to bin tasks into the Overdue section regardless of
 * their absolute time-of-day.
 */
export function isOverdue(date: Date, now: Date): boolean {
	const startOfToday = new Date(now);
	startOfToday.setHours(0, 0, 0, 0);
	return date.getTime() < startOfToday.getTime();
}

/**
 * Returns `true` if `date` falls within the same calendar day as `now`,
 * regardless of timezone. Used to bin tasks into the Today section.
 */
function isSameDay(date: Date, now: Date): boolean {
	return (
		date.getFullYear() === now.getFullYear() &&
		date.getMonth() === now.getMonth() &&
		date.getDate() === now.getDate()
	);
}

/**
 * Short relative date label rendered in the metadata strip
 * (e.g. `Yesterday`, `Today 3 PM`, `Mon 5 May`).
 *
 * Bins by calendar day rather than absolute hours so a task due at 1 AM
 * tomorrow doesn't get labeled "Today" just because it's < 24 h away.
 */
export function formatDueLabel(date: Date, now: Date): string {
	if (isSameDay(date, now)) {
		return `Today ${formatClock(date)}`;
	}

	const yesterday = new Date(now);
	yesterday.setDate(now.getDate() - 1);
	if (isSameDay(date, yesterday)) return 'Yesterday';

	const tomorrow = new Date(now);
	tomorrow.setDate(now.getDate() + 1);
	if (isSameDay(date, tomorrow)) return `Tomorrow ${formatClock(date)}`;

	const sameYear = date.getFullYear() === now.getFullYear();
	return new Intl.DateTimeFormat('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		year: sameYear ? undefined : 'numeric',
	}).format(date);
}

/**
 * Short clock label like `3 PM` or `9:30 PM`. Drops the `:00` minute when
 * exactly on the hour for a more editorial feel.
 */
function formatClock(date: Date): string {
	const hour12 = date.getHours() % 12 === 0 ? 12 : date.getHours() % 12;
	const meridiem = date.getHours() >= 12 ? 'PM' : 'AM';
	const minutes = date.getMinutes();
	if (minutes === 0) return `${hour12} ${meridiem}`;
	return `${hour12}:${minutes.toString().padStart(2, '0')} ${meridiem}`;
}

/**
 * Returns the priority's index in {@link TASK_PRIORITIES} so callers can
 * sort with `(a, b) => priorityWeight(a) - priorityWeight(b)` and have the
 * urgent rows float to the top of an unsorted bucket.
 */
export function priorityWeight(priority: Task['priority']): number {
	return TASK_PRIORITIES.indexOf(priority);
}

/**
 * Bins the seed list into the Today view's two display sections (Overdue
 * + Today) and computes the right-aligned "Reschedule" affordance on the
 * Overdue header.
 *
 * Tasks without a due date or with a due date outside today's window are
 * silently dropped — the Today view explicitly excludes them.
 */
export function buildTodaySections(
	tasks: readonly Task[],
	now: Date,
	onReschedule: () => void
): readonly TaskSectionData[] {
	const overdue: Task[] = [];
	const today: Task[] = [];

	for (const task of tasks) {
		if (task.completed) continue;
		if (!task.dueAt) continue;
		if (isOverdue(task.dueAt, now)) {
			overdue.push(task);
		} else if (isSameDay(task.dueAt, now)) {
			today.push(task);
		}
	}

	const sortByDue = (a: Task, b: Task): number => {
		// Non-null asserted by the filter above; both branches require dueAt.
		const aTime = a.dueAt ? a.dueAt.getTime() : 0;
		const bTime = b.dueAt ? b.dueAt.getTime() : 0;
		return aTime - bTime;
	};

	const sections: TaskSectionData[] = [];

	if (overdue.length > 0) {
		sections.push({
			id: 'overdue',
			label: 'Overdue',
			tasks: overdue.toSorted(sortByDue),
			tone: 'destructive',
			rightAction: { label: 'Reschedule', onClick: onReschedule },
		});
	}

	const todaySubtitle = new Intl.DateTimeFormat('en-GB', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
	}).format(now);

	sections.push({
		id: 'today',
		label: 'Today',
		subtitle: todaySubtitle,
		tasks: today.toSorted(sortByDue),
	});

	return sections;
}

/**
 * Bins the seed list into per-day Upcoming sections. Today is excluded
 * (the Today view owns it); past-dated tasks are dropped.
 */
export function buildUpcomingSections(
	tasks: readonly Task[],
	now: Date
): readonly TaskSectionData[] {
	const buckets = new Map<string, Task[]>();
	const labelFormatter = new Intl.DateTimeFormat('en-GB', {
		weekday: 'long',
		day: 'numeric',
		month: 'short',
	});

	for (const task of tasks) {
		if (task.completed) continue;
		if (!task.dueAt) continue;
		if (isOverdue(task.dueAt, now)) continue;
		if (isSameDay(task.dueAt, now)) continue;

		const key = task.dueAt.toISOString().slice(0, 10);
		const existing = buckets.get(key);
		if (existing) {
			existing.push(task);
		} else {
			buckets.set(key, [task]);
		}
	}

	const sortedKeys = Array.from(buckets.keys()).toSorted();
	return sortedKeys.map((key) => {
		const dayTasks = buckets.get(key) ?? [];
		const sample = dayTasks[0];
		const date = sample?.dueAt ?? new Date(key);
		return {
			id: `upcoming-${key}`,
			label: labelFormatter.format(date),
			tasks: dayTasks.toSorted(
				(a, b) => (a.dueAt?.getTime() ?? 0) - (b.dueAt?.getTime() ?? 0)
			),
		} satisfies TaskSectionData;
	});
}

/**
 * Bins the seed list into a single Inbox section — tasks with no due date
 * regardless of their project. Sorted by priority then by id.
 */
export function buildInboxSections(tasks: readonly Task[]): readonly TaskSectionData[] {
	const inbox = tasks.filter((task) => !task.completed && task.dueAt === null);
	if (inbox.length === 0) return [];

	return [
		{
			id: 'inbox',
			label: 'Inbox',
			subtitle: 'Tasks without a due date',
			tasks: inbox.toSorted(
				(a, b) => priorityWeight(a.priority) - priorityWeight(b.priority)
			),
		},
	];
}
