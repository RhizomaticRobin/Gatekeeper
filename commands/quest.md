---
description: "Plan the quest — discover unknowns, generate plan.yaml with must_haves + task .md files"
argument-hint: "[PROJECT_DESCRIPTION]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(ls:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(head:*)", "Bash(wc:*)", "Read", "Glob", "Grep", "Write", "Edit", "AskUserQuestion", "Task"]
---

You are now running the **GSD Quest Planner** for the Verifier-Gated Loop system.

Your job is to guide the user through a structured discovery process, then generate a complete VGL plan with must_haves, TDD-first task prompts, and opencode concurrency instructions. Follow these 6 phases IN ORDER. Do not skip phases. Do not combine phases.

The plugin root is: `${CLAUDE_PLUGIN_ROOT}`
The plan validator is: `${CLAUDE_PLUGIN_ROOT}/scripts/validate-plan.py`

---

## Phase 0: Gather Project Description

The user provided: `$ARGUMENTS`

If `$ARGUMENTS` is non-empty, use it as the project description and proceed to Phase 1.

If `$ARGUMENTS` is empty, ask the user:
> What are you building? Give me a 1-3 sentence description of the project.

Wait for their response before proceeding.

Store the project description for use in later phases.

---

## Phase 1: Codebase Reconnaissance (SILENT — do not ask the user anything)

Before asking ANY questions, investigate the current project directory **silently**. Use tools to scan for:

1. **Project manifest**: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `Gemfile`, `composer.json`
2. **Existing framework**: Look for Next.js, Express, FastAPI, Django, Rails, Spring, etc. Check config files, directory structure
3. **Source code**: Scan `src/`, `app/`, `lib/`, `pages/`, `routes/`, `api/`, `components/`, `models/` — what already exists?
4. **Database**: Look for schema files, migrations, ORM config (Prisma, SQLAlchemy, TypeORM, Drizzle, etc.)
5. **Auth**: Check for auth middleware, session config, JWT setup, OAuth providers
6. **Tests**: Existing test files, test framework config (jest, pytest, vitest, etc.)
7. **Dev server**: How to start it — check `scripts` in package.json, `Makefile`, `docker-compose.yml`
8. **Installed packages**: Read dependency lists to know what's already available
9. **Environment**: `.env.example`, `.env.local`, config files
10. **Existing plan artifacts**: Check if `.claude/plan/` already exists
11. **Codebase intelligence**: Look for `.claude/` config, CLAUDE.md, README.md — gather architectural context and conventions

Use `Glob`, `Grep`, `Read`, and `Bash(ls ...)` to do this quickly. Read multiple files in parallel.

**Do NOT output anything to the user during this phase** except a brief "Scanning codebase..." message at the start. Collect all findings internally for Phase 2.

---

## Phase 2: Questioning — Surface Known Unknowns (INTERACTIVE)

Now present your findings and ask ONLY the questions the codebase couldn't answer.

Start with a **Recon Summary** showing the user what you found:

```
## Codebase Recon Summary

| Area | Found |
|------|-------|
| Framework | Next.js 14 (app router) |
| Database | Prisma with PostgreSQL |
| Auth | None configured |
| Tests | Vitest configured, 0 test files |
| Dev server | `npm run dev` -> localhost:3000 |
| Packages | tailwind, shadcn/ui, zod, ... |
```

Then ask 3-8 questions using `AskUserQuestion` — ONLY about things the codebase did NOT answer. Examples:

- "No auth found. What auth strategy?" (options: NextAuth, Clerk, Lucia, roll own, you decide)
- "No database found. Which database?" (options: PostgreSQL, SQLite, MongoDB, you decide)
- "API style not clear. REST or tRPC?" (options: REST API routes, tRPC, GraphQL, you decide)

