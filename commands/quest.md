---
description: "Plan the quest — discover unknowns, generate plan.yaml with must_haves + task .md files"
argument-hint: "[PROJECT_DESCRIPTION]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(ls:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(head:*)", "Bash(wc:*)", "Read", "Glob", "Grep", "Write", "Edit", "AskUserQuestion", "Task"]
---

You are now running the **GSD Quest Planner** for the Verifier-Gated Loop system.

Your job is to guide the user through a structured discovery process, then generate a complete VGL plan with must_haves, TDD-first task prompts, and opencode concurrency instructions. Follow these phases IN ORDER (0 through 5). Do not skip phases. Do not combine phases.

The plugin root is: `${CLAUDE_PLUGIN_ROOT}`
The plan validator is: `${CLAUDE_PLUGIN_ROOT}/scripts/validate-plan.py`

---

## Phase 0: Gather Project Description

The user provided: `$ARGUMENTS`

If `$ARGUMENTS` is non-empty, use it as the project description and proceed to Phase 1. No discovery needed.

If `$ARGUMENTS` is empty, offer the user a choice using `AskUserQuestion`:

**Question**: "How would you like to describe your project?"
**Options**:
1. **Quick** — "Just a 1-3 sentence description" (fastest)
2. **Deep Discovery** — "Guided interview for comprehensive project understanding"

### If Quick:
Ask: "What are you building? Give me a 1-3 sentence description."
Store the response as the project description. Proceed to Phase 1.

### If Deep Discovery:
Run a 4-group interview. Use `AskUserQuestion` for each question. After each group, summarize what you captured back to the user before continuing.

**Group A — Vision & Purpose**
1. What are you building? (elevator pitch in 1-2 sentences)
2. Who is the primary user? (persona, role, or audience)
3. What problem does this solve? (pain point or opportunity)
4. What does success look like? (measurable outcome)

**Group B — Scope & Features**
5. What are the 3-5 core features for v1?
6. What is explicitly out of scope?
7. Any future features to plan for but not build yet?

**Group C — Technical Context**
8. Greenfield or brownfield? (new repo vs. existing codebase)
9. Technology constraints or preferences? (language, framework, infra)
10. Required integrations? (APIs, databases, auth providers)
11. Deployment target? (local, cloud, edge, etc.)

**Group D — Workflow Preferences**
12. Quality preference? (quality / balanced / budget — affects model routing)

After all groups complete, assemble a `project_context` dict from the answers:
```
project_context:
  vision: "..."
  primary_user: "..."
  problem: "..."
  success_criteria: "..."
  core_features: ["..."]
  out_of_scope: ["..."]
  future_features: ["..."]
  greenfield: true/false
  tech_constraints: "..."
  integrations: ["..."]
  deploy_target: "..."
  quality_preference: "quality|balanced|budget"
```

Use the `vision` field as the project description for subsequent phases. Store `project_context` for inclusion in plan.yaml metadata during Phase 5.

Present a summary of the captured project context before proceeding to Phase 1.

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

### Brownfield Detection — Auto-Spawn Codebase Mapper

After the initial scan, determine if this is a **brownfield project** (existing source code with meaningful implementation). A project is brownfield if ANY of these are true:
- 10+ source files exist in `src/`, `app/`, `lib/`, or similar directories
- A project manifest (`package.json`, `pyproject.toml`, etc.) exists with 5+ dependencies
- Database schema or migration files exist
- Existing test files exist

If brownfield is detected, **immediately spawn a `codebase-mapper` agent** to perform a deep 7-dimension analysis:

```python
Task(
    subagent_type='gatekeeper:codebase-mapper',
    prompt="""Analyze the codebase at the current directory and produce comprehensive documentation.

    Project type: {detected type from manifest}

    Perform full analysis: Technology Stack, Architecture, Directory Structure,
    Code Conventions, Testing, Integrations, and Concerns/Tech Debt.

    Write each analysis to .planning/codebase/ directory (STACK.md, ARCHITECTURE.md,
    STRUCTURE.md, CONVENTIONS.md, TESTING.md, INTEGRATIONS.md, CONCERNS.md).

    Return a summary of key findings."""
)
```

