<purpose>
Verify phase goal achievement through goal-backward analysis. Check that the codebase actually delivers what the phase promised, not just that tasks were completed.

This workflow is executed by the verifier agent, either spawned from execute-phase.md or invoked directly via /verify-milestone.
</purpose>

<core_principle>
**Task completion does not equal Goal achievement**

A task "create chat component" can be marked complete when the component is a placeholder. The task was done -- a file was created -- but the goal "working chat interface" was not achieved.

Goal-backward verification starts from the outcome and works backwards:
1. What must be TRUE for the goal to be achieved?
2. What must EXIST for those truths to hold?
3. What must be WIRED for those artifacts to function?

Then verify each level against the actual codebase.

This forms the VGL (Verify-Gap-Loop) mechanism: verify -> identify gaps -> loop back for fixes until the goal is truly met.
</core_principle>

<required_reading>
Reference verification-patterns and verification-report templates as needed.
</required_reading>

<process>

<step name="load_context" priority="first">
**Gather all verification context:**

```bash
# Read the plan
cat plan.yaml 2>/dev/null

# Extract phase goal and must_haves from plan.yaml
# Phase goal is the outcome to verify, not the tasks

# All task files (claims to verify)
ls task-*.md 2>/dev/null
```

**Extract phase goal:** Parse plan.yaml for this phase's goal/description. This is the outcome to verify, not the tasks.

**Extract must_haves:** Parse plan.yaml for the must_haves block containing truths, artifacts, and key_links. These are the primary verification targets.
</step>

<step name="establish_must_haves">
**Determine what must be verified.**

**Option A: must_haves defined in plan.yaml (preferred)**

Extract the must_haves block from plan.yaml:

```yaml
must_haves:
  truths:
    - "User can see existing messages"
    - "User can send a message"
  artifacts:
    - path: "src/components/Chat.tsx"
      provides: "Message list rendering"
    - path: "src/api/chat.ts"
      provides: "Chat API endpoint"
  key_links:
    - from: "Chat.tsx"
      to: "api/chat"
      via: "fetch in useEffect"
```

Each section serves a verification purpose:
- **truths**: Observable behaviors that must be true from a user perspective
- **artifacts**: Concrete files that must exist and be substantive
- **key_links**: Critical connections between artifacts that must be wired

**Option B: Derive from phase goal**

If no must_haves in plan.yaml, derive using goal-backward process:

1. **State the goal:** Take phase goal from plan.yaml
2. **Derive truths:** Ask "What must be TRUE for this goal to be achieved?"
   - List 3-7 observable behaviors from user perspective
   - Each truth should be testable by a human using the app
3. **Derive artifacts:** For each truth, ask "What must EXIST?"
   - Map truths to concrete files (components, routes, schemas)
   - Be specific: `src/components/Chat.tsx`, not "chat component"
4. **Derive key links:** For each artifact, ask "What must be CONNECTED?"
   - Identify critical wiring (component calls API, API queries DB)
   - These are where stubs hide
5. **Document derived must-haves** before proceeding to verification.
</step>

<step name="verify_truths">
**For each observable truth, determine if codebase enables it.**

A truth is achievable if the supporting artifacts exist, are substantive, and are wired correctly.

**Verification status:**
- VERIFIED: All supporting artifacts pass all checks
- FAILED: One or more supporting artifacts missing, stub, or unwired
- UNCERTAIN: Can't verify programmatically (needs human)

**For each truth:**

1. Identify supporting artifacts (which files make this truth possible?)
2. Check artifact status (see verify_artifacts step)
3. Check wiring status (see verify_wiring step)
4. Determine truth status based on supporting infrastructure

**Example:**

Truth: "User can see existing messages"

Supporting artifacts:
- Chat.tsx (renders messages)
- /api/chat GET (provides messages)
- Message model (defines schema)

If Chat.tsx is a stub -> Truth FAILED
If /api/chat GET returns hardcoded [] -> Truth FAILED
If Chat.tsx exists, is substantive, calls API, renders response -> Truth VERIFIED
</step>

<step name="verify_artifacts">
**For each required artifact from must_haves, verify three levels:**

### Level 1: Existence

```bash
check_exists() {
  local path="$1"
  if [ -f "$path" ]; then
    echo "EXISTS"
  elif [ -d "$path" ]; then
    echo "EXISTS (directory)"
  else
    echo "MISSING"
  fi
}
```

If MISSING -> artifact fails, record and continue to next artifact.

### Level 2: Substantive

Check that the file has real implementation, not a stub.

