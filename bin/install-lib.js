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
  '.DS_Store',
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
    'bin/ralph.sh',
    'templates/opencode.json',
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
 * Set up the Better-OpenCodeMCP submodule: ensure source exists,
 * npm install, build, register MCP.
 */
function setupMcpServer(fs, execSync, pluginDir) {
  const mcpDir = path.join(pluginDir, 'Better-OpenCodeMCP');
  const mcpPkg = path.join(mcpDir, 'package.json');
  const mcpDist = path.join(mcpDir, 'dist', 'index.js');
  const repoUrl = 'https://github.com/RhizomaticRobin/Better-OpenCodeMCP.git';

  // If source wasn't copied (e.g. npx install without submodule), clone it
  if (!fs.existsSync(mcpPkg)) {
    console.log(`  ${dim}Cloning opencode-mcp server...${reset}`);
    try {
      execSync(`git clone --depth 1 ${repoUrl} "${mcpDir}"`, { stdio: 'pipe' });
      console.log(`  ${green}✓${reset} Cloned opencode-mcp server`);
    } catch (err) {
      console.error(`\n  ${yellow}Failed to clone opencode-mcp server${reset}`);
      console.error(`  ${dim}${err.stderr ? err.stderr.toString().trim() : err.message}${reset}`);
      console.error(`  ${yellow}You can set it up manually later:${reset}`);
      console.error(`  ${dim}cd ${mcpDir} && git clone ${repoUrl} . && npm install && npm run build${reset}`);
      console.error(`  ${dim}claude mcp add opencode-mcp node ${mcpDist}${reset}`);
      return;
    }
  }

  // npm install
  console.log(`  ${dim}Installing opencode-mcp dependencies...${reset}`);
  try {
    execSync('npm install --production=false', { cwd: mcpDir, stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Installed opencode-mcp dependencies`);
  } catch (err) {
    console.error(`\n  ${yellow}npm install failed for opencode-mcp${reset}`);
    console.error(`  ${dim}${err.stderr ? err.stderr.toString().trim() : err.message}${reset}`);
    console.error(`  ${yellow}Run manually:${reset} cd ${mcpDir} && npm install && npm run build`);
    return;
  }

  // npm run build
  console.log(`  ${dim}Building opencode-mcp server...${reset}`);
  try {
    execSync('npm run build', { cwd: mcpDir, stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Built opencode-mcp server`);
  } catch (err) {
    console.error(`\n  ${yellow}Build failed for opencode-mcp${reset}`);
    console.error(`  ${dim}${err.stderr ? err.stderr.toString().trim() : err.message}${reset}`);
    console.error(`  ${yellow}Run manually:${reset} cd ${mcpDir} && npm run build`);
    return;
  }

  // Verify dist/index.js exists
  if (!fs.existsSync(mcpDist)) {
    console.error(`  ${yellow}Build produced no output at ${mcpDist}${reset}`);
    return;
  }

  // Register MCP server with Claude Code
  console.log(`  ${dim}Registering opencode-mcp with Claude Code...${reset}`);
  try {
    execSync(`claude mcp add opencode-mcp node "${mcpDist}"`, { stdio: 'pipe' });
    console.log(`  ${green}✓${reset} Registered opencode-mcp MCP server`);
  } catch (err) {
    // claude CLI might not be available or might already be registered
    const stderr = err.stderr ? err.stderr.toString().trim() : '';
    if (stderr.includes('already exists')) {
      // Remove and re-add to update the path
      try {
        execSync('claude mcp remove opencode-mcp', { stdio: 'pipe' });
        execSync(`claude mcp add opencode-mcp node "${mcpDist}"`, { stdio: 'pipe' });
        console.log(`  ${green}✓${reset} Updated opencode-mcp MCP server registration`);
      } catch {
        console.error(`  ${yellow}Could not update MCP registration. Run manually:${reset}`);
        console.error(`  ${dim}claude mcp add opencode-mcp node ${mcpDist}${reset}`);
      }
    } else {
      console.error(`  ${yellow}Could not register MCP server automatically${reset}`);
      console.error(`  ${dim}${stderr || err.message}${reset}`);
      console.error(`  ${yellow}Run manually:${reset} claude mcp add opencode-mcp node ${mcpDist}`);
    }
  }
}

module.exports = { copyPluginDirectory, verifyInstallation, setupMcpServer, EXCLUDE };
