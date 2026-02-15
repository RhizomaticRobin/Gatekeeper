---
name: "gsd-vgl:map-codebase"
description: "Map existing codebase for brownfield projects"
allowed-tools:
  - Read
  - Bash
  - Task
  - Glob
  - Grep
---

# gsd-vgl:map-codebase — Codebase Analysis

You are a senior software architect performing a comprehensive codebase analysis. Your goal is to produce a complete map of an existing codebase so that future development work has full context. This is essential for brownfield projects where code already exists.

---

## Step 1: Initial Survey

Before spawning the mapper agent, perform a quick survey:

1. **Check for `.claude/plan/plan.yaml`** — load project context if available
2. **List top-level files and directories:**
   ```bash
   ls -la
   ```
3. **Identify the project type** from files present:
   - `package.json` → Node.js/JavaScript
   - `Cargo.toml` → Rust
   - `go.mod` → Go
   - `pyproject.toml` / `setup.py` / `requirements.txt` → Python
   - `pom.xml` / `build.gradle` → Java
   - `Gemfile` → Ruby
   - `*.sln` / `*.csproj` → .NET
4. **Count files by type** to understand codebase scale:
   ```bash
   find . -type f -name '*.{ext}' | wc -l
   ```
5. **Check for existing docs** that might accelerate analysis

---

## Step 2: Spawn Codebase Mapper Agent

Spawn a `codebase-mapper` agent via the Task tool with the full survey context:

```
Task: "You are a codebase-mapper agent. Analyze the codebase at {path} and produce comprehensive documentation.

Project type: {detected type}
File count: ~{N} source files

Perform the following analyses:

### A. Technology Stack Analysis
- Languages and versions
- Frameworks and libraries (with versions)
- Build tools and task runners
- Development dependencies vs. production dependencies
- Infrastructure-as-code or deployment tools

### B. Architecture Analysis
- Overall architecture pattern (monolith, microservices, serverless, etc.)
- Module/package structure and dependency graph
- Entry points (main files, route handlers, CLI entry)
- Data flow patterns
- State management approach
- Error handling patterns

### C. Directory Structure Analysis
- Purpose of each top-level directory
- File naming conventions
- Module organization pattern
- Asset/resource locations
- Configuration file locations

### D. Code Conventions Analysis
- Naming conventions (camelCase, snake_case, etc.)
- Import/module patterns
- Error handling style
- Logging approach
- Comment and documentation style
- Linting/formatting configuration

### E. Testing Analysis
- Test framework(s) in use
- Test file locations and naming
- Test coverage configuration
- Test categories (unit, integration, e2e)
- How to run tests

### F. Integration Analysis
- External API integrations
- Database connections and ORMs
- Authentication/authorization mechanisms
- Message queues or event systems
- File storage / CDN
- Third-party services

### G. Concerns & Tech Debt
- Obvious code smells or anti-patterns
- Deprecated dependencies
- Security concerns
- Performance bottlenecks (if apparent)
- Missing error handling
- Incomplete features or TODO markers

Write each analysis to the corresponding file in .planning/codebase/"
```

---

## Step 3: Create Output Files

Ensure the `.planning/codebase/` directory exists, then write each file:

### `.planning/codebase/STACK.md`
```markdown
# Technology Stack

## Languages
| Language | Version | Usage |
|----------|---------|-------|
| {lang} | {ver} | {primary/secondary} |

## Frameworks
| Framework | Version | Purpose |
|-----------|---------|---------|
| {name} | {ver} | {what it does} |

## Build & Dev Tools
- {tool}: {purpose}

## Infrastructure
- {tool/service}: {purpose}
```

### `.planning/codebase/ARCHITECTURE.md`
```markdown
# Architecture Overview

## Pattern
{monolith | microservices | serverless | ...}

## Component Diagram
{ASCII or text description of major components and their relationships}

## Entry Points
| Entry Point | File | Purpose |
|-------------|------|---------|
| {name} | {path} | {what it does} |

## Data Flow
{Description of how data moves through the system}

## Key Design Decisions
1. {decision}: {rationale}
```

### `.planning/codebase/STRUCTURE.md`
```markdown
# Directory Structure

## Top-Level Layout
```
{tree output, 2-3 levels deep}
```

## Directory Purposes
| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| {dir} | {purpose} | {notable files} |

## File Conventions
- Source files: {pattern}
- Test files: {pattern}
- Config files: {pattern}
```

### `.planning/codebase/CONVENTIONS.md`
```markdown
# Code Conventions

## Naming
- Variables: {convention}
- Functions: {convention}
- Classes/Types: {convention}
- Files: {convention}

## Patterns
- Imports: {style}
- Error handling: {approach}
- Logging: {framework and style}
- Async: {approach}

## Formatting
- Formatter: {tool}
- Linter: {tool}
- Config: {file}
```

### `.planning/codebase/TESTING.md`
```markdown
# Testing Overview

## Framework
{test framework and version}

## Running Tests
```bash
{command to run all tests}
{command to run specific tests}
```

## Test Structure
| Category | Location | Count |
|----------|----------|-------|
| Unit | {path} | ~{N} |
| Integration | {path} | ~{N} |
| E2E | {path} | ~{N} |

## Coverage
{coverage configuration and current metrics if available}
```

### `.planning/codebase/INTEGRATIONS.md`
```markdown
# External Integrations

## APIs
| Service | Purpose | Auth Method | Config Location |
|---------|---------|-------------|-----------------|
| {name} | {purpose} | {method} | {file} |

## Databases
| Database | ORM/Driver | Connection Config |
|----------|-----------|-------------------|
| {name} | {orm} | {file} |

## Other Services
{message queues, caches, CDNs, etc.}
```

### `.planning/codebase/CONCERNS.md`
```markdown
# Concerns & Tech Debt

## Critical
- {issue}: {description and recommendation}

## High Priority
- {issue}: {description and recommendation}

## Medium Priority
- {issue}: {description and recommendation}

## TODOs Found
| File | Line | TODO |
|------|------|------|
| {file} | {line} | {text} |
```

---

## Step 4: Summary

After all files are created, present a summary to the user:

> "Codebase mapped. Key findings:
> - **Stack:** {primary language} + {framework}
> - **Architecture:** {pattern}
> - **Size:** ~{N} source files across {M} directories
> - **Tests:** {test framework}, ~{N} test files
> - **Concerns:** {N} critical, {N} high priority
>
> Full analysis in `.planning/codebase/`. Next steps:
> - `gsd-vgl:quest` — create project plan informed by this analysis
> - `gsd-vgl:research` — investigate specific concerns or technologies
> - `gsd-vgl:cross-team` — begin execution"
