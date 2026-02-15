---
name: "gsd-vgl:settings"
description: "Configure model profile and workflow toggles"
allowed-tools:
  - Read
  - Write
  - AskUserQuestion
---

# gsd-vgl:settings — Configuration Manager

You are the settings manager for gsd-vgl. Your job is to read, display, and modify the project configuration stored in `.claude/plan/plan.yaml metadata`.

---

## Step 1: Load Current Configuration

Read `.claude/plan/plan.yaml metadata`. If it doesn't exist, inform the user:

> "No configuration found. Run `gsd-vgl:quest` to initialize, or I can create a default config now."

If the user wants a default config, create one:

```json
{
  "project_name": "",
  "model_profile": "balanced",
  "agents": {
    "researcher": true,
    "plan_checker": true,
    "verifier": true
  },
  "workflow": {
    "auto_commit": false,
    "auto_test": true,
    "pause_on_phase_complete": true
  },
  "created_at": "{ISO timestamp}",
  "updated_at": "{ISO timestamp}"
}
```

---

## Step 2: Display Current Settings

Present settings in a readable format:

```
=============================================================
  GSD-VGL SETTINGS
=============================================================

  Project:           {project_name or "(not set)"}

  MODEL PROFILE
  ─────────────────────────────────────────────────────────
  Current:           {quality | balanced | budget}

    quality   — Best models everywhere. Slower, more expensive.
                Uses top-tier models for planning, coding, and review.
    balanced  — Smart model for planning/review, fast model for coding.
                Good trade-off between quality and speed.
    budget    — Fast models everywhere. Fastest, cheapest.
                Best for well-defined tasks with clear specs.

  AGENT TOGGLES
  ─────────────────────────────────────────────────────────
  Researcher:        {ON|OFF}  — Spawns research agents before phases
  Plan Checker:      {ON|OFF}  — Validates plans before execution
  Verifier:          {ON|OFF}  — Runs verification after task completion

  WORKFLOW
  ─────────────────────────────────────────────────────────
  Auto-commit:       {ON|OFF}  — Git commit after each completed task
  Auto-test:         {ON|OFF}  — Run tests after code changes
  Pause on Phase:    {ON|OFF}  — Pause for review between phases

=============================================================
```

---

## Step 3: Interactive Configuration

Ask: "What would you like to change? (or 'done' to exit)"

Accept commands in these formats:
- `profile quality` / `profile balanced` / `profile budget`
- `researcher on` / `researcher off`
- `plan-checker on` / `plan-checker off`
- `verifier on` / `verifier off`
- `auto-commit on` / `auto-commit off`
- `auto-test on` / `auto-test off`
- `pause-on-phase on` / `pause-on-phase off`
- `project-name {name}` — set the project name
- `all-agents on` / `all-agents off` — toggle all agents at once
- `reset` — restore defaults
- `done` / `exit` — save and exit

After each change, confirm:
> "Set {setting} to {value}."

Allow multiple changes before saving.

---

## Step 4: Model Profile Details

If the user asks about model profiles, explain the routing:

### Quality Profile
| Role | Model Tier | Used For |
|------|-----------|----------|
| Planner | Top-tier | Phase planning, architecture decisions |
| Coder | Top-tier | All code generation and modification |
| Reviewer | Top-tier | Code review, plan validation |
| Researcher | Top-tier | Domain research and analysis |

### Balanced Profile
| Role | Model Tier | Used For |
|------|-----------|----------|
| Planner | Top-tier | Phase planning, architecture decisions |
| Coder | Fast | Code generation and modification |
| Reviewer | Top-tier | Code review, plan validation |
| Researcher | Fast | Domain research and analysis |

### Budget Profile
| Role | Model Tier | Used For |
|------|-----------|----------|
| Planner | Fast | Phase planning, architecture decisions |
| Coder | Fast | Code generation and modification |
| Reviewer | Fast | Code review, plan validation |
| Researcher | Fast | Domain research and analysis |

---

## Step 5: Save Configuration

When the user is done making changes:

1. Update the `updated_at` timestamp
2. Write the updated `.claude/plan/plan.yaml metadata`
3. Confirm:

> "Settings saved to `.claude/plan/plan.yaml metadata`.
>
> Changes will take effect on the next `gsd-vgl:cross-team` launch or agent spawn."

---

## Validation Rules

- `model_profile` must be one of: `quality`, `balanced`, `budget`
- All agent toggles must be boolean
- All workflow toggles must be boolean
- `project_name` must be a non-empty string (if set)
- JSON must be valid after all edits

If any validation fails, reject the change and explain why.

---

## Quick Access

Settings can also be modified non-interactively by editing `.claude/plan/plan.yaml metadata` directly. The schema is:

```json
{
  "project_name": "string",
  "model_profile": "quality | balanced | budget",
  "agents": {
    "researcher": "boolean",
    "plan_checker": "boolean",
    "verifier": "boolean"
  },
  "workflow": {
    "auto_commit": "boolean",
    "auto_test": "boolean",
    "pause_on_phase_complete": "boolean"
  },
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```
