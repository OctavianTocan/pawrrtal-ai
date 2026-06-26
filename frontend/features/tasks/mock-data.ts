/**
 * Mock seed for the Tasks feature.
 *
 * 22+ credible items pulled from real-feeling work-product (job hunt,
 * infra, learning, research) plus four projects covering the full tone
 * vocabulary. Dates are computed relative to "now" at module evaluation
 * time so the Today view always has populated Overdue and Today sections
 * regardless of when the route loads.
 *
 * No backend integration — these objects exist purely so the surface has
 * something to render. The real implementation will swap this file for a
 * TanStack Query loader returning the same shape.
 */

import type { Task, TaskProject } from './types';

/**
 * Returns the Date offset by `hours` from "now". Positive values fall in
 * the future, negative values in the past. Used to seed `dueAt` values
 * relative to module evaluation time so sections always render populated.
 */
function offsetHours(hours: number): Date {
  const date = new Date();
  date.setHours(date.getHours() + hours);
  return date;
}

/**
 * Returns the Date offset by `days` from "now". Same semantics as
 * {@link offsetHours} but for whole-day shifts.
 */
function offsetDays(days: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(9, 0, 0, 0);
  return date;
}

/**
 * Project list seed. The four projects cover the full tone vocabulary
 * (`neutral` Inbox, `info` Health & Life, `accent` Job Hunt, `destructive`
 * Survival Mode) so any task row referencing one shows a distinct chip.
 */
export const TASK_PROJECTS: readonly TaskProject[] = [
  { id: 'inbox', name: 'Inbox', tone: 'neutral' },
  { id: 'health-life', name: 'Health & Life', tone: 'info' },
  { id: 'job-hunt', name: 'Job Hunt', tone: 'accent' },
  { id: 'survival-mode', name: 'Survival Mode', emoji: '🔥', tone: 'destructive' },
  { id: 'learning', name: 'Learning', tone: 'success' },
];

/**
 * Task seed for the Today view.
 *
 * Mix of overdue (negative offset hours) and today-due (positive offsets
 * within the same calendar day). Survival-mode flagged items get the fire
 * emoji prefix and the destructive chip regardless of the underlying
 * project — mirrors how the reference Todoist screenshot painted it.
 */
