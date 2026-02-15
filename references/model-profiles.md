# Model Profiles

Model profiles control which Claude model each GSD-VGL agent uses. This allows balancing quality vs token spend.

## Profile Definitions

| Agent | `quality` | `balanced` | `budget` |
|-------|-----------|------------|----------|
| planner | opus | opus | sonnet |
| roadmapper | opus | sonnet | sonnet |
| executor | opus | sonnet | sonnet |
| phase-researcher | opus | sonnet | haiku |
| project-researcher | opus | sonnet | haiku |
| research-synthesizer | sonnet | sonnet | haiku |
| debugger | opus | sonnet | sonnet |
| codebase-mapper | sonnet | haiku | haiku |
| verifier | sonnet | sonnet | haiku |
| plan-checker | sonnet | sonnet | haiku |
| integration-checker | sonnet | sonnet | haiku |

## Profile Philosophy

**quality** - Maximum reasoning power
- Opus for all decision-making agents
- Sonnet for read-only verification
- Use when: quota available, critical architecture work

**balanced** (default) - Smart allocation
- Opus only for planning (where architecture decisions happen)
- Sonnet for execution and research (follows explicit instructions)
- Sonnet for verification (needs reasoning, not just pattern matching)
- Use when: normal development, good balance of quality and cost

**budget** - Minimal Opus usage
- Sonnet for anything that writes code
- Haiku for research and verification
- Use when: conserving quota, high-volume work, less critical phases

## Resolution Logic

Orchestrators resolve model before spawning:

```
1. Read plan.yaml metadata
2. Get model_profile (default: "balanced")
3. Look up agent in table above
4. Pass model parameter to Task call
```

## Switching Profiles

Runtime: `/gsd-vgl:set-profile <profile>`

Per-project default: Set in `plan.yaml` metadata:
```yaml
metadata:
  model_profile: "balanced"
```

## Plan Metadata Schema

The `metadata` section of `plan.yaml` supports required and optional fields.

### Required Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `project` | string | Project name identifier |
| `dev_server_command` | string | Command to start the development server |
| `dev_server_url` | string | URL where the dev server is accessible |

### Optional Metadata Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_vgl_iterations` | positive integer | 50 | Maximum VGL loop iterations before halting |
| `timeout_hours` | positive integer | 8 | Maximum hours before timeout |
| `stuck_threshold` | positive integer | 3 | Number of retries on the same task before marking stuck |
| `circuit_breaker_threshold` | positive integer | 5 | Consecutive failures before circuit breaker trips |
| `model_profile` | string | "default" | Which model profile to use (quality/balanced/budget) |
| `test_framework` | string | — | Test framework in use (e.g., pytest, jest) |
| `project_context` | dict | — | Discovery answers from the quest workflow (vision, users, tech stack, etc.) |

### Resilience Fields

The four resilience fields (`max_vgl_iterations`, `timeout_hours`, `stuck_threshold`, `circuit_breaker_threshold`) correspond to the defaults in `scripts/resilience.py`. When present in `plan.yaml` metadata, they are validated as positive integers. When absent, the runtime defaults from `resilience.py` apply.

### Deliverables

Task-level `deliverables` has one required and one optional field:

| Field | Required | Description |
|-------|----------|-------------|
| `deliverables.backend` | Yes | Backend implementation description |
| `deliverables.frontend` | No (warning) | Frontend implementation description. Omitting produces a warning, not an error. This supports CLI-only tasks. |

## Design Rationale

**Why Opus for planner?**
Planning involves architecture decisions, goal decomposition, and task design. This is where model quality has the highest impact.

**Why Sonnet for executor?**
Executors follow explicit task-{id}.md instructions. The task already contains the reasoning; execution is implementation.

**Why Sonnet (not Haiku) for verifiers in balanced?**
Verification requires goal-backward reasoning - checking if code *delivers* what the phase promised, not just pattern matching. Sonnet handles this well; Haiku may miss subtle gaps.

**Why Haiku for codebase-mapper?**
Read-only exploration and pattern extraction. No reasoning required, just structured output from file contents.
