# v1 Roadmap — Gatekeeper

## Phase 1: Foundation — Testing & Stability
- **Goal:** Establish test coverage for existing code before adding new capabilities
- **Requirements:** R-001, R-002, R-003, R-004, R-005
- **Tasks:** ~8 tasks
- **Deliverables:**
  - Test suite for plan_utils.py
  - Integration tests for shell scripts
  - Hook tests
  - Installer tests
  - Edge case fixes for Gatekeeper loop
- **Dependencies:** None (first phase)
- **Integration Check:** Yes — verify all tests pass and test infrastructure is solid before building on it

## Phase 2: Self-Improving Core — History & Learnings
- **Goal:** System records execution outcomes and accumulates actionable learnings
- **Requirements:** R-006, R-007, R-008, R-009
- **Tasks:** ~6 tasks
- **Deliverables:**
  - Run history database (SQLite/JSON)
  - Learnings accumulator (extract + store + inject)
  - Pattern recognition engine
  - Strategy adaptation logic
- **Dependencies:** Phase 1 (need test infrastructure to verify learning system works)
- **Integration Check:** Yes — verify history is recorded correctly, learnings are injected into prompts

## Phase 3: Smarter Orchestration
- **Goal:** Orchestration adapts dynamically based on context, history, and resources
- **Requirements:** R-010, R-011, R-012, R-013
- **Tasks:** ~6 tasks
- **Deliverables:**
  - Dynamic wave sizer
  - Adaptive retry with failure classification
  - Task type detection and agent routing
  - Budget-aware scheduling
- **Dependencies:** Phase 2 (orchestration uses historical data for decisions)
- **Integration Check:** Yes — verify orchestration decisions are correct under various scenarios

## Phase 4: End-to-End Autonomy
- **Goal:** System handles failures, dependencies, and decisions without human intervention
- **Requirements:** R-014, R-015, R-016, R-017
- **Tasks:** ~6 tasks
- **Deliverables:**
  - Auto-fix for integration failures
  - Autonomous dependency resolution
  - Progress-aware decision making
  - End-to-end smoke test
- **Dependencies:** Phase 3 (autonomy builds on smart orchestration)
- **Integration Check:** Yes — full pipeline smoke test validates everything works together

## Phase 5: UX, Polish & Rename
- **Goal:** Rename to Gatekeeper, improve error messages, add onboarding
- **Requirements:** R-018, R-019, R-020
- **Tasks:** ~4 tasks
- **Deliverables:**
  - Project rename (package.json, plugin.json, marketplace.json, README)
  - Error message audit and improvement
  - First-run onboarding flow
- **Dependencies:** Phase 4 (rename after all features are stable)
- **Integration Check:** No — final polish, verified by manual review

## Summary

| Phase | Name | Tasks | Requirements | Integration Check |
|-------|------|-------|--------------|-------------------|
| 1 | Testing & Stability | ~8 | R-001 to R-005 | Yes |
| 2 | Self-Improving Core | ~6 | R-006 to R-009 | Yes |
| 3 | Smarter Orchestration | ~6 | R-010 to R-013 | Yes |
| 4 | End-to-End Autonomy | ~6 | R-014 to R-017 | Yes |
| 5 | UX, Polish & Rename | ~4 | R-018 to R-020 | No |

**Total:** ~30 tasks across 5 phases
**Critical path:** Phase 1 → 2 → 3 → 4 → 5 (sequential, each builds on the last)