**Line count check:**
```bash
check_length() {
  local path="$1"
  local min_lines="$2"
  local lines=$(wc -l < "$path" 2>/dev/null || echo 0)
  [ "$lines" -ge "$min_lines" ] && echo "SUBSTANTIVE ($lines lines)" || echo "THIN ($lines lines)"
}
```

Minimum lines by type:
- Component: 15+ lines
- API route: 10+ lines
- Hook/util: 10+ lines
- Schema model: 5+ lines

**Stub pattern check:**
```bash
check_stubs() {
  local path="$1"

  # Universal stub patterns
  local stubs=$(grep -c -E "TODO|FIXME|placeholder|not implemented|coming soon" "$path" 2>/dev/null || echo 0)

  # Empty returns
  local empty=$(grep -c -E "return null|return undefined|return \{\}|return \[\]" "$path" 2>/dev/null || echo 0)

  # Placeholder content
  local placeholder=$(grep -c -E "will be here|placeholder|lorem ipsum" "$path" 2>/dev/null || echo 0)

  local total=$((stubs + empty + placeholder))
  [ "$total" -gt 0 ] && echo "STUB_PATTERNS ($total found)" || echo "NO_STUBS"
}
```

**Export check (for components/hooks):**
```bash
check_exports() {
  local path="$1"
  grep -E "^export (default )?(function|const|class)" "$path" && echo "HAS_EXPORTS" || echo "NO_EXPORTS"
}
```

**Combine level 2 results:**
- SUBSTANTIVE: Adequate length + no stubs + has exports
- STUB: Too short OR has stub patterns OR no exports
- PARTIAL: Mixed signals (length OK but has some stubs)

### Level 3: Wired

Check that the artifact is connected to the system.

**Import check (is it used?):**
```bash
check_imported() {
  local artifact_name="$1"
  local search_path="${2:-src/}"

  # Find imports of this artifact
  local imports=$(grep -r "import.*$artifact_name" "$search_path" --include="*.ts" --include="*.tsx" 2>/dev/null | wc -l)

  [ "$imports" -gt 0 ] && echo "IMPORTED ($imports times)" || echo "NOT_IMPORTED"
}
```

**Usage check (is it called?):**
```bash
check_used() {
  local artifact_name="$1"
  local search_path="${2:-src/}"

  # Find usages (function calls, component renders, etc.)
  local uses=$(grep -r "$artifact_name" "$search_path" --include="*.ts" --include="*.tsx" 2>/dev/null | grep -v "import" | wc -l)

  [ "$uses" -gt 0 ] && echo "USED ($uses times)" || echo "NOT_USED"
}
```

**Combine level 3 results:**
- WIRED: Imported AND used
- ORPHANED: Exists but not imported/used
- PARTIAL: Imported but not used (or vice versa)

### Final artifact status

| Exists | Substantive | Wired | Status |
|--------|-------------|-------|--------|
| yes | yes | yes | VERIFIED |
| yes | yes | no | ORPHANED |
| yes | no | - | STUB |
| no | - | - | MISSING |

Record status and evidence for each artifact.
</step>

<step name="verify_wiring">
**Verify key_links between artifacts from must_haves.**

Key links are critical connections. If broken, the goal fails even with all artifacts present.

### Pattern: Component -> API

Check if component actually calls the API:

```bash
verify_component_api_link() {
  local component="$1"
  local api_path="$2"

  # Check for fetch/axios call to the API
  local has_call=$(grep -E "fetch\(['\"].*$api_path|axios\.(get|post).*$api_path" "$component" 2>/dev/null)

  if [ -n "$has_call" ]; then
    # Check if response is used
    local uses_response=$(grep -A 5 "fetch\|axios" "$component" | grep -E "await|\.then|setData|setState" 2>/dev/null)

    if [ -n "$uses_response" ]; then
      echo "WIRED: $component -> $api_path (call + response handling)"
    else
      echo "PARTIAL: $component -> $api_path (call exists but response not used)"
    fi
  else
    echo "NOT_WIRED: $component -> $api_path (no call found)"
  fi
}
```

### Pattern: API -> Database

Check if API route queries database:

```bash
verify_api_db_link() {
  local route="$1"
  local model="$2"

  # Check for Prisma/DB call
  local has_query=$(grep -E "prisma\.$model|db\.$model|$model\.(find|create|update|delete)" "$route" 2>/dev/null)

  if [ -n "$has_query" ]; then
    # Check if result is returned
    local returns_result=$(grep -E "return.*json.*\w+|res\.json\(\w+" "$route" 2>/dev/null)

    if [ -n "$returns_result" ]; then
      echo "WIRED: $route -> database ($model)"
    else
      echo "PARTIAL: $route -> database (query exists but result not returned)"
    fi
  else
    echo "NOT_WIRED: $route -> database (no query for $model)"
  fi
}
```

