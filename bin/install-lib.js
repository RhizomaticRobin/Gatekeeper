/**
 * install-lib.js — Pure library functions used by install.js.
 *
 * Extracted so they can be tested in isolation with injected
 * fs / child_process dependencies.
 */

const path = require('path');

// Directories/files to exclude when copying
const EXCLUDE = new Set([
  'node_modules',
  '.git',
  '.github',
  '.npmrc',
  '.npmignore',
  '.gitignore',
  '.gitmodules',
  '.DS_Store',
  '.claude',
  '.planning',
  'tests',
  'verifier-mcp',
  'vitest.config.js',
  'pytest.ini',
  'package-lock.json',
]);

// Colors (re-declared here to keep the module self-contained)
const green = '\x1b[32m';
const yellow = '\x1b[33m';
const dim = '\x1b[2m';
const reset = '\x1b[0m';

/**
 * Recursively copy plugin directory, excluding build/dev artifacts.
 */
function copyPluginDirectory(fs, src, dest) {
  fs.mkdirSync(dest, { recursive: true });

  const entries = fs.readdirSync(src, { withFileTypes: true });

  for (const entry of entries) {
    if (EXCLUDE.has(entry.name)) continue;

    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyPluginDirectory(fs, srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

/**
 * Verify that key plugin files exist after installation.
 */
function verifyInstallation(fs, pluginDir) {
  const requiredFiles = [
    '.claude-plugin/plugin.json',
    'hooks/hooks.json',
    'commands/help.md',
    'agents/verifier.md',
  ];

  const failures = [];
  for (const relPath of requiredFiles) {
    const fullPath = path.join(pluginDir, relPath);
    if (!fs.existsSync(fullPath)) {
      failures.push(relPath);
    }
  }

  return failures;
}

/**
 * Set up the evolve-mcp server: install fastmcp Python dependency.
 * evolve-mcp is a FastMCP Python server bundled with the plugin.
 * It auto-installs fastmcp on first launch via bin/evolve-mcp.sh,
 * but we pre-install here for a better experience.
 */
function setupEvolveMcp(fs, execSync, pluginDir) {
  const mcpDir = path.join(pluginDir, 'evolve-mcp');
  const serverPy = path.join(mcpDir, 'server.py');
  const launcherScript = path.join(pluginDir, 'bin', 'evolve-mcp.sh');

  // Verify source exists (bundled with plugin)
  if (!fs.existsSync(serverPy)) {
    console.error(`  ${yellow}evolve-mcp source not found at ${mcpDir}${reset}`);
    console.error(`  ${dim}This is bundled with the plugin — reinstall may be needed${reset}`);
    return;
  }

  // Install fastmcp Python dependency
  console.log(`  ${dim}Installing evolve-mcp dependencies (fastmcp)...${reset}`);
  try {
    execSync('pip install fastmcp', { stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Installed fastmcp Python dependency`);
  } catch (err) {
    // Try pip3 as fallback
    try {
      execSync('pip3 install fastmcp', { stdio: 'pipe' });
      console.log(`  ${green}✓${reset} Installed fastmcp Python dependency`);
    } catch (err2) {
      console.error(`  ${yellow}Could not install fastmcp automatically${reset}`);
      console.error(`  ${dim}${err2.stderr ? err2.stderr.toString().trim() : err2.message}${reset}`);
      console.error(`  ${yellow}Run manually:${reset} pip install fastmcp`);
      console.error(`  ${dim}The evolve-mcp launcher will also auto-install on first use${reset}`);
    }
  }

  // Deregister old verifier-mcp if it exists
  console.log(`  ${dim}Cleaning up old verifier-mcp registration...${reset}`);
  try {
    execSync('claude mcp remove verifier-mcp', { stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Removed old verifier-mcp MCP server`);
  } catch {
    // Not registered — that's fine
  }

  // Make launcher executable
  try {
    fs.chmodSync(launcherScript, 0o755);
  } catch {
    // Already executable or chmod not needed
  }

  console.log(`  ${green}✓${reset} evolve-mcp ready (auto-starts via plugin.json)`);
}

/**
 * Set up the gatekeeper-mcp server: install Python dependencies.
 * gatekeeper-mcp is a FastMCP Python server for centralized token management.
 */
function setupGatekeeperMcp(fs, execSync, pluginDir) {
  const mcpDir = path.join(pluginDir, 'gatekeeper-mcp');
  const pyprojectToml = path.join(mcpDir, 'pyproject.toml');
  const launcherScript = path.join(pluginDir, 'bin', 'gatekeeper-mcp.sh');

  // Verify source exists (bundled with plugin)
  if (!fs.existsSync(pyprojectToml)) {
    console.error(`  ${yellow}gatekeeper-mcp source not found at ${mcpDir}${reset}`);
    console.error(`  ${dim}This is bundled with the plugin — reinstall may be needed${reset}`);
    return;
  }

  // Install gatekeeper-mcp in editable mode
  console.log(`  ${dim}Installing gatekeeper-mcp...${reset}`);
  try {
    execSync(`pip install -e "${mcpDir}"`, { stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Installed gatekeeper-mcp package`);
  } catch (err) {
    // Try pip3 as fallback
    try {
      execSync(`pip3 install -e "${mcpDir}"`, { stdio: 'pipe' });
      console.log(`  ${green}✓${reset} Installed gatekeeper-mcp package`);
    } catch (err2) {
      console.error(`  ${yellow}Could not install gatekeeper-mcp automatically${reset}`);
      console.error(`  ${dim}${err2.stderr ? err2.stderr.toString().trim() : err2.message}${reset}`);
      console.error(`  ${yellow}Run manually:${reset} pip install -e ${mcpDir}`);
    }
  }

  // Make launcher executable
  try {
    fs.chmodSync(launcherScript, 0o755);
  } catch {
    // Already executable or chmod not needed
  }

  console.log(`  ${green}✓${reset} gatekeeper-mcp ready`);
}

module.exports = { copyPluginDirectory, verifyInstallation, setupEvolveMcp, setupGatekeeperMcp, EXCLUDE };
