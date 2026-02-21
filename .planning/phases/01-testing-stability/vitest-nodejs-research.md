# Vitest for Node.js Testing — Research Findings

**Phase:** 01-testing-stability
**Requirement:** R-004 (test install.js and MCP launcher)
**Date:** 2025-02-11
**Targets:** `bin/install.js`, `hooks/intel-index.js`

---

## 1. Overview

Vitest is a Vite-powered test framework with Jest-compatible APIs. It supports Node.js
testing out of the box with `environment: 'node'`. Key advantages for this project:

- Native ESM support; can also test CommonJS files via Vite's transform pipeline
- Built-in mocking via `vi.mock()`, `vi.spyOn()`, `vi.fn()`
- Jest-compatible `describe/it/expect` API (no migration cost if switching from Jest)
- Fast startup, watch mode, parallel execution
- Requires **Node >= 20** and **Vite >= 6.0**

**Critical constraint:** `install.js` and `intel-index.js` are CommonJS (`require()`-based).
Vitest transforms CJS to ESM internally via Vite, but `vi.mock()` only intercepts
`import`-resolved modules, **not raw `require()` calls**. This means we must either:

1. Write tests using `import` syntax (vitest transforms CJS source automatically), or
2. Use manual mocking strategies (`__mocks__/` directory, `vi.hoisted()` with
   `require.cache` manipulation, or the `vitest-mock-commonjs` package)

The recommended path: **write test files as ESM** (`.test.js` with `import` syntax).
Vitest will resolve the CJS source through Vite's pipeline, making `vi.mock()` work
transparently.

---

## 2. Setup — vitest.config.js for Plain JS

### Install

```bash
npm install --save-dev vitest
```

### Config file: `vitest.config.js`

Vitest supports `.js`, `.mjs`, `.cjs`, `.ts`, `.cts`, `.mts` config extensions.
For a plain JS project without TypeScript:

```js
// vitest.config.js
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Use Node.js environment (not jsdom/happy-dom)
    environment: 'node',

    // Make describe/it/expect/vi available globally (no imports needed)
    globals: true,

    // Test file discovery patterns
    include: ['tests/**/*.test.js'],

    // Timeout for individual tests (ms)
    testTimeout: 10000,

    // Reset mocks between tests automatically
    restoreMocks: true,
  },
});
```

### package.json scripts

```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run",
    "test:coverage": "vitest run --coverage"
  }
}
```

**Note on `"type": "module"`:** The vitest.config.js file uses `import` syntax.
If the project's package.json does NOT have `"type": "module"`, rename the config
to `vitest.config.mjs`. Test files can use `.mjs` extension or the project can add
`"type": "module"` to package.json. Since gatekeeper currently has no `"type"` field
(defaults to CJS), the simplest approach is:

- Use `vitest.config.mjs` for the config file, OR
- Add `"type": "module"` to package.json (may affect other scripts)

The config file extension approach (`vitest.config.mjs`) is less invasive.

---

## 3. Project Structure Conventions

Two common patterns exist. For this project, a **separate test directory** is recommended
since the source files are organized by function (bin/, hooks/, commands/) rather than
as a library with src/:

```
gatekeeper/
  bin/
    install.js              # Source under test
  hooks/
    intel-index.js          # Source under test
  tests/
    bin/
      install.test.js       # Tests for install.js
    hooks/
      intel-index.test.js   # Tests for intel-index.js
    __mocks__/              # Optional: auto-mocks for node modules
      fs.cjs
      child_process.cjs
  vitest.config.mjs
  package.json
```

Alternative (co-located): place `install.test.js` next to `install.js` in `bin/`.
This works but clutters the published package since `bin/` is in the npm `"files"` list.
The separate `tests/` directory avoids that issue.

---

## 4. Key Mocking Patterns

### 4.1 vi.mock() — Module-Level Mocking

Replaces an entire module with a mock factory. **Calls are hoisted** to the top of the
file automatically, executing before any imports.

