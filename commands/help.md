---
name: "gsd-vgl:help"
description: "Show gsd-vgl command reference"
---

# gsd-vgl:help — Command Reference

Display the following command reference to the user. Do NOT attempt to run any tools or modify any files. Simply present this documentation clearly.

---

```
===============================================================================
  EvoGatekeeper — Spec-Driven Development with Verifier-Gated Loops
  Command Reference
===============================================================================

  COMMAND                      DESCRIPTION
  ─────────────────────────────────────────────────────────────────────────────

  VGL Core Commands
  ─────────────────
  gsd-vgl:quest                Structured task execution with verification
                               gates. Supports optional deep discovery mode
                               for comprehensive project understanding.

  gsd-vgl:cross-team           Execute tasks with TDD + VGL. Handles both
                               single-task and multi-task parallel execution.

  gsd-vgl:bridge               Start a standalone Verifier-Gated Loop with
                               TDD-first workflow for ad-hoc tasks.

  gsd-vgl:run-away             Emergency rollback. Safely revert changes
                               when execution goes off track.

  Project Commands
  ────────────────
  gsd-vgl:research <phase>     Research domain knowledge for a phase.
                               Spawns parallel researcher agents for thorough
                               investigation before implementation begins.

  gsd-vgl:map-codebase         Map an existing codebase for brownfield projects.
                               Produces STACK, ARCHITECTURE, STRUCTURE,
                               CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS.

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

### Unified Workflow
```
1. gsd-vgl:quest                — Plan your project (quick or deep discovery)
2. gsd-vgl:map-codebase         — (If brownfield) Analyze existing code
3. gsd-vgl:research 1           — Research Phase 1 domain knowledge
4. gsd-vgl:cross-team           — Execute tasks with TDD + VGL
5. gsd-vgl:progress             — Monitor progress at any time
6. gsd-vgl:verify-milestone     — Audit completed milestones
7. gsd-vgl:bridge               — Start a standalone VGL loop for ad-hoc tasks
8. gsd-vgl:run-away             — Emergency rollback if needed
```

---

## Core Workflow

Best for: all project types, from bug fixes to multi-phase projects.

```
quest --> cross-team (execute) --> verify-milestone
  |                                     |
  v                                     v
research / map-codebase           debug (if issues)
                                        |
                                        v
                                  bridge (standalone VGL)
```

The workflow uses structured discovery via quest, then TDD-first execution via
cross-team with verifier-gated loops. Bridge provides a standalone VGL loop for
ad-hoc tasks outside the main plan. Run-away offers emergency rollback.

---

## Security Model

EvoGatekeeper commands operate within a defined security boundary:

| Command           | File Access          | Network   | Git          |
|-------------------|----------------------|-----------|--------------|
| research          | .claude/plan/ (write)| WebSearch | None         |
| map-codebase      | Full read            | None      | Read-only    |
| progress          | .claude/plan/ (read) | None      | None         |
| settings          | config.json (r/w)    | None      | None         |
| verify-milestone  | Full read            | None      | Read-only    |
| debug             | Full read + debug/   | None      | Read-only    |
| quest             | Per-quest scope      | None      | Per-quest    |
| cross-team        | Team scope           | None      | Per-team     |
| bridge            | .claude/ (r/w)       | None      | None         |
| run-away          | Full access          | None      | Write        |
| help              | None                 | None      | None         |

---

## State Files

EvoGatekeeper maintains state in the `.claude/plan/` directory:

```
.claude/plan/
  plan.yaml                             — Project plan with phases, tasks, must_haves
  tasks/
    task-{N.M}.md                       — Individual task prompts (TDD-first)
```

Additional state directories:

```
.claude/
  vgl-sessions/                         — Per-task VGL session state
  plans/
    plan-summary.md                     — Condensed plan summary
```

These files are the source of truth for all gsd-vgl commands. They are designed
to be human-readable and editable. You can modify them directly if needed.

---

For more details on any command, run it without arguments for interactive guidance.
