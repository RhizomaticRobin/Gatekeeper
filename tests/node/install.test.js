import { describe, it, expect, vi, beforeEach } from 'vitest';
import path from 'path';

// Suppress console output during tests
vi.spyOn(console, 'log').mockImplementation(() => {});
vi.spyOn(console, 'error').mockImplementation(() => {});

// Import the library module directly (pure functions with DI)
const lib = await import('../../bin/install-lib.js');
const { copyPluginDirectory, verifyInstallation, setupMcpServer } = lib.default || lib;

describe('install.js', () => {
  let mockFs;
  let mockExecSync;

  beforeEach(() => {
    vi.clearAllMocks();

    // Create fresh mock fs for each test
    mockFs = {
      mkdirSync: vi.fn(),
      readdirSync: vi.fn().mockReturnValue([]),
      copyFileSync: vi.fn(),
      existsSync: vi.fn().mockReturnValue(false),
      lstatSync: vi.fn(),
      unlinkSync: vi.fn(),
      rmSync: vi.fn(),
      chmodSync: vi.fn(),
    };

    mockExecSync = vi.fn().mockReturnValue(Buffer.from(''));
  });

  // ── copyPluginDirectory ──────────────────────────────────────────────

  describe('copyPluginDirectory', () => {
    it('creates the target directory', () => {
      copyPluginDirectory(mockFs, '/src', '/dest');

      expect(mockFs.mkdirSync).toHaveBeenCalledWith('/dest', { recursive: true });
    });

    it('copies all files from source', () => {
      mockFs.readdirSync.mockReturnValue([
        { name: 'file1.txt', isDirectory: () => false },
        { name: 'file2.js', isDirectory: () => false },
      ]);

      copyPluginDirectory(mockFs, '/src', '/dest');

      expect(mockFs.copyFileSync).toHaveBeenCalledWith(
        path.join('/src', 'file1.txt'),
        path.join('/dest', 'file1.txt'),
      );
      expect(mockFs.copyFileSync).toHaveBeenCalledWith(
        path.join('/src', 'file2.js'),
        path.join('/dest', 'file2.js'),
      );
    });

    it('handles nested directories', () => {
      mockFs.readdirSync
        .mockReturnValueOnce([
          { name: 'subdir', isDirectory: () => true },
        ])
        .mockReturnValueOnce([
          { name: 'nested.txt', isDirectory: () => false },
        ]);

      copyPluginDirectory(mockFs, '/src', '/dest');

      expect(mockFs.mkdirSync).toHaveBeenCalledWith('/dest', { recursive: true });
      expect(mockFs.mkdirSync).toHaveBeenCalledWith(
        path.join('/dest', 'subdir'),
        { recursive: true },
      );
      expect(mockFs.copyFileSync).toHaveBeenCalledWith(
        path.join('/src', 'subdir', 'nested.txt'),
        path.join('/dest', 'subdir', 'nested.txt'),
      );
    });

    it('skips node_modules and .git', () => {
      mockFs.readdirSync.mockReturnValue([
        { name: 'node_modules', isDirectory: () => true },
        { name: '.git', isDirectory: () => true },
        { name: 'keep.js', isDirectory: () => false },
      ]);

      copyPluginDirectory(mockFs, '/src', '/dest');

      expect(mockFs.copyFileSync).toHaveBeenCalledTimes(1);
      expect(mockFs.copyFileSync).toHaveBeenCalledWith(
        path.join('/src', 'keep.js'),
        path.join('/dest', 'keep.js'),
      );
      expect(mockFs.mkdirSync).toHaveBeenCalledTimes(1);
    });
  });

  // ── verifyInstallation ───────────────────────────────────────────────

  describe('verifyInstallation', () => {
    it('passes with all required files present', () => {
      mockFs.existsSync.mockReturnValue(true);

      const failures = verifyInstallation(mockFs, '/plugin');

      expect(failures).toEqual([]);
    });

    it('fails with missing file', () => {
      mockFs.existsSync.mockImplementation((filePath) => {
        if (filePath.includes('.claude-plugin/plugin.json')) return false;
        return true;
      });

      const failures = verifyInstallation(mockFs, '/plugin');

      expect(failures).toContain('.claude-plugin/plugin.json');
      expect(failures.length).toBe(1);
    });

    it('checks all entries in requiredFiles array', () => {
      mockFs.existsSync.mockReturnValue(false);

      const failures = verifyInstallation(mockFs, '/plugin');

      expect(failures).toContain('.claude-plugin/plugin.json');
      expect(failures).toContain('hooks/hooks.json');
      expect(failures).toContain('commands/help.md');
      expect(failures).toContain('agents/verifier.md');
      expect(failures).toContain('templates/opencode.json');
      expect(failures.length).toBe(5);
    });
  });

  // ── setupMcpServer ──────────────────────────────────────────────────

  describe('setupMcpServer', () => {
    it('clones submodule when package.json is missing', () => {
      mockFs.existsSync.mockImplementation((p) => {
        if (p.includes('package.json')) return false;
        if (p.includes('dist/index.js')) return true;
        return false;
      });

      setupMcpServer(mockFs, mockExecSync, '/plugin');

      const cloneCall = mockExecSync.mock.calls.find(
        (call) => typeof call[0] === 'string' && call[0].includes('git clone'),
      );
      expect(cloneCall).toBeTruthy();
      expect(cloneCall[0]).toContain('Better-OpenCodeMCP');
    });

    it('runs npm install and build', () => {
      mockFs.existsSync.mockImplementation((p) => {
        if (p.includes('package.json')) return true;
        if (p.includes('dist/index.js')) return true;
        return false;
      });

      setupMcpServer(mockFs, mockExecSync, '/plugin');

      const calls = mockExecSync.mock.calls.map((c) => c[0]);
      expect(calls).toContain('npm install --production=false');
      expect(calls.some((c) => c === 'npm run build')).toBe(true);
    });

    it('calls claude mcp add with correct args', () => {
      mockFs.existsSync.mockImplementation((p) => {
        if (p.includes('package.json')) return true;
        if (p.includes('dist/index.js')) return true;
        return false;
      });

      setupMcpServer(mockFs, mockExecSync, '/plugin');

      const calls = mockExecSync.mock.calls.map((c) => c[0]);
      const mcpAddCall = calls.find((c) => c.includes('claude mcp add'));

      expect(mcpAddCall).toBeTruthy();
      expect(mcpAddCall).toContain('opencode-mcp');
      expect(mcpAddCall).toContain('node');
      expect(mcpAddCall).toContain(
        path.join('/plugin', 'Better-OpenCodeMCP', 'dist', 'index.js'),
      );
    });

    it('handles already-registered gracefully', () => {
      mockFs.existsSync.mockImplementation((p) => {
        if (p.includes('package.json')) return true;
        if (p.includes('dist/index.js')) return true;
        return false;
      });

      let firstMcpAdd = true;
      mockExecSync.mockImplementation((cmd) => {
        if (typeof cmd === 'string' && cmd.includes('claude mcp add') && firstMcpAdd) {
          firstMcpAdd = false;
          const err = new Error('already exists');
          err.stderr = Buffer.from('already exists');
          throw err;
        }
        return Buffer.from('');
      });

      expect(() => setupMcpServer(mockFs, mockExecSync, '/plugin')).not.toThrow();

      const calls = mockExecSync.mock.calls.map((c) => c[0]);
      expect(calls.some((c) => c.includes('claude mcp remove'))).toBe(true);
    });
  });
});