```js
import { vi, describe, it, expect } from 'vitest';

// Mock the entire 'fs' module
vi.mock('fs');

// Now all fs functions are vi.fn() stubs that return undefined
import fs from 'fs';

it('calls mkdirSync', () => {
  fs.mkdirSync('/tmp/test', { recursive: true });
  expect(fs.mkdirSync).toHaveBeenCalledWith('/tmp/test', { recursive: true });
});
```

### 4.2 vi.mock() with Factory — Custom Implementations

```js
vi.mock('fs', () => ({
  existsSync: vi.fn(() => true),
  mkdirSync: vi.fn(),
  readdirSync: vi.fn(() => []),
  copyFileSync: vi.fn(),
  readFileSync: vi.fn(() => '{}'),
  writeFileSync: vi.fn(),
  chmodSync: vi.fn(),
  rmSync: vi.fn(),
  unlinkSync: vi.fn(),
  lstatSync: vi.fn(() => ({
    isSymbolicLink: () => false,
    isDirectory: () => false,
  })),
}));
```

### 4.3 vi.spyOn() — Spy on Individual Methods

Does not replace the entire module. Wraps a single method to track calls while
optionally overriding behavior:

```js
import * as fs from 'fs';

const spy = vi.spyOn(fs, 'existsSync').mockReturnValue(true);

// Later:
expect(spy).toHaveBeenCalledWith('/some/path');
spy.mockRestore(); // Restore original implementation
```

### 4.4 vi.fn() — Standalone Mock Functions

```js
const mockCallback = vi.fn();
mockCallback('hello');
expect(mockCallback).toHaveBeenCalledWith('hello');
expect(mockCallback).toHaveBeenCalledTimes(1);
```

### 4.5 Partial Module Mocking (importOriginal)

Keep real implementations for some exports, mock others:

```js
vi.mock('fs', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    existsSync: vi.fn(() => true),   // Override only this
    // All other fs functions remain real
  };
});
```

### 4.6 Per-Test Mock Variations

Use `mockImplementation` or `mockReturnValue` inside individual tests to change
behavior per-test without re-declaring vi.mock:

```js
vi.mock('fs');
import fs from 'fs';

describe('verifyInstallation', () => {
  it('returns empty array when all files exist', () => {
    fs.existsSync.mockReturnValue(true);
    // ... test
  });

  it('returns missing files when some do not exist', () => {
    fs.existsSync.mockImplementation((p) => !p.includes('hooks.json'));
    // ... test
  });
});
```

---

## 5. Mocking fs (File System Operations)

### Strategy A: Manual vi.mock (Recommended for install.js)

install.js uses synchronous fs APIs (`existsSync`, `mkdirSync`, `readdirSync`,
`copyFileSync`, `chmodSync`, `rmSync`, `lstatSync`, `unlinkSync`, `writeFileSync`,
`readFileSync`). Mock them directly:

```js
vi.mock('fs', () => {
  return {
    existsSync: vi.fn(),
    mkdirSync: vi.fn(),
    readdirSync: vi.fn(() => []),
    copyFileSync: vi.fn(),
    chmodSync: vi.fn(),
    rmSync: vi.fn(),
    unlinkSync: vi.fn(),
    readFileSync: vi.fn(() => Buffer.from([])),
    writeFileSync: vi.fn(),
    lstatSync: vi.fn(() => ({
      isSymbolicLink: vi.fn(() => false),
      isDirectory: vi.fn(() => false),
    })),
  };
});
```

### Strategy B: memfs (In-Memory Filesystem)

Better for integration-style tests where you want realistic fs behavior:

```bash
npm install --save-dev memfs
```

Create `__mocks__/fs.cjs`:
```js
const { fs } = require('memfs');
module.exports = fs;
```

In tests:
```js
import { vi } from 'vitest';
import { fs, vol } from 'memfs';

vi.mock('fs');

beforeEach(() => {
  vol.reset();
});

it('copies plugin directory', () => {
  vol.fromJSON({
    '/src/file.js': 'content',
    '/src/hooks/hook.js': 'hook content',
  });

  copyPluginDirectory('/src', '/dest');

  expect(fs.existsSync('/dest/file.js')).toBe(true);
});
```

