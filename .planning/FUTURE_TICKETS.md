# Future Tickets

## Enforce file_scope.owns at Write Time

**Priority**: High
**Context**: Skeleton generation + progressive decryption creates per-task file ownership. Currently, this is informational — agents CAN write outside their scope.

**Implementation**: Add a PreToolUse hook for Write/Edit tools that:
1. Reads the current task's `file_scope.owns` from plan.yaml
2. Checks if the target file path is within the owned scope
3. Blocks the write if the path is outside scope
4. Logs a warning for reads of files outside `file_scope.reads`

**Files to modify**:
- `hooks/guard-scope.sh` — already exists for file conflict detection, extend to enforce write scope
- `.claude-plugin/plugin.json` — register the guard hook for PreToolUse:Write and PreToolUse:Edit