### Pattern: Form -> Handler

Check if form submission does something:

```bash
verify_form_handler_link() {
  local component="$1"

  # Find onSubmit handler
  local has_handler=$(grep -E "onSubmit=\{|handleSubmit" "$component" 2>/dev/null)

  if [ -n "$has_handler" ]; then
    # Check if handler has real implementation
    local handler_content=$(grep -A 10 "onSubmit.*=" "$component" | grep -E "fetch|axios|mutate|dispatch" 2>/dev/null)

    if [ -n "$handler_content" ]; then
      echo "WIRED: form -> handler (has API call)"
    else
      # Check for stub patterns
      local is_stub=$(grep -A 5 "onSubmit" "$component" | grep -E "console\.log|preventDefault\(\)$|\{\}" 2>/dev/null)
      if [ -n "$is_stub" ]; then
        echo "STUB: form -> handler (only logs or empty)"
      else
        echo "PARTIAL: form -> handler (exists but unclear implementation)"
      fi
    fi
  else
    echo "NOT_WIRED: form -> handler (no onSubmit found)"
  fi
}
```

### Pattern: State -> Render

Check if state is actually rendered:

```bash
verify_state_render_link() {
  local component="$1"
  local state_var="$2"

  # Check if state variable exists
  local has_state=$(grep -E "useState.*$state_var|\[$state_var," "$component" 2>/dev/null)

  if [ -n "$has_state" ]; then
    # Check if state is used in JSX
    local renders_state=$(grep -E "\{.*$state_var.*\}|\{$state_var\." "$component" 2>/dev/null)

    if [ -n "$renders_state" ]; then
      echo "WIRED: state -> render ($state_var displayed)"
    else
      echo "NOT_WIRED: state -> render ($state_var exists but not displayed)"
    fi
  else
    echo "N/A: state -> render (no state var $state_var)"
  fi
}
```

### Aggregate key link results

For each key_link in must_haves:
- Run appropriate verification function
- Record status and evidence
- WIRED / PARTIAL / STUB / NOT_WIRED
</step>

<step name="verify_requirements">
**Check requirements coverage if requirements are defined in plan.yaml.**

For each requirement:
1. Parse requirement description
2. Identify which truths/artifacts support it
3. Determine status based on supporting infrastructure

**Requirement status:**
- SATISFIED: All supporting truths verified
- BLOCKED: One or more supporting truths failed
- NEEDS HUMAN: Can't verify requirement programmatically
</step>

<step name="scan_antipatterns">
**Scan for anti-patterns across phase files.**

Identify files modified by tasks in this phase:
```bash
# Extract files from task checkpoint summaries and file_scope in plan.yaml
grep "file_scope" plan.yaml | sed 's/.*\[//;s/\].*//' | tr ',' '\n' | tr -d ' "' | sort -u
```

Run anti-pattern detection:
```bash
scan_antipatterns() {
  local files="$@"

  echo "## Anti-Patterns Found"
  echo ""

  for file in $files; do
    [ -f "$file" ] || continue

    # TODO/FIXME comments
    grep -n -E "TODO|FIXME|XXX|HACK" "$file" 2>/dev/null | while read line; do
      echo "| $file | $(echo $line | cut -d: -f1) | TODO/FIXME | Warning |"
    done

    # Placeholder content
    grep -n -E "placeholder|coming soon|will be here" "$file" -i 2>/dev/null | while read line; do
      echo "| $file | $(echo $line | cut -d: -f1) | Placeholder | Blocker |"
    done

    # Empty implementations
    grep -n -E "return null|return \{\}|return \[\]|=> \{\}" "$file" 2>/dev/null | while read line; do
      echo "| $file | $(echo $line | cut -d: -f1) | Empty return | Warning |"
    done

    # Console.log only implementations
    grep -n -B 2 -A 2 "console\.log" "$file" 2>/dev/null | grep -E "^\s*(const|function|=>)" | while read line; do
      echo "| $file | - | Log-only function | Warning |"
    done
  done
}
```

Categorize findings:
- Blocker: Prevents goal achievement (placeholder renders, empty handlers)
- Warning: Indicates incomplete (TODO comments, console.log)
- Info: Notable but not problematic
</step>

<step name="identify_human_verification">
**Flag items that need human verification.**

Some things can't be verified programmatically:

**Always needs human:**
- Visual appearance (does it look right?)
- User flow completion (can you do the full task?)
- Real-time behavior (WebSocket, SSE updates)
- External service integration (payments, email)
- Performance feel (does it feel fast?)
- Error message clarity

**Needs human if uncertain:**
- Complex wiring that grep can't trace
- Dynamic behavior depending on state
- Edge cases and error states