### Recommendation for install.js

Use **Strategy A** (manual vi.mock) for unit tests. The installer's fs operations are
straightforward copy/mkdir/chmod sequences. Manual mocks give precise control over
return values and make assertions clearer. Reserve memfs for integration tests if needed.

---

## 6. Mocking child_process.execSync

install.js calls `execSync` for git clone, npm install, npm run build, and
`claude mcp add`. Mock the entire module:

```js
vi.mock('child_process', () => ({
  execSync: vi.fn(),
}));

import { execSync } from 'child_process';
```

### Testing execSync Success

```js
it('clones MCP server repo when package.json missing', () => {
  fs.existsSync.mockImplementation((p) => {
    if (p.includes('package.json')) return false;
    return true;
  });

  execSync.mockReturnValue('');

  setupMcpServer('/dest/plugin');

  expect(execSync).toHaveBeenCalledWith(
    expect.stringContaining('git clone --depth 1'),
    expect.objectContaining({ stdio: 'pipe' })
  );
});
```

### Testing execSync Failure

```js
it('handles git clone failure gracefully', () => {
  fs.existsSync.mockReturnValue(false);

  const error = new Error('git failed');
  error.stderr = Buffer.from('fatal: repository not found');
  execSync.mockImplementation(() => { throw error; });

  const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

  // Should not throw — function handles error internally
  setupMcpServer('/dest/plugin');

  expect(consoleSpy).toHaveBeenCalledWith(
    expect.stringContaining('Failed to clone')
  );
});
```

### Testing Sequential execSync Calls

Use `mockImplementationOnce` to simulate different results for each call:

```js
it('runs npm install then npm run build', () => {
  fs.existsSync.mockReturnValue(true);

  execSync
    .mockReturnValueOnce('')  // npm install
    .mockReturnValueOnce('')  // npm run build
    .mockReturnValueOnce(''); // claude mcp add

  setupMcpServer('/dest/plugin');

  expect(execSync).toHaveBeenCalledTimes(3);
  expect(execSync).toHaveBeenNthCalledWith(1,
    'npm install --production=false',
    expect.objectContaining({ cwd: expect.stringContaining('mcp-server') })
  );
});
```

---

## 7. Testing readline Interactive Prompts

install.js uses `readline.createInterface` for the interactive location prompt.
The key challenge: readline creates an async question/answer flow.

### Strategy: Mock readline.createInterface

```js
vi.mock('readline', () => {
  const mockRl = {
    question: vi.fn(),
    close: vi.fn(),
    on: vi.fn(),
  };
  return {
    createInterface: vi.fn(() => mockRl),
    // Expose for test access
    __mockRl: mockRl,
  };
});

import readline from 'readline';
```

### Testing the Prompt

```js
it('installs globally when user selects 1', () => {
  const mockRl = readline.__mockRl;

  // Simulate user typing "1" and pressing Enter
  mockRl.question.mockImplementation((prompt, callback) => {
    callback('1');
  });

  promptLocation();

  expect(mockRl.question).toHaveBeenCalled();
  // Assert install was called with isGlobal=true
});

it('installs locally when user selects 2', () => {
  const mockRl = readline.__mockRl;

  mockRl.question.mockImplementation((prompt, callback) => {
    callback('2');
  });

  promptLocation();
  // Assert install was called with isGlobal=false
});

it('defaults to global on empty input', () => {
  const mockRl = readline.__mockRl;

  mockRl.question.mockImplementation((prompt, callback) => {
    callback('');  // Empty = default = "1" = global
  });

  promptLocation();
});
```

### Testing Non-TTY Fallback

install.js checks `process.stdin.isTTY`:

```js
it('defaults to global install in non-interactive mode', () => {
  const originalIsTTY = process.stdin.isTTY;
  Object.defineProperty(process.stdin, 'isTTY', { value: false, writable: true });

  promptLocation();
  // Assert global install was triggered

  Object.defineProperty(process.stdin, 'isTTY', { value: originalIsTTY, writable: true });
});
```