Wait for the mapper to complete. Its findings will inform Phase 2 questioning (you'll know what already exists and won't ask about it) and Phase 4 task design (you'll build on existing architecture rather than reinventing it).

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

## Phase 3: Parallel Research — Investigate Unknown Unknowns

After receiving user decisions, spawn parallel research agents to dig deeper — the user might not know what they don't know.

### Identify Research Topics

From the project description, user answers, and codebase recon, identify 2-5 research topics. Topics should cover:

1. **Reinventing the wheel**: Are there existing packages or framework built-ins for planned features?
2. **Framework constraints**: Will the planned architecture actually work with the chosen tools?
3. **Integration patterns**: How do the chosen technologies connect (auth + framework, ORM + database, etc.)?
4. **Infrastructure gaps**: What's needed but not mentioned (migrations, env vars, external services)?

### Spawn Research Agents

For each topic, spawn a `project-researcher` agent in parallel:

```python
Task(
    subagent_type='gatekeeper:project-researcher',
    prompt="""You are a project-researcher investigating: {topic}

    Project context:
    - Description: {project description}
    - Framework: {detected or chosen framework}
    - Key technologies: {list from recon + user answers}

    Research this topic thoroughly using WebSearch and WebFetch:
    1. Official documentation and guides
    2. Best practices and common patterns
    3. Known gotchas, limitations, and pitfalls
    4. Alternative approaches with trade-offs

    Return a structured summary with:
    - Key findings (bullet points)
    - Recommended approach
    - Gotchas to avoid
    - Relevant documentation URLs"""
)
```

Spawn all agents in parallel (multiple Task calls in one message). Wait for all to complete.

### Synthesize Findings

After all researchers return, present a unified **Pre-flight Check** to the user:

```
## Pre-flight Check

- shadcn/ui already has a DataTable component — we'll use it instead of building from scratch
- NextAuth v5 requires a specific auth.ts config file at the project root
- Prisma needs `npx prisma generate` after schema changes — tasks will include this
```

If nothing significant, just say "Pre-flight check passed, no issues found." and move on.

Feed all research findings into Phase 4 task design — they inform architecture decisions, package choices, and gotcha avoidance.

---

## Phase 4: Hierarchical Plan Generation

Phase 4 uses a hierarchy of specialized subagents to build the plan with full context preservation. Each subagent operates on a focused scope, preventing context overflow and fidelity loss.

**Architecture**: High-level planner → Sequential refinement → Per-phase decomposition → Assembly

### Step 4.0: Ensure `.planning/PROJECT.md` Exists

Check for the project intent file:

```bash
ls .planning/PROJECT.md 2>/dev/null
```

**If missing**, create it:
```bash
mkdir -p .planning
```

Then generate `.planning/PROJECT.md` using the Write tool, following the template at `${CLAUDE_PLUGIN_ROOT}/templates/project.md`. Populate it from:
- `project_context` (if Deep Discovery was used in Phase 0)
- Project description + codebase recon findings (if Quick mode)
- User answers from Phase 2

**If exists**, read it for use as the intent anchor in all subsequent subagent prompts.

Store the contents of `.planning/PROJECT.md` in a variable `PROJECT_INTENT` for injection into subagent prompts.

### Step 4.1: Spawn High-Level Planner (Opus 4.6)

Create output directories:
```bash
mkdir -p .claude/plan/tasks .claude/plan/phases .claude/plans
```

Spawn the high-level-planner agent:

```python
Task(
    subagent_type='gatekeeper:high-level-planner',
    model='opus',
    prompt="""
## PROJECT INTENT
{PROJECT_INTENT — full contents of .planning/PROJECT.md}

## PROJECT DESCRIPTION
{project description from Phase 0}

## CODEBASE RECON SUMMARY
{all findings from Phase 1 — frameworks, existing code, packages, dev server, etc.}
{if brownfield: include summary of codebase-mapper findings from .planning/codebase/*.md}

## RESEARCH FINDINGS
{synthesized results from Phase 3 parallel research agents}

## INSTRUCTIONS
Design the high-level phase outline for this project. Write it to .claude/plan/high-level-outline.yaml.
Follow your agent instructions for schema, methodology, and constraints.
Keep under 200 lines of YAML. Phase-level only — no individual tasks.
"""
)
```

**Wait for completion.** Then verify the outline was created:
```bash
ls .claude/plan/high-level-outline.yaml
```

Read the outline contents for use in subsequent steps.

### Step 4.2: Sequential Plan Refinement (1-2 passes)

Run 2 sequential refinement passes. Each pass reads the current outline and improves it.

**Pass 1:**
```python
Task(
    subagent_type='gatekeeper:plan-refiner',
    model='opus',
    prompt="""
## PROJECT INTENT
{PROJECT_INTENT — full contents of .planning/PROJECT.md}

## CURRENT OUTLINE
{full contents of .claude/plan/high-level-outline.yaml}

## REFINEMENT PASS NUMBER
1

## PREVIOUS REFINEMENT NOTES
(none — this is the first pass)

## INSTRUCTIONS
Evaluate and improve the outline across all 7 dimensions.
Overwrite .claude/plan/high-level-outline.yaml with the improved version.
Append refinement_notes documenting all changes.
"""
)
```

**Wait.** Read back the updated outline.

**Pass 2:**
```python
Task(
    subagent_type='gatekeeper:plan-refiner',
    model='opus',
    prompt="""
## PROJECT INTENT
{PROJECT_INTENT — full contents of .planning/PROJECT.md}

## CURRENT OUTLINE
{full contents of UPDATED .claude/plan/high-level-outline.yaml after pass 1}

## REFINEMENT PASS NUMBER
2

## PREVIOUS REFINEMENT NOTES
{refinement_notes section from pass 1 output}

## INSTRUCTIONS
Evaluate and improve the outline across all 7 dimensions.
Focus on issues the previous pass identified but didn't fully resolve.
Overwrite .claude/plan/high-level-outline.yaml with the improved version.
Append refinement_notes documenting all changes.
"""
)
```

**Wait.** Read back the final outline. Parse it to get the list of phases for Step 4.3.

### Step 4.3: Per-Phase Task Decomposition (Sequential with Full Context Injection)

**CRITICAL**: Phase-planner agents run SEQUENTIALLY. Each one receives the FULL contents of all prior phases' outputs — both the YAML fragments AND the complete task-{id}.md files. This ensures no granularity is lost between phases.

Initialize an accumulator for prior phase context:

```
completed_phases_context = ""
```

For each phase in the outline (sorted by ID):

```python
# Before spawning, build the full prior-phase context by reading ALL files
# produced by prior phase-planner agents

prior_context_parts = []
for prev_phase_id in completed_phase_ids:
    # Read the phase YAML fragment
    phase_yaml = read(f".claude/plan/phases/phase-{prev_phase_id}.yaml")
    prior_context_parts.append(f"### Phase {prev_phase_id} YAML Fragment\n```yaml\n{phase_yaml}\n```")

    # Read EVERY task .md file from that phase (the full content, not just names)
    for task_file in glob(f".claude/plan/tasks/task-{prev_phase_id}.*.md"):
        task_content = read(task_file)
        prior_context_parts.append(f"### {task_file}\n```markdown\n{task_content}\n```")

completed_phases_context = "\n\n".join(prior_context_parts)

Task(
    subagent_type='gatekeeper:phase-planner',
    model='opus',
    prompt="""
## ASSIGNED PHASE
Phase {id}: {name}
Goal: {goal}
Integration check: {integration_check}
Must-haves:
  Truths: {truths}
  Artifacts: {artifacts}
  Key links: {key_links}
Estimated tasks: {estimated_tasks}
Dependencies: {dependencies}

## PROJECT INTENT
{PROJECT_INTENT — full contents of .planning/PROJECT.md}

## FULL HIGH-LEVEL OUTLINE
{full contents of refined .claude/plan/high-level-outline.yaml}

## TASK ID PREFIX
{phase_id} (your tasks will be {phase_id}.1, {phase_id}.2, etc.)

## PRIOR PHASES' COMPLETE TASK CONTEXT
This section contains the FULL output from all prior phase-planner agents.
Read it carefully — it tells you exactly what files, APIs, types, and test
infrastructure exist when your phase begins executing. Your tasks MUST
build on this foundation. Only reference task IDs that appear here.

{completed_phases_context}

(If this is Phase 1, this section will be empty — you have no prior tasks.)

## CODEBASE SUMMARY
{key findings from Phase 1 recon — frameworks, existing code, packages}
{if brownfield: codebase-mapper dimension summaries}

## INSTRUCTIONS
Decompose this phase into concrete tasks. Write:
1. .claude/plan/phases/phase-{id}.yaml — phase fragment with all tasks
2. .claude/plan/tasks/task-{id}.{seq}.md — one prompt file per task

Follow your agent instructions for task design rules, output format, and success criteria.
Reference prior task outputs by specific file path and function/class name.
"""
)
```

**Wait for completion.** Then:
1. Read the newly created `phases/phase-{id}.yaml`
2. Read ALL newly created `tasks/task-{id}.*.md` files
3. Append their FULL contents to `completed_phases_context` for the next phase
4. Continue to the next phase

**The context accumulation is the key mechanism**: by the time Phase N runs, its planner has seen the complete task specifications (not just IDs) from Phases 1 through N-1. This preserves full granularity of dependency information, artifact locations, API surfaces, and test infrastructure across phase boundaries.

### Step 4.4: Assemble Final plan.yaml

The quest orchestrator (not a subagent) assembles the final artifacts:

1. **Read** `high-level-outline.yaml` for metadata and project_must_haves
2. **Read** each `phases/phase-{id}.yaml` (sorted by phase ID)
3. **Merge** into a single `.claude/plan/plan.yaml` with schema:

```yaml
metadata:
  project: "Project name"
  description: "One-line description"
  dev_server_command: "..."
  dev_server_url: "..."
  test_framework: "..."
  model_profile: "..."
  created_at: "YYYY-MM-DD"
  project_context: { ... }  # if available from Phase 0

phases:
  - id: 1
    name: "..."
    goal: "..."
    integration_check: true|false
    must_haves: { truths: [], artifacts: [], key_links: [] }
    tasks:
      - id: "1.1"
        name: "..."
        status: "pending"
        depends_on: []
        deliverables: { backend: "...", frontend: "..." }
        tests:
          quantitative: { command: "..." }
          qualitative: { criteria: ["..."] }
        must_haves: { truths: [], artifacts: [], key_links: [] }
        prompt_file: "tasks/task-1.1.md"
        file_scope: { owns: [], reads: [] }
        wave: 1
  # ... remaining phases merged from phase fragments
```

4. **Validate** the assembled plan:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate-plan.py" .claude/plan/plan.yaml
```

If validation fails, fix errors in plan.yaml and re-validate. Do NOT proceed until validation passes.

5. **Spawn plan-checker** for post-assembly quality gate:

```python
Task(
    subagent_type='gatekeeper:plan-checker',
    prompt="""Verify the assembled plan at .claude/plan/plan.yaml and task files at .claude/plan/tasks/.

    Project intent: {PROJECT_INTENT summary}

    Run all 6 verification dimensions:
    1. Requirement coverage — every project must_have maps to task(s)
    2. Task completeness — all required fields present
    3. Dependency integrity — DAG valid, no orphans, references real task IDs
    4. Test quality — specific commands, observable criteria
    5. File scope safety — parallel waves have non-overlapping owns
    6. Context budget — no oversized tasks

    Return PASS or NEEDS_REVISION with specific issues."""
)
```

If verdict is **NEEDS_REVISION** with blockers, fix the issues in plan.yaml and task files, then re-run the checker. Do NOT proceed until PASS.

6. **Generate** `.claude/plans/plan-summary.md` (under 200 lines) using the Write tool:

```markdown
# Plan: {Project Name}

## Overview
{2-3 sentence summary}

## Tech Stack
- Framework: ...
- Database: ...
- Testing: ...

## must_haves (Project-Level)
### Truths
- {Global invariant 1}

### Artifacts
- {Key deliverable 1}

## Task Graph

| ID | Task | Wave | Depends On | must_haves | Status |
|----|------|------|------------|------------|--------|
| 1.1 | ... | 1 | — | truths: ..., artifacts: ... | pending |

## Architecture Decisions
- {Key decision 1}: {rationale}

## Dev Server
Command: `{command}`
URL: {url}
```

7. **Verify** the summary length:
```bash
wc -l .claude/plans/plan-summary.md
```

8. **Verify** all files exist at correct paths:
```bash
ls -la .claude/plan/plan.yaml .claude/plans/plan-summary.md .claude/plan/tasks/task-*.md
```

### Step 4.5: Cleanup (Optional)

Optionally remove intermediate files to reduce clutter:
- `high-level-outline.yaml` — incorporated into plan.yaml
- `phases/` directory — incorporated into plan.yaml

Keep these if you want to preserve the planning audit trail. The assembled `plan.yaml` and `tasks/task-*.md` files are the authoritative artifacts.

---

## Phase 5: Confirm and Summarize

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
Run `/gatekeeper:cross-team` to start executing tasks with TDD-first workflow.
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
8. Task prompts must include a Test Dependency Graph with 1 test per row, dependencies, and implementation guidance per test
9. Plan summary MUST stay under 200 lines
10. Dependencies must form a DAG (no cycles)
11. Qualitative criteria must describe observable UI behavior (what you'd see in a browser)
12. Use `$ARGUMENTS` as the project description if provided
13. Design must_haves goal-backward: end state first, then decompose
14. Assign wave numbers to enable parallel execution via `/gatekeeper:cross-team`
15. Set `integration_check` on each phase — true at natural seams where cross-phase wiring matters
