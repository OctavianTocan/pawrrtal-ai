/**
 * Pawrrtal artifact catalog — the safe component vocabulary the agent is
 * allowed to compose into. The agent emits a json-render flat-spec; the
 * catalog enumerated here is what actually renders.
 *
 * @fileoverview This file is the **single source of truth** for which
 * components an artifact can use. Adding a new component means:
 *  1. add a `z.object({...})` schema entry here,
 *  2. add a matching React renderer in {@link ./components},
 *  3. (optional) add styling tokens to {@link ./artifact.css}.
 *
 * The descriptions are model-facing — the LLM reads them when deciding
 * which component to use, so write them like a copywriter for an API
 * reference, not like internal code comments.
 */

import { defineCatalog } from '@json-render/core';
import { schema } from '@json-render/react/schema';
import { z } from 'zod';

export const artifactCatalog = defineCatalog(schema, {
  actions: {},
  components: {
    // ─── Layout ────────────────────────────────────────────────────────
    Page: {
      props: z.object({
        title: z.string(),
        accent: z
          .enum(['cat', 'cobalt', 'forest', 'vite'])
          .nullable()
          .describe('Theme palette. cat = pink/purple, cobalt = blue, forest = green, vite = orange/yellow.'),
      }),
      description: 'Top-level container. One per artifact. Always the root element of the spec.',
    },
    Section: {
      props: z.object({
        title: z.string(),
        lede: z.string().nullable(),
      }),
      description: 'Titled section with optional sub-headline.',
    },

    // ─── Headings & prose ─────────────────────────────────────────────
    Heading: {
      props: z.object({
        text: z.string(),
        level: z.enum(['h1', 'h2', 'h3']).nullable(),
      }),
      description: 'Standalone heading. Default level is h2.',
    },
    Paragraph: {
      props: z.object({
        text: z.string(),
      }),
      description: 'Body paragraph. Plain text only — no inline markdown.',
    },

    // ─── Stat & summary ───────────────────────────────────────────────
    StatPill: {
      props: z.object({
        value: z.string(),
        label: z.string(),
      }),
      description: 'Number + label chip. Use inside a Hero or stand-alone for a stat-row.',
    },
    CardRow: {
      props: z.object({
        cards: z.array(
          z.object({
            icon: z.string().describe('Single emoji to anchor the card.'),
            title: z.string(),
            body: z.string(),
          })
        ),
      }),
      description: 'Three-up summary card row.',
    },

    // ─── Comparison ───────────────────────────────────────────────────
    BeforeAfter: {
      props: z.object({
        before: z.string(),
        after: z.string(),
      }),
      description: 'Two big labels with a → between them. Use for renames or migrations.',
    },
    ColumnList: {
      props: z.object({
        title: z.string(),
        kind: z.enum(['before', 'after']),
        items: z.array(z.string()),
      }),
      description: 'Before/after column list. Pair two of them inside a Section.',
    },

    // ─── Numbered explanations ────────────────────────────────────────
    BucketList: {
      props: z.object({}),
      description: 'Container for numbered Bucket items.',
    },
    Bucket: {
      props: z.object({
        index: z.number(),
        title: z.string(),
        where: z.string().nullable(),
        body: z.string(),
      }),
      description: 'One numbered explanation row.',
    },

    // ─── Two-column code-mapping table ────────────────────────────────
    RouteTable: {
      props: z.object({
        headerLeft: z.string(),
        headerRight: z.string(),
        rows: z.array(
          z.object({
            from: z.string(),
            to: z.string(),
          })
        ),
      }),
      description: 'Two-column code/path mapping table.',
    },

    // ─── Risk cards ───────────────────────────────────────────────────
    RiskGrid: {
      props: z.object({
        items: z.array(
          z.object({
            kind: z.enum(['ok', 'warn', 'bad']),
            title: z.string(),
            body: z.string(),
          })
        ),
      }),
      description: 'Two-up grid of status cards (verified / unverified / risky).',
    },

    // ─── Numbered checklist ───────────────────────────────────────────
    Steps: {
      props: z.object({
        items: z.array(z.object({ body: z.string() })),
      }),
      description: 'Numbered ordered-list of steps the user should take.',
    },

    // ─── Interactive widgets (web + electron only) ────────────────────
    // All interactive widgets carry an `actionId` — a stable identifier
    // the model uses to recognise the interaction in the follow-up user
    // turn it triggers. Keep ids snake_case + meaningful (e.g.
    // `accept_plan`, `pick_severity`) rather than generic (`button_1`).
    ActionButton: {
      props: z.object({
        label: z.string(),
        actionId: z.string(),
        style: z.enum(['primary', 'secondary']).nullable(),
      }),
      description:
        'Single button. Clicking sends a follow-up user message with `label` as text and `actionId` as a stable identifier you can match in your next turn.',
    },
    ChoiceGroup: {
      props: z.object({
        actionId: z.string(),
        prompt: z.string().nullable(),
        multi: z.boolean(),
        options: z.array(
          z.object({
            value: z.string(),
            label: z.string(),
          })
        ),
      }),
      description:
        'Radio (multi=false) or checkbox (multi=true) group. The user picks one or more options and the labels are sent back as a follow-up user message.',
    },
    TextField: {
      props: z.object({
        actionId: z.string(),
        label: z.string(),
        placeholder: z.string().nullable(),
        multiline: z.boolean(),
        submitLabel: z.string().nullable(),
      }),
      description:
        'Free-text input the user submits with Enter (single line) or a button (multi-line). The typed string becomes the follow-up user message.',
    },
    NumberField: {
      props: z.object({
        actionId: z.string(),
        label: z.string(),
        min: z.number().nullable(),
        max: z.number().nullable(),
        step: z.number().nullable(),
        defaultValue: z.number().nullable(),
        kind: z.enum(['slider', 'input']),
        submitLabel: z.string().nullable(),
      }),
      description:
        'Numeric control (slider or text input). The user picks a number and submits; the value is sent back as a follow-up user message.',
    },
  },
});