---

## 8. Handling process.exit() in Tests

install.js calls `process.exit(0)` and `process.exit(1)` in multiple places.
Without mocking, this would terminate the test runner.

### Approach A: vi.spyOn (Simplest)

```js
const mockExit = vi.spyOn(process, 'exit').mockImplementation(() => {});

it('exits with 0 on --help', () => {
  // trigger help flow
  expect(mockExit).toHaveBeenCalledWith(0);
});

it('exits with 1 on conflicting flags', () => {
  // trigger --global --local
  expect(mockExit).toHaveBeenCalledWith(1);
});

afterEach(() => {
  mockExit.mockRestore();
});
```

**Important caveat:** `mockImplementation(() => {})` prevents the real exit, but
code after `process.exit()` **continues executing** since the mock returns `undefined`
instead of terminating. This can cause unexpected behavior if the code relies on
`process.exit()` halting execution.

### Approach B: Throw to Halt Execution

```js
const mockExit = vi.spyOn(process, 'exit').mockImplementation((code) => {
  throw new Error(`process.exit(${code})`);
});

it('exits with 1 on missing config-dir value', () => {
  expect(() => {
    parseConfigDirArg(); // with bad args
  }).toThrow('process.exit(1)');
});
```

This better simulates real behavior: code after `process.exit()` does NOT run.
The test catches the thrown error via `expect().toThrow()`.

### Approach C: vitest-mock-process Package

```bash
npm install --save-dev vitest-mock-process
```

```js
import { mockProcessExit } from 'vitest-mock-process';

it('exits cleanly on help', () => {
  const mockExit = mockProcessExit();

  // trigger help
  expect(mockExit).toHaveBeenCalledWith(0);
  mockExit.mockRestore();
});
```

### Recommendation

Use **Approach B** (throw on exit) as the default pattern for install.js tests.
Most process.exit calls in install.js are terminal — no code should run after them.
Throwing ensures tests accurately reflect that behavior.

---

## 9. Testing install.js — Structural Considerations

install.js has a significant architectural challenge for testing: **much of the logic
runs at module-load time** (top-level code). The arg parsing, banner printing,
`parseConfigDirArg()`, and the main if/else dispatch all execute on `require()`/`import`.

### Problem: Top-Level Side Effects

```js
// These run immediately when the module is loaded:
const args = process.argv.slice(2);        // line 33
const hasGlobal = args.includes('--global'); // line 34
console.log(banner);                        // line 62
const explicitConfigDir = parseConfigDirArg(); // line 60
// ... main dispatch at line 382-394
```

### Solution A: Dynamic Import in Each Test

```js
it('shows help and exits on --help', async () => {
  process.argv = ['node', 'install.js', '--help'];
  const mockExit = vi.spyOn(process, 'exit').mockImplementation((code) => {
    throw new Error(`exit:${code}`);
  });

  try {
    await import('../bin/install.js');
  } catch (e) {
    expect(e.message).toBe('exit:0');
  }

  expect(mockExit).toHaveBeenCalledWith(0);
});
```

**Problem:** Vitest caches modules. Repeated `import()` calls return the cached
module. Use `vi.resetModules()` before each test:

```js
beforeEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
});
```

### Solution B: Refactor for Testability (Recommended Long-Term)

Extract the pure functions into a separate module that can be imported and tested
without side effects:

```
bin/
  install.js          # Entry point (thin wrapper, calls main())
  install-lib.js      # Exported functions: copyPluginDirectory, verifyInstallation, etc.
```

Then test `install-lib.js` functions directly:

```js
import { copyPluginDirectory, verifyInstallation, makeScriptsExecutable } from '../bin/install-lib.js';
```

This is the cleaner approach but requires a minor refactor of install.js.

### Solution C: Test Exported Functions Where Possible

For now, without refactoring, focus on testing the individual functions that are
defined but can be exercised through careful module loading with controlled
process.argv and mocked dependencies.

---

## 10. Example Test Patterns for install.js Functions

### Testing copyPluginDirectory

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('fs');
import fs from 'fs';

