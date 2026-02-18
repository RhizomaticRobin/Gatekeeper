# Model Profiles

Model profiles control which Claude model each Gatekeeper agent uses. This allows balancing quality vs token spend.

## Profile Definitions

| Agent | `default` | `quality` | `balanced` | `budget` |
|-------|-----------|-----------|------------|----------|
| orchestrator | sonnet | opus | sonnet | sonnet |
| planner | opus | opus | opus | sonnet |
| verifier | opus | opus | opus | sonnet |
| assessor | opus | opus | opus | sonnet |
| tester | sonnet | opus | sonnet | haiku |
| executor | haiku | opus | sonnet | haiku |
| phase-researcher | sonnet | opus | sonnet | haiku |
| project-researcher | sonnet | opus | sonnet | haiku |
| debugger | sonnet | opus | sonnet | sonnet |
| codebase-mapper | haiku | sonnet | haiku | haiku |
| plan-checker | sonnet | sonnet | sonnet | haiku |
| phase-assessor | opus | opus | opus | sonnet |
| phase-verifier | opus | opus | opus | sonnet |
| evo-scout | haiku | haiku | haiku | haiku |
| evo-optimizer (island 0,1,2,3) | haiku | sonnet | haiku | haiku |
| evo-optimizer (island 4) | opus | opus | sonnet | haiku |

## Profile Philosophy

**default** - Smart allocation with strong verification
- Opus for planning and verification (where architecture decisions and quality gates happen)
- Sonnet for orchestration, testing, and research (follows explicit instructions)
- Haiku for execution (follows detailed task-{id}.md prompts)
- Use when: normal development, strong quality gates with efficient execution

**quality** - Maximum reasoning power
- Opus for all decision-making agents
- Sonnet for read-only verification and mapping
- Use when: quota available, critical architecture work

**balanced** - Moderate allocation
- Opus only for planning (where architecture decisions happen)
- Sonnet for execution, verification, and research
- Use when: good balance of quality and cost

**budget** - Minimal Opus usage
- Sonnet for anything that writes code or verifies
- Haiku for research, execution, and mapping
- Use when: conserving quota, high-volume work, less critical phases

## Resolution Logic

Orchestrators resolve model before spawning:

```
1. Read plan.yaml metadata
2. Get model_profile (default: "default")
3. Look up agent in table above
4. Pass model parameter to Task call
```

## Switching Profiles

Runtime: `/gatekeeper:set-profile <profile>`

Per-project default: Set in `plan.yaml` metadata:
```yaml
metadata:
  model_profile: "default"
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
| `max_gatekeeper_iterations` | positive integer | 50 | Maximum Gatekeeper loop iterations before halting |
| `timeout_hours` | positive integer | 8 | Maximum hours before timeout |
| `stuck_threshold` | positive integer | 3 | Number of retries on the same task before marking stuck |
| `circuit_breaker_threshold` | positive integer | 5 | Consecutive failures before circuit breaker trips |
| `model_profile` | string | "default" | Which model profile to use (default/quality/balanced/budget) |
| `test_framework` | string | — | Test framework in use (e.g., pytest, jest) |
| `project_context` | dict | — | Discovery answers from the quest workflow (vision, users, tech stack, etc.) |
| `hyperphase` | boolean | false | Enable Hyperphase N (evolutionary optimization) after all Hyperphase 1 tasks pass verification |
| `hyperphase_candidates` | positive integer | 3 | Number of top-K hotspot candidates to optimize in Hyperphase N |

### Resilience Fields

The four resilience fields (`max_gatekeeper_iterations`, `timeout_hours`, `stuck_threshold`, `circuit_breaker_threshold`) correspond to the defaults in `scripts/resilience.py`. When present in `plan.yaml` metadata, they are validated as positive integers. When absent, the runtime defaults from `resilience.py` apply.

### Deliverables

Task-level `deliverables` has one required and one optional field:

| Field | Required | Description |
|-------|----------|-------------|
| `deliverables.backend` | Yes | Backend implementation description |
| `deliverables.frontend` | No (warning) | Frontend implementation description. Omitting produces a warning, not an error. This supports CLI-only tasks. |

## Design Rationale

**Why Opus for planner?**
Planning involves architecture decisions, goal decomposition, and task design. This is where model quality has the highest impact.

**Why Haiku for executor in default?**
Executors follow explicit task-{id}.md instructions with detailed test dependency graphs and guidance. The task already contains the reasoning; execution is implementation that follows directions.

**Why Opus for verifier and assessor?**
Verification and assessment require goal-backward reasoning — checking if code *delivers* what the phase promised, spotting subtle gaps, impossible test assertions, and missing wiring. This is where Opus catches what Sonnet misses.

**Why Haiku for codebase-mapper?**
Read-only exploration and pattern extraction. No reasoning required, just structured output from file contents.

**Why Haiku for evo-scout?**
Scouts call a profiler MCP tool and filter results. Minimal reasoning needed — just data collection.

**Why Opus for evo-optimizer island 4?**
Island 4 focuses on novel algorithmic breakthroughs (reduced complexity class, mathematical reformulation). This requires the deepest reasoning — discovering fundamentally better algorithms, not just tweaking existing ones. The haiku islands (0-3) handle mechanical optimizations (vectorization, allocation reduction, memoization, data structures).
