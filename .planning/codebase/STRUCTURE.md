# Directory Structure

```
gsd-vgl/
├── .claude-plugin/
│   ├── plugin.json              Plugin manifest + MCP server declaration
│   └── marketplace.json         Self-contained marketplace definition
├── .gitmodules                  Submodule: Better-OpenCodeMCP
├── package.json                 npm config (v1.0.0, bin: gsd-vgl → install.js)
├── README.md
│
├── Better-OpenCodeMCP/          Submodule — opencode MCP server (TypeScript)
│
├── agents/                      9 agent definitions
│   ├── executor.md              TDD-first execution + opencode concurrency
│   ├── verifier.md              Independent verification + cryptographic token
│   ├── planner.md               Plan generation with must_haves
│   ├── plan-checker.md          Pre-execution plan quality gate
│   ├── integration-checker.md   Cross-phase wiring verification
│   ├── project-researcher.md    Domain research
│   ├── phase-researcher.md      Phase-specific technical deep dives
│   ├── codebase-mapper.md       Brownfield codebase analysis
│   └── debugger.md              Scientific method debugging
│
├── bin/
│   ├── install.js               npx installer (legacy fallback)
│   ├── opencode-mcp.sh          MCP server launcher (auto-builds)
│   ├── ralph.sh                 Autopilot outer loop
│   └── lib/                     Shell libraries (state, budget, display, ...)
│
├── commands/                    14 slash commands
│   ├── quest.md                 Plan generation (6-phase discovery)
│   ├── cross-team.md            Task execution (single or team)
│   ├── bridge.md                Standalone VGL for ad-hoc tasks
│   ├── autopilot.md             Launch Ralph outer loop
│   ├── new-project.md           Project initialization
│   ├── research.md              Domain research
│   ├── map-codebase.md          Codebase analysis
│   ├── progress.md              Status dashboard
│   ├── verify-milestone.md      Integration verification
│   ├── debug.md                 Systematic debugging
│   ├── settings.md              Configuration
│   ├── run-away.md              Cancel VGL loop
│   ├── help.md                  Command reference
│   └── cross.md                 [DEPRECATED]
│
├── hooks/
│   ├── hooks.json               Event registration (Stop, PreToolUse, PostToolUse)
│   ├── stop-hook.sh             VGL loop control + auto-transition
│   ├── guard-skills.sh          Block commands during active VGL
│   ├── post-cross.sh            Pipeline progress after /cross-team
│   └── intel-index.js           Codebase intelligence (dependency graph)
│
├── scripts/
│   ├── plan_utils.py            Shared plan utilities (load, save, find, sort)
│   ├── validate-plan.py         Plan structure validation
│   ├── next-task.py             Find next unblocked task
│   ├── get-unblocked-tasks.py   All unblocked tasks
│   ├── check-file-conflicts.py  File scope conflict detection
│   ├── parse-args.py            Argument parser for /bridge
│   ├── build-hooks.js           esbuild bundler for hooks
│   ├── cross-team-setup.sh      Orchestration setup
│   ├── setup-verifier-loop.sh   Initialize VGL state + token
│   ├── generate-verifier-prompt.sh  Build immutable verifier prompt
│   ├── fetch-completion-token.sh    Independent test execution for token
│   ├── transition-task.sh       Mark complete + find next task
│   └── team-orchestrator-prompt.md  Lead orchestrator template
│
├── templates/
│   ├── opencode.json            gsd-builder agent config
│   ├── config.json              Default project configuration
│   ├── project.md               .planning/project.md template
│   ├── requirements.md          .planning/requirements.md template
│   ├── roadmap.md               .planning/roadmap.md template
│   ├── state.md                 .planning/state.md template
│   ├── task-prompt.md           task-{id}.md template
│   ├── plan-summary.md          Plan summary template
│   └── codebase/                7-dimension analysis templates
│
├── references/
│   ├── tdd-opencode-workflow.md TDD + concurrent execution reference
│   ├── verification-patterns.md Artifact verification strategies
│   ├── model-profiles.md        Model selection & routing
│   └── git-integration.md       Git commit strategy
│
└── workflows/
    ├── discovery-phase.md       Discovery phase workflow
    ├── execute-phase.md         Execution phase workflow
    └── verify-phase.md          Verification phase workflow
```

## File Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Commands | kebab-case.md | cross-team.md |
| Agents | kebab-case.md | integration-checker.md |
| Shell scripts | kebab-case.sh | transition-task.sh |
| Python scripts | snake_case.py or kebab-case.py | plan_utils.py |
| Config files | lowercase.json | opencode.json |
| Planning docs | UPPERCASE.md | PROJECT.md, STATE.md |