// We need to access the function — either export it or use dynamic import
// Assuming a refactored install-lib.js exports it:

describe('copyPluginDirectory', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('creates destination directory', () => {
    fs.mkdirSync.mockImplementation(() => {});
    fs.readdirSync.mockReturnValue([]);

    copyPluginDirectory('/src', '/dest');

    expect(fs.mkdirSync).toHaveBeenCalledWith('/dest', { recursive: true });
  });

  it('copies files recursively', () => {
    fs.mkdirSync.mockImplementation(() => {});
    fs.readdirSync
      .mockReturnValueOnce([
        { name: 'file.js', isDirectory: () => false },
        { name: 'subdir', isDirectory: () => true },
      ])
      .mockReturnValueOnce([
        { name: 'nested.js', isDirectory: () => false },
      ]);
    fs.copyFileSync.mockImplementation(() => {});

    copyPluginDirectory('/src', '/dest');

    expect(fs.copyFileSync).toHaveBeenCalledWith('/src/file.js', '/dest/file.js');
    expect(fs.copyFileSync).toHaveBeenCalledWith('/src/subdir/nested.js', '/dest/subdir/nested.js');
  });

  it('excludes node_modules and .git', () => {
    fs.mkdirSync.mockImplementation(() => {});
    fs.readdirSync.mockReturnValue([
      { name: 'node_modules', isDirectory: () => true },
      { name: '.git', isDirectory: () => true },
      { name: 'keep.js', isDirectory: () => false },
    ]);
    fs.copyFileSync.mockImplementation(() => {});

    copyPluginDirectory('/src', '/dest');

    expect(fs.copyFileSync).toHaveBeenCalledTimes(1);
    expect(fs.copyFileSync).toHaveBeenCalledWith('/src/keep.js', '/dest/keep.js');
  });
});
```

### Testing verifyInstallation

```js
describe('verifyInstallation', () => {
  it('returns empty array when all required files exist', () => {
    fs.existsSync.mockReturnValue(true);

    const failures = verifyInstallation('/plugin');

    expect(failures).toEqual([]);
  });

  it('returns missing files', () => {
    fs.existsSync.mockImplementation((p) => {
      return !p.includes('hooks.json');
    });

    const failures = verifyInstallation('/plugin');

    expect(failures).toContain('hooks/hooks.json');
  });
});
```

### Testing makeScriptsExecutable

```js
describe('makeScriptsExecutable', () => {
  it('chmods .sh files to 755', () => {
    fs.readdirSync.mockReturnValue([
      { name: 'script.sh', isDirectory: () => false },
      { name: 'readme.md', isDirectory: () => false },
    ]);
    fs.chmodSync.mockImplementation(() => {});

    const count = makeScriptsExecutable('/plugin');

    expect(fs.chmodSync).toHaveBeenCalledWith(
      expect.stringContaining('script.sh'),
      0o755
    );
    expect(count).toBe(1);
  });

  it('chmods .js files under hooks/ subtree', () => {
    fs.readdirSync
      .mockReturnValueOnce([
        { name: 'hooks', isDirectory: () => true },
      ])
      .mockReturnValueOnce([
        { name: 'intel-index.js', isDirectory: () => false },
      ]);
    fs.chmodSync.mockImplementation(() => {});

    const count = makeScriptsExecutable('/plugin');

    expect(fs.chmodSync).toHaveBeenCalledWith(
      expect.stringContaining('intel-index.js'),
      0o755
    );
    expect(count).toBe(1);
  });
});
```

### Testing expandTilde

```js
describe('expandTilde', () => {
  it('expands ~/path to homedir/path', () => {
    const result = expandTilde('~/foo/bar');
    expect(result).toBe(path.join(os.homedir(), 'foo/bar'));
  });

  it('returns non-tilde paths unchanged', () => {
    expect(expandTilde('/absolute/path')).toBe('/absolute/path');
  });

  it('returns null/undefined as-is', () => {
    expect(expandTilde(null)).toBeNull();
  });
});
```

---

## 11. Testing intel-index.js

### Key Differences from install.js

- Uses `sql.js` (async initialization via `initSqlJs()`)
- Has async functions (`loadGraphDatabase`, `generateEntity`, `syncEntityToGraph`)
- Reads from stdin (standard hook pattern)
- Pure functions like `extractImports`, `extractExports`, `detectCase` are easily testable

### Pure Function Tests (No Mocking Needed)

```js
describe('extractImports', () => {
  it('extracts ES6 named imports', () => {
    const content = "import { foo, bar } from './utils';";
    expect(extractImports(content)).toContain('./utils');
  });

  it('extracts CommonJS requires', () => {
    const content = "const fs = require('fs');";
    expect(extractImports(content)).toContain('fs');
  });
});