**Format for human verification:**
```markdown
## Human Verification Required

### 1. {Test Name}
**Test:** {What to do}
**Expected:** {What should happen}
**Why human:** {Why can't verify programmatically}
```
</step>

<step name="determine_status">
**Calculate overall verification status.**

**Status: passed**
- All truths VERIFIED
- All artifacts pass level 1-3
- All key_links WIRED
- No blocker anti-patterns
- (Human verification items are OK -- will be prompted)

**Status: gaps_found**
- One or more truths FAILED
- OR one or more artifacts MISSING/STUB
- OR one or more key_links NOT_WIRED
- OR blocker anti-patterns found

**Status: human_needed**
- All automated checks pass
- BUT items flagged for human verification
- Can't determine goal achievement without human

**Calculate score:**
```
score = (verified_truths / total_truths)
```

**VGL Loop mechanism:**
When gaps_found, the Verify-Gap-Loop engages:
1. **Verify** -- this phase (just completed)
2. **Gap** -- gaps are identified and documented
3. **Loop** -- execution loops back to fix gaps, then re-verifies

The loop continues until status is `passed` or `human_needed`.
</step>

<step name="generate_fix_plans">
**If gaps_found, recommend fix tasks.**

Group related gaps into fix tasks:

1. **Identify gap clusters:**
   - API stub + component not wired -> "Wire frontend to backend"
   - Multiple artifacts missing -> "Complete core implementation"
   - Wiring issues only -> "Connect existing components"

2. **Generate task recommendations:**

```markdown
### task-{next-id}: {Fix Name}

**Objective:** {What this fixes}

**Steps:**
1. {Step to fix gap 1}
   - Files: {files to modify}
   - Action: {specific fix}
   - Verify: {how to confirm fix}

2. {Step to fix gap 2}
   - Files: {files to modify}
   - Action: {specific fix}
   - Verify: {how to confirm fix}

3. Re-verify phase goal
   - Run verification again
   - Confirm all must-haves pass

**Estimated scope:** {Small / Medium}
```

3. **Keep tasks focused:**
   - 2-3 steps per task
   - Single concern per task
   - Include verification step

4. **Order by dependency:**
   - Fix missing artifacts before wiring
   - Fix stubs before integration
   - Verify after all fixes
</step>

<step name="create_report">
**Generate verification report.**

Fill report sections:
1. **Header:** phase, verified timestamp, status, score
2. **Goal Achievement:** Truth verification table
3. **Required Artifacts:** Artifact verification table (from must_haves artifacts)
4. **Key Link Verification:** Wiring verification table (from must_haves key_links)
5. **Requirements Coverage:** If requirements defined
6. **Anti-Patterns Found:** Scan results table
7. **Human Verification Required:** Items needing human
8. **Gaps Summary:** Critical and non-critical gaps
9. **Recommended Fix Tasks:** If gaps_found
10. **Verification Metadata:** Approach, timing, counts
</step>

<step name="return_to_orchestrator">
**Return results to execute-phase orchestrator or /verify-milestone caller.**

**Return format:**

```markdown
## Verification Complete

**Status:** {passed | gaps_found | human_needed}
**Score:** {N}/{M} must-haves verified

{If passed:}
All must-haves verified. Phase goal achieved. Ready to proceed.

{If gaps_found:}
### Gaps Found

{N} critical gaps blocking goal achievement:
1. {Gap 1 summary}
2. {Gap 2 summary}

### Recommended Fixes

{N} fix tasks recommended:
1. task-{next-id}: {name}
2. task-{next-id+1}: {name}

### VGL Loop

Run `/verify-milestone` after fixes to re-verify.

{If human_needed:}
### Human Verification Required

{N} items need human testing:
1. {Item 1}
2. {Item 2}

Automated checks passed. Awaiting human verification.
```

The orchestrator will:
- If `passed`: Continue to update plan
- If `gaps_found`: Enter VGL loop -- create fix tasks, execute, then re-verify
- If `human_needed`: Present items to user, collect responses
</step>

</process>

<success_criteria>
- [ ] must_haves loaded from plan.yaml (truths, artifacts, key_links) or derived from phase goal
- [ ] All truths verified with status and evidence
- [ ] All artifacts checked at all three levels
- [ ] All key_links verified
- [ ] Requirements coverage assessed (if applicable)
- [ ] Anti-patterns scanned and categorized
- [ ] Human verification items identified
- [ ] Overall status determined
- [ ] Fix tasks generated (if gaps_found)
- [ ] Verification report created with complete results
- [ ] Results returned to orchestrator or /verify-milestone caller
</success_criteria>
