---
name: heartbeat
version: 2026-05-25
description: Manage and schedule recurring workspace heartbeats and database-bound reminders.
triggers: ["remind me every", "check in on me", "run this periodically", "schedule a recurring check", "schedule a heartbeat", "modify my heartbeat", "add a scheduled check", "remind me at"]
tools: [workspace_files, reminder_schedule, reminder_list, reminder_cancel]
category: workflow
---

# Heartbeat & Reminder Scheduler

Use this skill when the user wants to schedule recurring agent tasks, automated check-ins, or simple reminders.

## 1. Choosing the Right Mechanism

When the user asks to schedule something, choose the appropriate system:

*   **`HEARTBEAT.md` (Workspace-Scoped, Permanent)**: Use this for structured, workspace-bound recurring agent prompts (e.g., weekly project summaries, morning inbox triage, or build-status checks). These are checked into Git, shared with other team members/agents in the workspace, and support global text guidelines.
*   **Database Reminders (Personal, Transient)**: Use this for personal, lightweight, or one-shot conversational reminders (e.g., *"remind me to check X in 2 hours"* or *"remind me about Y tomorrow"*). This is done purely through the `reminder_schedule` tool, bypassing files and manual syncing.

---

## 2. Modifying the Heartbeat (`HEARTBEAT.md`)

When updating workspace-scoped heartbeat checks:

### Step 1: Read the Existing Config
Open and inspect `HEARTBEAT.md` at the workspace root to check for existing cron checks.
*   If the file does not exist, initialize it with a markdown title and the YAML front-matter fences.

### Step 2: Formulate the Cron Check
Construct the cron check dictionary with the following schema keys:
*   `name`: Unique, lowercase, and **strictly no whitespace** (e.g., `morning_pulse`).
*   `cron`: A valid 5-field cron trigger string (validated at parse time).
*   `prompt`: The self-contained instruction/prompt for the agent when it fires.

### Step 3: Write to File
*   Write or update the check in the YAML front matter of `HEARTBEAT.md`.
*   Preserve all pre-existing checks.
*   Optional: If the user provides general guidance on *how* checks should behave (e.g., *"ignore emails from automated senders"*), append it to the markdown body below the front matter so the agent reads it contextually when any check executes.

### Step 4: Instruct the User to Sync
The agent does not have direct sync tool permissions. Once the file is updated, tell the user:
> "I've successfully updated `HEARTBEAT.md` with your new schedule. Please click the **Sync** button in the Settings UI (or send a POST to `/api/v1/heartbeat/sync`) to activate the new schedules in the job database."

---

## 3. Scheduling Database Reminders

When the user wants simple reminders (one-shot or chat-only recurring tasks):
1. Use `reminder_list` to check if a similar schedule already exists.
2. Invoke `reminder_schedule` with a descriptive name, prompt, and either `cron_expression` or `fire_at`.
3. Inform the user of success and print the registered Job UUID.