describe('extractExports', () => {
  it('extracts named exports', () => {
    const content = "export function hello() {}";
    expect(extractExports(content)).toContain('hello');
  });

  it('extracts CommonJS module.exports', () => {
    const content = "module.exports = { foo, bar };";
    const exports = extractExports(content);
    expect(exports).toContain('foo');
    expect(exports).toContain('bar');
  });
});

describe('detectCase', () => {
  it('detects camelCase', () => {
    expect(detectCase('myFunction')).toBe('camelCase');
  });

  it('detects PascalCase', () => {
    expect(detectCase('MyComponent')).toBe('PascalCase');
  });

  it('detects SCREAMING_SNAKE', () => {
    expect(detectCase('MAX_VALUE')).toBe('SCREAMING_SNAKE');
  });
});

describe('generateSlug', () => {
  it('converts file path to slug', () => {
    expect(generateSlug('src/lib/db.ts')).toBe('src-lib-db');
  });
});
```

### Mocking sql.js

```js
vi.mock('sql.js/dist/sql-asm.js', () => {
  const mockDb = {
    run: vi.fn(),
    exec: vi.fn(() => []),
    prepare: vi.fn(() => ({
      run: vi.fn(),
      free: vi.fn(),
    })),
    export: vi.fn(() => new Uint8Array()),
    close: vi.fn(),
  };

  const MockDatabase = vi.fn(() => mockDb);

  return {
    default: vi.fn(async () => ({
      Database: MockDatabase,
    })),
  };
});
```

---

## 12. Gotchas and Pitfalls

### 12.1 vi.mock is Hoisted

`vi.mock()` calls are hoisted to the top of the file, even if written below imports.
This means you cannot use variables declared in the test file inside the mock factory
unless you wrap them with `vi.hoisted()`:

```js
// WRONG: myValue is not available inside the hoisted mock
const myValue = 'test';
vi.mock('fs', () => ({ readFileSync: vi.fn(() => myValue) })); // Error!

// RIGHT: Use vi.hoisted()
const { myValue } = vi.hoisted(() => {
  return { myValue: 'test' };
});
vi.mock('fs', () => ({ readFileSync: vi.fn(() => myValue) }));
```

### 12.2 Module Caching with Dynamic Import

When using `await import('./module.js')` in tests, Vitest caches the module.
Subsequent imports return the same cached module. Always call `vi.resetModules()`
before each test that needs a fresh module load:

```js
beforeEach(() => {
  vi.resetModules();
});
```

### 12.3 process.exit Mock Doesn't Stop Execution

When you mock `process.exit()` with `mockImplementation(() => {})`, the code
after the exit call **continues running**. This can cause:
- Multiple assertions firing unexpectedly
- Cascading errors from code that was never meant to execute
- False test passes

Use the throw pattern instead:
```js
vi.spyOn(process, 'exit').mockImplementation((code) => {
  throw new Error(`process.exit(${code})`);
});
```

### 12.4 process.argv Pollution

When testing CLI argument parsing, always save and restore `process.argv`:

```js
let originalArgv;

beforeEach(() => {
  originalArgv = process.argv;
});

