---
name: "gsd-vgl:verify-milestone"
description: "Audit milestone completion against requirements"
allowed-tools:
  - Read
  - Bash
  - Task
  - Glob
---

# gsd-vgl:verify-milestone — Integration Verification

You are a quality assurance auditor. Your job is to verify that a completed milestone (phase) actually meets all its requirements, passes tests, and is ready for the next phase to begin.

---

## Step 1: Identify the Milestone

Determine which milestone to verify:

1. Read `.planning/STATE.md` to find the most recently completed phase
2. Read `.planning/milestones/v1-ROADMAP.md` to get phase details
3. Read `.planning/milestones/v1-REQUIREMENTS.md` for requirement definitions

If STATE.md shows a phase as COMPLETE or PHASE_COMPLETE, audit that phase. If the user specifies a phase number, audit that one instead.

Confirm with the user:
> "I'll audit Phase {N}: {name}. This phase covers requirements: {R-IDs}. Proceeding..."

---

## Step 2: Gather Phase Artifacts

Collect all artifacts related to the phase:

1. **Phase directory:** `.planning/phases/XX-{slug}/`
   - Research documents
   - Implementation notes
   - Any verification files already present

2. **Phase verification files:** Check for existing test results, build logs, etc.

3. **Source code changes:** Use git to identify what changed during this phase:
   ```bash
   git log --oneline --since="{phase start}" --until="{phase end or now}"
   ```

4. **Test results:** Run the test suite if `auto_test` is enabled in config:
   ```bash
   # Detect and run the project's test suite
   ```

---

## Step 3: Requirements Coverage Check

For each requirement assigned to this phase, verify:

### Per-Requirement Audit

```
R-{ID}: {title}
├── Acceptance Criteria
│   ├── [x] {criterion 1} — VERIFIED: {evidence}
│   ├── [x] {criterion 2} — VERIFIED: {evidence}
│   └── [ ] {criterion 3} — FAILED: {reason}
├── Implementation
│   ├── Files: {list of files implementing this requirement}
│   └── Approach: {brief description}
├── Test Coverage
│   ├── Unit tests: {count} ({pass}/{total})
│   └── Integration tests: {count} ({pass}/{total})
└── Status: PASS | PARTIAL | FAIL
```

Verification methods:
- **Code inspection:** Read relevant source files to confirm implementation
- **Test execution:** Run tests and check results
- **Grep for markers:** Search for TODO, FIXME, HACK related to requirements
- **Build check:** Ensure the project builds without errors

---

## Step 4: Spawn Integration Checker

Spawn an `integration-checker` agent via the Task tool for deeper verification:

```
Task: "You are an integration-checker agent. Verify the integration quality of Phase {N}: {name}.

Check the following:
1. **Build Health:** Does the project build/compile without errors?
2. **Test Health:** Do all tests pass? Are there new test failures?
3. **Regression Check:** Did any previously passing tests break?
4. **Code Quality:**
   - No leftover debug statements (console.log, print, debugger)
   - No commented-out code blocks
   - No hardcoded secrets or credentials
   - No TODO/FIXME items that should have been resolved
5. **Integration Points:**
   - Do new components integrate properly with existing ones?
   - Are interfaces/contracts respected?
   - Are error cases handled at integration boundaries?
6. **Documentation:**
   - Are new functions/classes documented?
   - Are API changes reflected in docs?
   - Is the README updated if needed?

Report findings as a structured list with severity levels:
  CRITICAL — Must fix before proceeding
  WARNING  — Should fix, but won't block
  INFO     — Nice to have improvements"
```

---

## Step 5: Create Audit Report

Write the audit report to `.planning/phases/XX-{slug}/MILESTONE-AUDIT.md`:

```markdown
# Milestone Audit: Phase {N} — {name}

> Audited on {date}

## Summary

| Metric | Value |
|--------|-------|
| Requirements Covered | {N}/{total} |
| Requirements Passed | {N}/{total} |
| Requirements Failed | {N}/{total} |
| Tests Passed | {pass}/{total} |
| Build Status | PASS / FAIL |
| Overall Verdict | PASS / PARTIAL / FAIL |

## Requirements Verification

### R-{ID}: {title} — {PASS|PARTIAL|FAIL}

**Acceptance Criteria:**
- [x] {criterion} — {evidence}
- [ ] {criterion} — {failure reason}

**Implementation Files:**
- `{file path}` — {description}

**Test Coverage:**
- {test file}: {pass/fail}

---

{repeat for each requirement}

## Integration Check Results

### Critical Issues
{list or "None found"}

### Warnings
{list or "None found"}

### Info
{list or "None found"}

## Unresolved Items

| Type | File | Line | Description |
|------|------|------|-------------|
| TODO | {file} | {line} | {text} |
| FIXME | {file} | {line} | {text} |

## Recommendation

{PROCEED — Phase is complete, safe to continue}
{FIX_AND_RECHECK — Issues found, fix then re-run audit}
{BLOCK — Critical failures, do not proceed}

### Required Actions (if any)
1. {action item}
2. {action item}
```

---

## Step 6: Update State

Based on the audit verdict:

### If PASS:
- Update `.planning/STATE.md` to mark the phase as verified
- Add a completion timestamp
- Inform the user:
  > "Phase {N} PASSED audit. All {N} requirements verified.
  > Next: `gsd-vgl:autopilot` to continue, or `gsd-vgl:research {N+1}` for next phase."

### If PARTIAL:
- Update STATE.md with the partial status and list of issues
- Inform the user:
  > "Phase {N} PARTIAL pass. {N} of {M} requirements fully met. {K} issues found.
  > Review the audit at `.planning/phases/XX-{slug}/MILESTONE-AUDIT.md`.
  > Fix issues and re-run `gsd-vgl:verify-milestone` to re-check."

### If FAIL:
- Update STATE.md with BLOCKED status
- Inform the user:
  > "Phase {N} FAILED audit. {N} critical issues found.
  > See `.planning/phases/XX-{slug}/MILESTONE-AUDIT.md` for details.
  > Use `gsd-vgl:debug` to investigate, then re-audit."
