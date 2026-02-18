# Structure

## Top-Level Layout
```
gatekeeper/
├── .claude-plugin/           Plugin manifest (Claude Code plugin system)
│   ├── plugin.json           Name, version, MCP server declaration
│   └── marketplace.json      Self-contained marketplace definition
├── .claude/                  Active plan state (per-project, git-tracked)
│   └── plan/
│       ├── plan.yaml         Current plan with phases/tasks/statuses
│       └── tasks/            Per-task prompt files (task-{id}.md)
├── .planning/                Project management state
│   ├── PROJECT.md            Vision, problem, success criteria
│   ├── STATE.md              Execution progress tracker
│   ├── config.json           Project config (model_profile, workflow settings)
│   ├── codebase/             7-dimension codebase analysis output
│   ├── milestones/           Phase milestone records
│   ├── phases/               Phase-level planning artifacts
│   ├── evolution/            Per-task evolutionary population DBs
│   ├── history/              Task execution history (runs.jsonl)
│   └── learnings.jsonl       Extracted learnings from verifier feedback
├── agents/                   9 agent definitions (.md with YAML frontmatter)
├── bin/                      Entry points and runtime scripts
│   ├── install.js            CLI installer (npx gatekeeper)
│   ├── install-lib.js        Extracted testable functions from install.js
│   ├── opencode-mcp.sh       MCP server launcher (auto-builds submodule)
│   ├── ralph.sh              Autopilot outer loop (~550 lines)
│   └── lib/                  Shell libraries for ralph.sh
│       ├── state.sh           State machine management (~875 lines)
│       ├── learnings.sh       Learnings integration for autopilot
│       ├── budget.sh          Budget tracking and caps
│       ├── checkpoint.sh      Git checkpoint commits
│       ├── display.sh         Terminal output formatting
│       ├── exit.sh            Exit handling and cleanup
│       ├── failfast.sh        Failure detection
│       ├── invoke.sh          Claude CLI invocation
│       ├── mode.sh            Operating mode selection
│       ├── parse.sh           Output parsing
│       ├── path-resolve.sh    Path resolution utilities
│       ├── planning.sh        Planning file management
│       ├── recovery.sh        Error recovery
│       ├── progress-watcher.js   Progress monitoring (Node.js)
│       └── terminal-launcher.js  Terminal window management (Node.js)
├── commands/                 15 slash commands (.md with frontmatter)
├── hooks/                    4 hook scripts + hooks.json registration
│   ├── hooks.json            Event->script mapping (Stop, PreToolUse, PostToolUse)
│   ├── stop-hook.sh          VGL loop control + auto-transition (~400 lines)
│   ├── guard-skills.sh       Skill blocker during VGL
│   ├── post-cross.sh         Post-execution pipeline info
│   └── intel-index.js        Codebase intelligence indexer (bundled with sql.js)
├── scripts/                  Core orchestration scripts
│   ├── setup-verifier-loop.sh     Initialize VGL state + token
│   ├── generate-verifier-prompt.sh Build immutable verifier prompt
│   ├── fetch-completion-token.sh  Independent test execution for token grant
│   ├── transition-task.sh         Mark complete + find next task
│   ├── cross-team-setup.sh        Plan validation + task dispatch setup
│   ├── single-task-setup.sh       Single-task VGL initialization
│   ├── validate-plan.py           Plan.yaml structural validation
│   ├── plan_utils.py              Shared plan utilities (load, save, find, sort, lock)
│   ├── next-task.py               Find next unblocked task
│   ├── get-unblocked-tasks.py     Find all unblocked tasks
│   ├── check-file-conflicts.py    Detect file scope overlaps for safe parallelism
│   ├── parse-args.py              Argument parser for /bridge
│   ├── evo_db.py                  MAP-Elites population database
│   ├── evo_eval.py                Cascade evaluation (3-stage: collect, partial, full)
│   ├── evo_prompt.py              Evolution prompt builder (5-section markdown)
│   ├── evo_pollinator.py          Cross-task strategy pollination
│   ├── run_history.py             JSONL-based run history database
│   ├── learnings.py               Learnings extract/store/query/strategy
│   ├── onboarding.sh              First-run welcome message
│   ├── build-hooks.js             esbuild bundler for hook scripts
│   └── team-orchestrator-prompt.md Lead orchestrator template
├── templates/                Template files for project initialization
│   ├── opencode.json         gsd-builder agent config (deployed to project root)
│   ├── task-prompt.md        task-{id}.md template
│   ├── plan-summary.md       Plan summary template
│   ├── project.md            .planning/PROJECT.md template
│   ├── requirements.md       .planning/requirements.md template
│   ├── roadmap.md            .planning/roadmap.md template
│   ├── state.md              .planning/STATE.md template
│   ├── config.json           Default .planning/config.json
│   └── codebase/             7-dimension analysis templates
├── references/               Reference docs for agents
│   ├── tdd-opencode-workflow.md    TDD + concurrent execution patterns
│   ├── verification-patterns.md   Artifact verification strategies
│   ├── model-profiles.md          Model selection per agent per profile
│   └── git-integration.md         Git commit strategy
├── workflows/                Workflow phase documentation
│   ├── discovery-phase.md    6-phase discovery process
│   ├── execute-phase.md      Execution workflow details
│   └── verify-phase.md       Verification workflow details
├── Better-OpenCodeMCP/       Git submodule — opencode MCP server
├── tests/                    Test suite (385 tests across 3 frameworks)
└── package.json              npm config, scripts, dependencies
```

## Key Entry Points
- **Plugin registration:** `.claude-plugin/plugin.json` (loaded by Claude Code)
- **User commands:** `commands/*.md` (registered as slash commands)
- **Agent definitions:** `agents/*.md` (agent profiles with tool restrictions)
- **Hook dispatch:** `hooks/hooks.json` -> hook scripts
- **Autopilot:** `bin/ralph.sh` (standalone outer loop)
- **MCP server:** `bin/opencode-mcp.sh` -> `Better-OpenCodeMCP/dist/index.js`
- **Installer:** `bin/install.js` (npx entry point)

## File Naming Conventions
- Agent definitions: `{role-name}.md` (kebab-case)
- Commands: `{command-name}.md` (kebab-case)
- Shell scripts: `{verb-noun}.sh` (kebab-case)
- Python scripts: `{module_name}.py` (snake_case)
- Task prompts: `task-{phase.task}.md` (e.g., task-1.1.md)
