---
name: "gsd-vgl:help"
description: "Show gsd-vgl command reference"
---

# gsd-vgl:help — Command Reference

Display the following command reference to the user. Do NOT attempt to run any tools or modify any files. Simply present this documentation clearly.

---

```
===============================================================================
  GSD-VGL — Get Shit Done with Verified Game Logic
  Command Reference
===============================================================================

  COMMAND                      DESCRIPTION
  ─────────────────────────────────────────────────────────────────────────────

  VGL Core Commands (Game-Theoretic Collaboration)
  ────────────────────────────────────────────────
  gsd-vgl:quest                Structured task execution with verification
                               gates. Define objectives, execute with
                               checkpoints, verify completion criteria.

  gsd-vgl:cross                [DEPRECATED] Use cross-team instead.

  gsd-vgl:cross-team           Execute tasks with TDD + VGL. Handles both
                               single-task and multi-task parallel execution.

  gsd-vgl:bridge               Context bridging between sessions. Export
                               and import state for session continuity.

  gsd-vgl:run-away             Emergency rollback. Safely revert changes
                               when execution goes off track.

  GSD Project Commands (Plan-First Workflow)
  ──────────────────────────────────────────
  gsd-vgl:new-project          Initialize a new project with deep questioning.
                               Creates PROJECT.md, REQUIREMENTS.md, ROADMAP.md,
                               STATE.md, and config.json in .planning/.

  gsd-vgl:research <phase>     Research domain knowledge for a phase.
                               Spawns parallel researcher agents for thorough
                               investigation before implementation begins.

  gsd-vgl:map-codebase         Map an existing codebase for brownfield projects.
                               Produces STACK, ARCHITECTURE, STRUCTURE,
                               CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS.

  gsd-vgl:autopilot            Launch autonomous execution via ralph.sh outer
                               loop. Configures settings, detects state,
                               launches in a new terminal.

  gsd-vgl:progress             Show project status and progress dashboard.
                               Progress bars, task completion %, recent
                               activity, and next-action routing.

  gsd-vgl:settings             Configure model profile and workflow toggles.
                               Manages quality/balanced/budget profiles and
                               agent enable/disable switches.

  gsd-vgl:verify-milestone     Audit milestone completion against requirements.
                               Spawns integration-checker, validates acceptance
                               criteria, produces MILESTONE-AUDIT.md.

  gsd-vgl:debug [issue]        Systematic debugging with persistent state.
                               Creates debug sessions with checkpoints that
                               survive across sessions for continuation.

  Meta
  ────
  gsd-vgl:help                 Show this command reference.

===============================================================================
```

---

## Quick Start

### New Project (Plan-First Workflow)
```
1. gsd-vgl:new-project          — Define your project through guided discovery
2. gsd-vgl:map-codebase         — (If brownfield) Analyze existing code
3. gsd-vgl:research 1           — Research Phase 1 domain knowledge
4. gsd-vgl:autopilot            — Launch autonomous execution
5. gsd-vgl:progress             — Monitor progress at any time
6. gsd-vgl:verify-milestone     — Audit completed milestones
```

### Ad-Hoc Tasks (Game-Theoretic Workflow)
```
1. gsd-vgl:quest                — Execute a focused task with verification
2. gsd-vgl:cross-team           — Execute tasks with TDD + VGL
3. gsd-vgl:bridge               — Preserve context between sessions
4. gsd-vgl:run-away             — Emergency rollback if needed
```

### Combined Workflow
The plan-first and ad-hoc workflows complement each other:
- Use `gsd-vgl:new-project` + `gsd-vgl:autopilot` for the overall project arc
- Use `gsd-vgl:quest` for individual tasks within a phase
- Use `gsd-vgl:cross-team` for task execution within the autopilot flow
- Use `gsd-vgl:cross-team` for phases requiring parallel workstreams
- Use `gsd-vgl:debug` when issues arise during any workflow

---

## Core Workflows

### Plan-First Workflow
Best for: new features, large changes, multi-phase projects.

```
new-project --> research --> autopilot --> progress --> verify-milestone
                   |                          |
                   v                          v
              map-codebase               debug (if issues)
```

The plan-first workflow creates structured artifacts in `.planning/` that guide
autonomous execution. The autopilot reads the roadmap, generates task-level plans,
and executes them with optional verification at each step.

### Ad-Hoc Workflow
Best for: bug fixes, small features, exploratory work.

```
quest --> cross-team (execute) --> bridge (if multi-session)
  |
  v
run-away (if things go wrong)
```

The ad-hoc workflow uses game-theoretic verification to ensure quality without
heavyweight planning. Quests define clear objectives and completion criteria.
Cross-verification adds adversarial review for high-stakes changes.

---

## Security Model

GSD-VGL commands operate within a defined security boundary:

| Command           | File Access        | Network   | Git          |
|-------------------|--------------------|-----------|--------------|
| new-project       | .planning/ (write) | None      | None         |
| research          | .planning/ (write) | WebSearch | None         |
| map-codebase      | Full read          | None      | Read-only    |
| autopilot         | .planning/ (read)  | None      | Via ralph.sh |
| progress          | .planning/ (read)  | None      | None         |
| settings          | config.json (r/w)  | None      | None         |
| verify-milestone  | Full read          | None      | Read-only    |
| debug             | Full read + debug/ | None      | Read-only    |
| quest             | Per-quest scope    | None      | Per-quest    |
| cross (deprecated)| Review scope       | None      | None         |
| cross-team        | Team scope         | None      | Per-team     |
| bridge            | .planning/ (r/w)   | None      | None         |
| run-away          | Full access        | None      | Write        |
| help              | None               | None      | None         |

---

## State Files

GSD-VGL maintains state in the `.planning/` directory:

```
.planning/
  PROJECT.md                          — Project definition and vision
  STATE.md                            — Current execution state
  config.json                         — Configuration and preferences
  milestones/
    v1-REQUIREMENTS.md                — Version 1 requirements
    v1-ROADMAP.md                     — Version 1 phase roadmap
    v2-REQUIREMENTS.md                — Future version requirements
  phases/
    01-foundation/
      01-RESEARCH.md                  — Phase research findings
      MILESTONE-AUDIT.md              — Phase audit report
    02-feature-name/
      02-RESEARCH.md
      MILESTONE-AUDIT.md
  codebase/
    STACK.md                          — Technology stack
    ARCHITECTURE.md                   — System architecture
    STRUCTURE.md                      — Directory structure
    CONVENTIONS.md                    — Code conventions
    TESTING.md                        — Test infrastructure
    INTEGRATIONS.md                   — External integrations
    CONCERNS.md                       — Tech debt and concerns
  research/
    {topic-slug}.md                   — Domain research documents
  debug/
    {issue-slug}.md                   — Debug session logs
```

These files are the source of truth for all gsd-vgl commands. They are designed
to be human-readable and editable. You can modify them directly if needed.

---

For more details on any command, run it without arguments for interactive guidance.