afterEach(() => {
  process.argv = originalArgv;
});
```

### 12.5 __dirname and __filename in CJS under Vitest

Vitest transforms CJS to ESM. The `__dirname` and `__filename` globals from CJS
may not behave identically. install.js uses `path.join(__dirname, '..')` to find
the project root. This needs to be accounted for in tests — either by mocking
the path resolution or by setting up the test to provide the expected directory
structure.

### 12.6 Top-Level Code Execution

install.js runs significant logic at the top level (arg parsing, banner, dispatch).
This means importing the module triggers side effects. Use `vi.resetModules()` +
dynamic `import()` for each test that needs different argv or env values.

### 12.7 Console Output Noise

install.js uses `console.log` and `console.error` extensively. Mock them to keep
test output clean and to assert on output:

```js
vi.spyOn(console, 'log').mockImplementation(() => {});
vi.spyOn(console, 'error').mockImplementation(() => {});
```

### 12.8 os.homedir() in Tests

install.js uses `os.homedir()` for path resolution. Mock it for deterministic
test paths:

```js
vi.spyOn(os, 'homedir').mockReturnValue('/mock/home');
```

### 12.9 Environment Variables

install.js reads `process.env.CLAUDE_CONFIG_DIR`. Set and restore it per-test:

```js
const originalEnv = process.env.CLAUDE_CONFIG_DIR;
afterEach(() => {
  if (originalEnv === undefined) {
    delete process.env.CLAUDE_CONFIG_DIR;
  } else {
    process.env.CLAUDE_CONFIG_DIR = originalEnv;
  }
});
```

Or use `vi.stubEnv()`:
```js
vi.stubEnv('CLAUDE_CONFIG_DIR', '/custom/config');
// Automatically restored if restoreMocks is true in config
```

### 12.10 Vitest Requires Node >= 20

The current project declares `"engines": { "node": ">=16.7.0" }`. Vitest 3.x
requires Node >= 20. This only affects the dev/test environment, not the
runtime requirement for end users. Document this in contributing guidelines.

---

## 13. Recommended Test Implementation Plan

### Priority 1: Pure function unit tests (no mocking needed)
- `expandTilde`
- `extractImports`, `extractExports`
- `detectCase`, `generateSlug`
- `parseEntityFrontmatter`, `extractWikiLinks`, `extractPurpose`
- `signatureChanged`
- `detectConventions`, `generateSummary`

### Priority 2: Core install functions (fs mocking)
- `copyPluginDirectory`
- `makeScriptsExecutable`
- `verifyInstallation`
- `isSymlink`

### Priority 3: Integration-style tests (fs + child_process + process.exit)
- `install()` function flow
- `setupMcpServer()` happy path and error handling
- `parseConfigDirArg()` with various argv configurations
- `promptLocation()` with readline mock

### Priority 4: intel-index.js database operations (sql.js mock)
- `loadGraphDatabase`
- `syncEntityToGraph`
- `getHotspots`, `getDependents`, `getNodesByType`
- `updateIndex`

---

## 14. Sources

- [Vitest Getting Started](https://vitest.dev/guide/)
- [Vitest Configuration](https://vitest.dev/config/)
- [Vitest Mocking Guide](https://vitest.dev/guide/mocking)
- [Vitest Mocking the File System](https://vitest.dev/guide/mocking/file-system)
- [Vitest Mocking Modules](https://vitest.dev/guide/mocking/modules)
- [Vitest Vi API (vi.mock, vi.spyOn)](https://vitest.dev/api/vi)
- [Mock child_process.exec in Vitest (Gist)](https://gist.github.com/joemaller/f9171aa19a187f59f406ef1ffe87d9ac)
- [vitest-mock-process](https://github.com/leonsilicon/vitest-mock-process)
- [Cannot Mock process.exit — Issue #5400](https://github.com/vitest-dev/vitest/issues/5400)
- [Mocking require() modules — Discussion #3134](https://github.com/vitest-dev/vitest/discussions/3134)
- [Vitest Best Practices](https://www.projectrules.ai/rules/vitest)
- [Test File Organization Strategies](https://app.studyraid.com/en/read/11292/352301/test-file-organization-strategies)
- [How to Setup Vitest for Node.js](https://casperiv.dev/blog/how-to-setup-vitest)
