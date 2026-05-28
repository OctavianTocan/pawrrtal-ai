---
# pawrrtal-0zne
title: 'spike(backend): pilot dry-python/returns on the provider seam'
status: todo
type: task
priority: deferred
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T09:54:25Z
blocked_by:
    - pawrrtal-ca8v
---

From paw v3 brainstorm Thread 1. NOT a blanket adoption — pilot on backend/app/core/providers/ only, where 8 providers funnel into a single chat-router caller (textbook FutureResult fit). 4-week trial; re-evaluate. Do NOT migrate API routes / pydantic-adjacent code / scheduler. Owner + start date TBD by user. See brainstorm doc for full rationale + costs.



## Updated scope (2026-05-28 grilling)

This is now PHASE 3 of a phased experiment. Do NOT start until Phases 0/1/2 (pawrrtal-67rg / pawrrtal-3lnz / pawrrtal-ca8v) have produced positive signals. See docs/superpowers/specs/2026-05-28-returns-adoption-grilling.md for the full rationale.