export const TASK_SEED: readonly Task[] = [
  // ─── Overdue ──────────────────────────────────────────────────────────
  {
    id: 'overdue-neuro',
    title: 'Book neurologist appointment for essential tremor meds',
    description:
      'Insurance prescription back before next refill window — without that the tremor meds lapse and dose has to ramp again.',
    dueAt: offsetHours(-30),
    completed: false,
    priority: 'urgent',
    projectId: 'health-life',
    tags: ['health'],
  },
  {
    id: 'overdue-wretch',
    title: 'Figure out a setup for Wretch.io guardrails implementation',
    description: 'Three providers in the prototype — pick the validation strategy before the demo on Friday.',
    dueAt: offsetHours(-26),
    completed: false,
    priority: 'high',
    projectId: 'survival-mode',
    tags: ['wretch', 'guardrails', 'infra'],
    flags: ['survival-mode'],
  },
  {
    id: 'overdue-double-wretch',
    title: '"test" double-check Wretch.io guardrails implementation',
    description: 'Spot-check what shipped late last night — confirm the rules really fired in prod.',
    dueAt: offsetHours(-25),
    completed: false,
    priority: 'normal',
    projectId: 'survival-mode',
    tags: ['wretch', 'guardrails', 'qa'],
    flags: ['survival-mode'],
  },
  {
    id: 'overdue-engineer',
    title: 'Reverse-engineer Hermes’ auto-skill creation + give Wretch a basic version',
    description:
      'Look at the Hermes daemon, sketch the minimal acquire / persist loop, drop a stub into Wretch tonight.',
    dueAt: offsetHours(-22),
    completed: false,
    priority: 'high',
    projectId: 'survival-mode',
    tags: ['wretch', 'skills', 'infrastructure'],
    flags: ['survival-mode'],
  },
  {
    id: 'overdue-linkedin',
    title: 'Sit down and improve LinkedIn profile — optimise for recruiter inbound the way yesterday’s hit suggests',
    description: 'About, headline, top three featured projects. 45-minute pomodoro, no rabbit-holing.',
    dueAt: offsetHours(-19),
    completed: false,
    priority: 'high',
    projectId: 'job-hunt',
    tags: ['linkedin', 'job-hunt', 'quick-win'],
  },
  {
    id: 'overdue-second-neuro',
    title: 'Book neurologist appointment for essential tremor meds',
    description: 'Duplicate from earlier — still no callback. Try the second clinic on the list.',
    dueAt: offsetHours(-18),
    completed: false,
    priority: 'normal',
    projectId: 'health-life',
    tags: ['health'],
  },
  {
    id: 'overdue-streaming',
    title: 'Design a more thorough streaming setup modeled on the retro skill',
    description: 'The current pattern leaks tokens — write a proper buffer + RAF flush. Reference the rule note.',
    dueAt: offsetHours(-15),
    completed: false,
    priority: 'high',
    projectId: 'learning',
    tags: ['research', 'infra'],
  },
  {
    id: 'overdue-portfolio',
    title: 'Create tiny Selected Work station',
    description: 'Three case studies, one screen each. Static page, no CMS — link from LinkedIn featured.',
    dueAt: offsetHours(-13),
    completed: false,
    priority: 'normal',
    projectId: 'job-hunt',
    tags: ['portfolio', 'job-hunt'],
  },
  {
    id: 'overdue-restore',
    title: 'Restore + give Wretch back the transcribe skill',
    description: 'Was on the older provider — port the call into the new agent factory and re-test.',
    dueAt: offsetHours(-9),
    completed: false,
    priority: 'normal',
    projectId: 'survival-mode',
    tags: ['wretch', 'skills'],
    flags: ['survival-mode'],
  },
  {
    id: 'overdue-vault',
    title: 'LinkedIn vault review session — go through each with Wretch, draw conclusions, cut what’s not working',
    description: 'Two sessions queued at 25 min each. Keep the editor open the whole time.',
    dueAt: offsetHours(-6),
    completed: false,
    priority: 'normal',
    projectId: 'job-hunt',
    tags: ['linkedin', 'review'],
  },
  {
    id: 'overdue-tljam',
    title: 'Do 60-minute practical TLDraw/JAM rep',
    description: 'Project sketch, not perfection — the goal is feel for the constraint envelope before Friday.',
    dueAt: offsetHours(-4),
    completed: false,
    priority: 'low',
    projectId: 'learning',
    tags: ['practice', 'design'],
  },

  // ─── Today (later in the day) ────────────────────────────────────────
  {
    id: 'today-pr-review',
    title: 'Review sidebar resize jitter fix',
    description: 'Single-file change, should be under 10 minutes — push reviewer queue to zero.',
    dueAt: offsetHours(2),
    completed: false,
    priority: 'high',
    projectId: 'inbox',
    tags: ['code-review', 'quick-win'],
  },
  {
    id: 'today-standup',
    title: 'Async stand-up: what shipped + Friday demo plan',
    description: 'Four bullets, no waffle. Drop a screenshot of the new tasks UI.',
    dueAt: offsetHours(3),
    completed: false,
    priority: 'normal',
    projectId: 'inbox',
    tags: ['admin'],
  },
  {
    id: 'today-stretch',
    title: 'Stretch + 10-minute walk before next deep block',
    dueAt: offsetHours(4),
    completed: false,
    priority: 'low',
    projectId: 'health-life',
    tags: ['health', 'recovery'],
  },
  {
    id: 'today-cover-letter',
    title: 'Draft cover letter v2 for the Series B infra role',
    description:
      'Pull the three best lines from yesterday’s draft, ditch the rest, and re-anchor on the team’s job-hunt thread.',
    dueAt: offsetHours(5),
    completed: false,
    priority: 'high',
    projectId: 'job-hunt',
    tags: ['job-hunt', 'writing'],
  },
  {
    id: 'today-rules-audit',
    title: 'Audit `.claude/rules/general/` — propose two merges',
    description: 'Three rules drift on the "diagnose-before-workaround" theme. Pick the canonical, retire the others.',
    dueAt: offsetHours(6),
    completed: false,
    priority: 'normal',
    projectId: 'inbox',
    tags: ['agent-ops', 'cleanup'],
  },
  {
    id: 'today-postmortem',
    title: 'Write postmortem for Wednesday’s 503 incident',
    description: 'Five-Whys structure, no blame, drop in the shared incidents folder.',
    dueAt: offsetHours(7),
    completed: false,
    priority: 'high',
    projectId: 'survival-mode',
    tags: ['incident', 'writing'],
    flags: ['survival-mode'],
  },
  {
    id: 'today-react-rules',
    title: 'Re-read `react/no-direct-useeffect` before the refactor block',
    dueAt: offsetHours(8),
    completed: false,
    priority: 'low',
    projectId: 'learning',
    tags: ['react', 'reading'],
  },
  {
    id: 'today-recruiter',
    title: 'Reply to the two recruiters from Tuesday',
    description: 'Boilerplate "happy to chat next week" + calendar link. Keep it under 4 sentences each.',
    dueAt: offsetHours(9),
    completed: false,
    priority: 'normal',
    projectId: 'job-hunt',
    tags: ['linkedin', 'job-hunt', 'admin'],
  },
  {
    id: 'today-meds',
    title: 'Take evening meds at the alarm — no skipping',
    dueAt: offsetHours(10),
    completed: false,
    priority: 'normal',
    projectId: 'health-life',
    tags: ['health'],
  },
  {
    id: 'today-deep-block',
    title: 'Deep block: finish the openclaw retry adapter',
    description: 'Two hours uninterrupted, phone in the other room. End with a green test run.',
    dueAt: offsetHours(11),
    completed: false,
    priority: 'high',
    projectId: 'survival-mode',
    tags: ['openclaw', 'infra'],
    flags: ['survival-mode'],
  },
  {
    id: 'today-journal',
    title: 'End-of-day journal: one win, one drag, one tomorrow',
    dueAt: offsetHours(12),
    completed: false,
    priority: 'low',
    projectId: 'health-life',
    tags: ['journal', 'recovery'],
  },
  {
    id: 'today-feedback',
    title: 'Send Wretch design crit to the Friday review thread',
    description: 'Six bullets, link the Loom, no apologies for length.',
    dueAt: offsetHours(13),
    completed: false,
    priority: 'normal',
    projectId: 'survival-mode',
    tags: ['wretch', 'design'],
    flags: ['survival-mode'],
  },

  // ─── Upcoming (next several days) ────────────────────────────────────
  {
    id: 'upcoming-deep-clean',
    title: 'Inbox zero pass on every channel',
    dueAt: offsetDays(1),
    completed: false,
    priority: 'normal',
    projectId: 'inbox',
    tags: ['admin'],
  },
  {
    id: 'upcoming-quarterly',
    title: 'Quarterly review draft — what worked, what to drop',
    dueAt: offsetDays(2),
    completed: false,
    priority: 'high',
    projectId: 'inbox',
    tags: ['planning', 'writing'],
  },
  {
    id: 'upcoming-onboarding',
    title: 'Record 5-min loom on the new agent factory',
    dueAt: offsetDays(3),
    completed: false,
    priority: 'normal',
    projectId: 'learning',
    tags: ['onboarding', 'video'],
  },
  {
    id: 'upcoming-haircut',
    title: 'Haircut before the on-site',
    dueAt: offsetDays(4),
    completed: false,
    priority: 'low',
    projectId: 'health-life',
    tags: ['admin'],
  },
  {
    id: 'upcoming-onsite-prep',
    title: 'On-site prep: pull together case-study one-pagers',
    dueAt: offsetDays(5),
    completed: false,
    priority: 'high',
    projectId: 'job-hunt',
    tags: ['job-hunt', 'prep'],
  },

  // ─── Inbox (no due date) ─────────────────────────────────────────────
  {
    id: 'inbox-rss',
    title: 'Look at that RSS-as-knowledge-graph idea later',
    dueAt: null,
    completed: false,
    priority: 'low',
    projectId: 'inbox',
    tags: ['ideas', 'research'],
  },
  {
    id: 'inbox-newsletter',
    title: 'Pitch newsletter v2 to the team — themes, cadence, scope',
    dueAt: null,
    completed: false,
    priority: 'normal',
    projectId: 'inbox',
    tags: ['writing'],
  },
  {
    id: 'inbox-vacation',
    title: 'Plan the late-summer vacation week — flights, dog sitter',
    dueAt: null,
    completed: false,
    priority: 'low',
    projectId: 'health-life',
    tags: ['planning'],
  },
];