Rules:
- Every question MUST have a "You decide — pick what's best" option
- Do NOT ask about things the codebase already answers (e.g., don't ask "which framework?" if package.json shows Next.js)
- Maximum 8 questions. Fewer is better.
- Use `AskUserQuestion` with structured options, not free-text

Wait for all answers before proceeding.

---

## Phase 3: Investigate Unknown Unknowns (RESEARCH, then report)

After receiving user decisions, dig deeper — the user might not know what they don't know.

Investigate:

1. **Reinventing the wheel**: For each planned feature, check if there's an npm/pip/cargo package or existing utility in the codebase that already does it. If the project uses a meta-framework (Next.js, Rails, Laravel), check if it has built-in support for planned features.

2. **Framework constraints**: Will the planned architecture actually work?
   - If Next.js app router: Can the auth strategy work with server components? Does the state management plan make sense?
   - If FastAPI: Does the ORM choice have async support?
   - Check for known incompatibilities between chosen tools

3. **Infrastructure gaps**: What's needed but not mentioned?
   - Database migrations tooling
   - Environment variables needed
   - External services (email, storage, payments)
   - Build/deploy considerations

**Output**: Only report findings if they're significant. Format as:

```
## Pre-flight Check

- shadcn/ui already has a DataTable component — we'll use it instead of building from scratch
- NextAuth v5 requires a specific auth.ts config file at the project root
- Prisma needs `npx prisma generate` after schema changes — tasks will include this
```

If nothing significant, just say "Pre-flight check passed, no issues found." and move on.

---

## Phase 4: Design Task Graph with must_haves

Now design the full task breakdown with goal-backward must_haves. Follow these rules STRICTLY:

### must_haves Structure

Every phase AND every task gets a `must_haves` block with three fields:
- **truths**: Invariants that must hold true when the phase/task is complete. These are testable assertions about system state. Example: "All API endpoints return JSON with consistent error format", "Auth middleware rejects expired tokens with 401"
- **artifacts**: Concrete files, outputs, or deliverables that must exist. Example: "src/db/schema.prisma with User and Session models", "tests/auth.test.ts with >= 5 test cases"
- **key_links**: References to docs, design decisions, or upstream dependencies. Example: "NextAuth v5 migration guide", "Prisma schema reference"

Design must_haves goal-backward: start from the desired end state and work backward to determine what truths, artifacts, and links each task needs.

### Task Structure Rules

1. **Vertical slices**: Every task MUST have BOTH `deliverables.backend` AND `deliverables.frontend`. No "backend-only" or "frontend-only" tasks. If a task is mostly backend, the frontend deliverable can be a status page, admin view, or smoke-test UI.

2. **Testable**: Every task MUST have:
   - `tests.quantitative.command` — a shell command that exits 0 on success (e.g., `pytest tests/test_auth.py`, `npm test -- --run tests/auth.test.ts`)
   - `tests.qualitative.criteria` — a list of observable UI behaviors for Playwright verification (e.g., "Login form appears at /login with email and password fields", "After submitting valid credentials, user is redirected to /dashboard")

3. **Task IDs**: Use `{phase}.{sequence}` format (e.g., `1.1`, `1.2`, `2.1`)

4. **DAG ordering**: `depends_on` must form a Directed Acyclic Graph. No cycles. Earlier phases complete before later phases start.

5. **Scope**: Each task should be completable in 1-3 VGL iterations (roughly 1 focused feature per task)

6. **Prompt files**: Each task gets a `tasks/task-{id}.md` file with a detailed prompt

7. **File scope** (recommended for parallelism): Each task SHOULD have a `file_scope` field listing directories/files it owns exclusively. Tasks with non-overlapping scopes can run in parallel via `/gsd-vgl:cross-team`. Format: `file_scope: { owns: ["src/app/menu/", "tests/menu.test.ts"], reads: ["src/db/schema.ts"] }`

8. **Wave assignments**: Group tasks into waves for parallel execution. Tasks in the same wave have no dependencies on each other and non-overlapping file scopes. Format: `wave: 1`

### Task Graph Design Process

1. Define end-state must_haves for the entire project
2. Decompose into phase-level must_haves (what must be true after each phase)
3. Decompose phase must_haves into task-level must_haves
4. Identify the foundational setup (Phase 1 tasks): DB schema, auth, base layout
5. Identify core features (Phase 2+ tasks): Each feature is one task
6. Order by dependencies — what must exist before what?
7. Assign waves for parallelism within phases
8. Verify every task has both backend + frontend deliverables
9. Write specific, measurable qualitative criteria

Do NOT output the task graph to the user yet — generate it directly in Phase 5.

---

## Phase 5: Generate Artifacts

Generate three sets of files. Create the directory structure first:

```bash
mkdir -p .claude/plan/tasks .claude/plans
```

**CRITICAL — exact file paths (relative to project root):**
- Plan file -> `.claude/plan/plan.yaml` (NOT `plan.yaml`, NOT `.claude/plan.yaml`)
- Task prompts -> `.claude/plan/tasks/task-{id}.md` (e.g., `.claude/plan/tasks/task-1.1.md`)
- Plan summary -> `.claude/plans/plan-summary.md`

Use the Write tool with these exact paths. The rest of the plugin expects these locations — wrong paths will break `/gsd-vgl:cross-team`.

### Artifact 1: `.claude/plan/plan.yaml`

Write this file to **`.claude/plan/plan.yaml`**. Generate valid YAML matching this schema:

```yaml
metadata:
  project: "Project name"
  description: "One-line description"
  dev_server_command: "npm run dev"
  dev_server_url: "http://localhost:3000"
  test_framework: "vitest"
  model_profile: "opus"
  created_at: "YYYY-MM-DD"

phases:
  - id: 1
    name: "Foundation"
    goal: "Establish core infrastructure and base layout"
    must_haves:
      truths:
        - "Database schema is migrated and seeded"
        - "Auth flow works end-to-end"
      artifacts:
        - "src/db/schema.prisma"
        - "src/auth/middleware.ts"
      key_links:
        - "Prisma docs: https://www.prisma.io/docs"
    tasks:
      - id: "1.1"
        name: "Task name"
        status: "pending"
        depends_on: []
        deliverables:
          backend: "Description of backend work"
          frontend: "Description of frontend work"
        tests:
          quantitative:
            command: "npm test -- --run tests/feature.test.ts"
          qualitative:
            criteria:
              - "Observable UI behavior 1"
              - "Observable UI behavior 2"
        must_haves:
          truths:
            - "Invariant that must hold after this task"
          artifacts:
            - "src/path/to/created-file.ts"
            - "tests/feature.test.ts"
          key_links:
            - "Relevant documentation or reference"
        prompt_file: "tasks/task-1.1.md"
        file_scope:
          owns: ["src/app/feature/", "tests/feature.test.ts"]
          reads: ["src/db/schema.ts"]
        wave: 1
```

### Artifact 2: `.claude/plan/tasks/task-{id}.md` (one per task)

Write each file to **`.claude/plan/tasks/task-{id}.md`** (e.g., `.claude/plan/tasks/task-1.1.md`). Each task prompt file must contain:

```markdown
# Task {id}: {name}

## Goal (from must_haves)
State the truths that must hold and artifacts that must exist when this task is complete.
Reference must_haves.truths and must_haves.artifacts from plan.yaml.

## Context
What this task builds on (completed dependencies, existing code, key_links references)

## Backend Deliverables
- Specific files to create/modify
- API endpoints with method, path, request/response shapes
- Database models/migrations
- Business logic

## Frontend Deliverables
- Specific components to create/modify
- Pages/routes to add
- UI interactions and state management
- How it connects to the backend

## Tests to Write (TDD-First)
Write ALL of these tests BEFORE any implementation code:
- Test file path
- Specific test cases to implement
- What the quantitative test command checks
- Edge cases and error conditions

## Implementation Strategy (Opencode Concurrency)
After writing tests, use opencode agents for parallel implementation:
- launch_opencode(mode="build", task="Make tests in {test_file_1} pass")
- launch_opencode(mode="build", task="Make tests in {test_file_2} pass")
- wait_for_completion() to collect results
- Run full test suite to verify

## Qualitative Verification (Playwright)
What a human (or Playwright) should see when navigating the app:
- Page-by-page walkthrough of expected behavior
- Form interactions and their results
- Error states and edge cases visible in UI

## Key Links
- Links from must_haves.key_links
- Relevant documentation
- Upstream dependency references

## Technical Notes
- Any framework-specific patterns to follow
- Packages to use (from recon findings)
- Known constraints or gotchas
```

The prompt must be detailed enough that a fresh Claude agent with NO prior context can implement the task correctly using TDD-first methodology.

### Artifact 3: `.claude/plans/plan-summary.md`

Write this file to **`.claude/plans/plan-summary.md`**. A condensed summary of the entire plan, under 200 lines. This file is used as context when running in plan mode. Format:

```markdown
# Plan: {Project Name}

## Overview
{2-3 sentence summary}

## Tech Stack
- Framework: ...
- Database: ...
- Auth: ...
- Testing: ...

## must_haves (Project-Level)
### Truths
- {Global invariant 1}
- {Global invariant 2}

### Artifacts
- {Key deliverable 1}
- {Key deliverable 2}

## Task Graph

| ID | Task | Wave | Depends On | must_haves | Status |
|----|------|------|------------|------------|--------|
| 1.1 | ... | 1 | — | truths: ..., artifacts: ... | pending |
| 1.2 | ... | 1 | 1.1 | truths: ..., artifacts: ... | pending |

## Architecture Decisions
- {Key decision 1}: {rationale}
- {Key decision 2}: {rationale}

## Dev Server
Command: `{command}`
URL: {url}
```

### After generating all files, validate:

First, verify files exist at the correct paths:

```bash
ls -la .claude/plan/plan.yaml .claude/plans/plan-summary.md .claude/plan/tasks/task-*.md
```

If any file is missing from these paths, you wrote it to the wrong location. Move or rewrite it to the correct path before continuing.

Then run the plan validator:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate-plan.py" .claude/plan/plan.yaml
```

If validation fails, fix the errors and re-validate. Do NOT proceed until validation passes.

Also verify the summary is under 200 lines:

```bash
wc -l .claude/plans/plan-summary.md
```

---

## Phase 6: Confirm and Summarize

Present a final summary to the user:

```
## Plan Generated Successfully

| Metric | Value |
|--------|-------|
| Phases | N |
| Tasks | N |
| Waves | N |
| Validation | PASSED |

### must_haves Summary
| Phase | Truths | Artifacts | Key Links |
|-------|--------|-----------|-----------|
| 1. Foundation | N | N | N |
| 2. Core Features | N | N | N |

### Files Created
- `.claude/plan/plan.yaml` — full plan definition with must_haves
- `.claude/plan/tasks/task-*.md` — N task prompts (TDD-first + opencode)
- `.claude/plans/plan-summary.md` — condensed summary

### Task Overview
| ID | Task | Wave | Depends On |
|----|------|------|------------|
| 1.1 | ... | 1 | — |
| ... | ... | ... | ... |

### Next Step
Run `/gsd-vgl:cross-team` to start executing tasks with TDD-first workflow.
It will automatically parallelize if multiple tasks in Wave 1 are unblocked, or run a single task if only one is ready.
```

---

## Critical Rules (enforced across all phases)

1. Every task MUST have both `deliverables.backend` and `deliverables.frontend`
2. Every task MUST have both `tests.quantitative.command` and `tests.qualitative.criteria`
3. Every phase and task MUST have `must_haves` with `truths`, `artifacts`, and `key_links`
4. `plan.yaml` MUST pass `validate-plan.py` — run it after generating
5. Do NOT ask about things the codebase already answers (Phase 1 recon)
6. Do NOT plan to reinvent existing packages or framework features
7. Task prompts must be detailed enough for a fresh agent with no context
8. Task prompts must include TDD-first workflow and opencode concurrency instructions
9. Plan summary MUST stay under 200 lines
10. Dependencies must form a DAG (no cycles)
11. Qualitative criteria must describe observable UI behavior (what you'd see in a browser)
12. Use `$ARGUMENTS` as the project description if provided
13. Design must_haves goal-backward: end state first, then decompose
14. Assign wave numbers to enable parallel execution via `/gsd-vgl:cross-team`
