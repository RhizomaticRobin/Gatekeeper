---
name: "gsd-vgl:research"
description: "Research domain knowledge for a phase"
argument-hint: "<phase-number>"
allowed-tools:
  - Read
  - Bash
  - Task
  - WebSearch
  - WebFetch
---

# gsd-vgl:research — Domain Research

You are a research coordinator. Your job is to spawn parallel research agents that investigate domain knowledge needed for a specific project phase, then synthesize their findings into a structured research document.

---

## Step 1: Identify the Phase

Read the argument provided by the user (phase number). Then load context:

1. Read `.claude/plan/plan.yaml` to find the phase details
2. Read `.claude/plan/plan.yaml` for requirements in that phase
3. Read `.claude/plan/plan.yaml` for overall project context
4. Read `.claude/plan/plan.yaml metadata` for model profile settings

If no phase number is provided, ask the user which phase to research.

If the phase directory does not exist yet, create it:
```
.planning/phases/XX-{phase-slug}/
```

---

## Step 2: Identify Research Topics

From the phase requirements, identify 3-7 research topics. Each topic should be:

- A technology, API, or framework the phase depends on
- A domain concept that needs understanding
- A pattern or architecture decision that needs investigation
- An integration point that needs documentation

Present the topics to the user for confirmation:

> "I've identified these research topics for Phase {N}:
> 1. {topic 1} — {why it's needed}
> 2. {topic 2} — {why it's needed}
> ...
> Shall I proceed, or add/remove topics?"

---

## Step 3: Spawn Research Agents

For each approved topic, spawn a `gsd-phase-researcher` agent using the Task tool:

```
Task: "You are a gsd-phase-researcher agent investigating: {topic}

Context:
- Project: {project name}
- Phase: {phase number} — {phase name}
- Relevant requirements: {requirement IDs and titles}

Research this topic thoroughly. Use WebSearch and WebFetch to find:
1. Official documentation and guides
2. Best practices and common patterns
3. Code examples and implementation approaches
4. Known gotchas, limitations, and pitfalls
5. Alternative approaches with trade-offs

Produce a structured research document with these sections:
- Overview (2-3 sentence summary)
- Key Concepts (definitions and explanations)
- Implementation Approach (recommended pattern)
- Code Examples (minimal, relevant snippets)
- Gotchas & Pitfalls (things to watch for)
- References (URLs to key docs)

Write your findings to: .planning/phases/{XX}-{phase-slug}/{topic-slug}-research.md"
```

Spawn all agents in parallel using multiple Task calls.

---

## Step 4: Synthesize Findings

After all agents complete, read their output files and create a unified research document:

### `.planning/phases/XX-{phase-slug}/XX-RESEARCH.md`

```markdown
# Phase {N} Research: {phase name}

> Research completed on {date}. {N} topics investigated.

## Executive Summary
{2-3 paragraph synthesis of all findings, highlighting key decisions and risks}

## Topic Summaries

### 1. {Topic Name}
- **Recommendation:** {one-line recommendation}
- **Confidence:** {HIGH | MEDIUM | LOW}
- **Key Insight:** {most important finding}
- **Details:** See `{topic-slug}-research.md`

### 2. {Topic Name}
...

## Architecture Implications
{How findings affect the phase's implementation approach}

## Risk Register
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {risk} | {H/M/L} | {H/M/L} | {strategy} |

## Open Questions
- {questions that research could not fully answer}

## Cross-References
- Requirements: {IDs this research informs}
- Dependencies: {external dependencies discovered}
```

---

## Step 5: Update State

After research is complete:

1. Update `.claude/plan/plan.yaml` to note that research for Phase {N} is complete
2. Summarize findings to the user:

> "Research complete for Phase {N}. Key findings:
> - {finding 1}
> - {finding 2}
> - {finding 3}
>
> {N} risk(s) identified. See `.planning/phases/XX-{slug}/XX-RESEARCH.md` for full details.
>
> Next: `gsd-vgl:cross-team` to begin execution, or `gsd-vgl:research {N+1}` for the next phase."

---

## Error Handling

- If WebSearch/WebFetch fails, note the gap and continue with available information
- If a researcher agent fails, log the failure and proceed with remaining topics
- If the phase has no obvious research needs, tell the user and suggest alternatives:
  - `gsd-vgl:map-codebase` for understanding existing code
  - `gsd-vgl:quest` if planning is incomplete
