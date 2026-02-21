#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');
const { execSync } = require('child_process');
const lib = require('./install-lib');

// Colors
const crimson = '\x1b[38;2;220;20;60m';
const green = '\x1b[32m';
const yellow = '\x1b[33m';
const dim = '\x1b[2m';
const reset = '\x1b[0m';

// Get version from package.json
const pkg = require('../package.json');

const banner = `
${crimson}      ██████╗  █████╗ ████████╗ ██████╗ ██╗ ██╗ ██████╗ ██████╗ █████╗  ██████╗ █████╗
     ██╔════╝ ██╔══██╗╚══██╔══╝██╔════╝██║ ██╔╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗
    ██║  ███╗███████║   ██║   █████╗  █████╔╝ █████╗  █████╗  ██████╔╝█████╗  ██████╔╝
   ██║   ██║██╔══██║   ██║   ██╔══╝  ██╔═██╗ ██╔══╝  ██╔══╝  ██╔═══╝ ██╔══╝  ██╔══██╗
  ╚██████╔╝██║  ██║   ██║   ███████╗██║  ██╗███████╗███████╗██║     ███████╗██║  ██║
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝${reset}

  Gatekeeper ${dim}v${pkg.version}${reset}
  Visual verifier-gated compartmentalized TDD + evolutionary optimization
  for Claude Code by RhizomaticRobin.
`;

// Parse args
const args = process.argv.slice(2);
const hasGlobal = args.includes('--global') || args.includes('-g');
const hasLocal = args.includes('--local') || args.includes('-l');
const hasHelp = args.includes('--help') || args.includes('-h');

// Parse --config-dir argument
function parseConfigDirArg() {
  const configDirIndex = args.findIndex(arg => arg === '--config-dir' || arg === '-c');
  if (configDirIndex !== -1) {
    const nextArg = args[configDirIndex + 1];
    if (!nextArg || nextArg.startsWith('-')) {
      console.error(`  ${yellow}--config-dir requires a path argument${reset}`);
      process.exit(1);
    }
    return nextArg;
  }
  const configDirArg = args.find(arg => arg.startsWith('--config-dir=') || arg.startsWith('-c='));
  if (configDirArg) {
    const value = configDirArg.split('=')[1];
    if (!value) {
      console.error(`  ${yellow}--config-dir requires a non-empty path${reset}`);
      process.exit(1);
    }
    return value;
  }
  return null;
}
const explicitConfigDir = parseConfigDirArg();

// Banner and help are only shown when running directly
if (require.main === module) {
  console.log(banner);

  // Show help if requested
  if (hasHelp) {
    console.log(`  ${yellow}Usage:${reset} npx gatekeeper [options]

  ${yellow}Options:${reset}
    ${crimson}-g, --global${reset}              Install globally (to Claude plugins directory)
    ${crimson}-l, --local${reset}               Install locally (to ./.claude/plugins in current directory)
    ${crimson}-c, --config-dir <path>${reset}   Specify custom Claude config directory
    ${crimson}-h, --help${reset}                Show this help message

  ${yellow}Examples:${reset}
    ${dim}# Install to default ~/.claude/plugins/marketplaces/gatekeeper${reset}
    npx gatekeeper --global

    ${dim}# Install to custom config directory${reset}
    npx gatekeeper --global --config-dir ~/.claude-bc

    ${dim}# Using environment variable${reset}
    CLAUDE_CONFIG_DIR=~/.claude-bc npx gatekeeper --global

    ${dim}# Install to current project only${reset}
    npx gatekeeper --local

  ${yellow}Notes:${reset}
    Gatekeeper is a Claude Code plugin. The installer copies the plugin
    directory to your Claude plugins folder. Claude Code discovers
    commands, agents, and hooks automatically via \${CLAUDE_PLUGIN_ROOT}.
`);
    process.exit(0);
  }
}

/**
 * Expand ~ to home directory
 */
function expandTilde(filePath) {
  if (filePath && filePath.startsWith('~/')) {
    return path.join(os.homedir(), filePath.slice(2));
  }
  return filePath;
}

// Delegate to library functions, binding fs and execSync from this module's scope
function copyPluginDirectory(src, dest) {
  return lib.copyPluginDirectory(fs, src, dest);
}

/**
 * Walk the plugin directory and chmod 755 all .sh files
 * and .js files under hooks/.
 */
function makeScriptsExecutable(pluginDir) {
  let count = 0;

  function walk(dir, isHooksSubtree) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath, isHooksSubtree || entry.name === 'hooks');
      } else if (entry.name.endsWith('.sh')) {
        fs.chmodSync(fullPath, 0o755);
        count++;
      } else if (isHooksSubtree && entry.name.endsWith('.js')) {
        fs.chmodSync(fullPath, 0o755);
        count++;
      }
    }
  }

  walk(pluginDir, false);
  return count;
}

function verifyInstallation(pluginDir) {
  return lib.verifyInstallation(fs, pluginDir);
}

function setupEvolveMcp(pluginDir) {
  return lib.setupEvolveMcp(fs, execSync, pluginDir);
}

/**
 * Register the gatekeeper marketplace in known_marketplaces.json.
 */
function registerMarketplace(claudeDir, marketplaceDir) {
  const knownPath = path.join(claudeDir, 'plugins', 'known_marketplaces.json');
  let known = {};
  if (fs.existsSync(knownPath)) {
    try {
      known = JSON.parse(fs.readFileSync(knownPath, 'utf8'));
    } catch {
      known = {};
    }
  }

  known['gatekeeper'] = {
    source: { source: 'github', repo: 'RhizomaticRobin/gsd-vgl' },
    installLocation: marketplaceDir,
    lastUpdated: new Date().toISOString(),
  };

  fs.writeFileSync(knownPath, JSON.stringify(known, null, 2) + '\n');
  console.log(`  ${green}✓${reset} Registered gatekeeper marketplace`);
}

/**
 * Create the marketplace.json inside the marketplace directory.
 */
function createMarketplaceJson(marketplaceDir) {
  const metaDir = path.join(marketplaceDir, '.claude-plugin');
  fs.mkdirSync(metaDir, { recursive: true });

  const manifest = {
    name: 'gatekeeper',
    description: 'Gatekeeper plugin marketplace',
    owner: { name: 'RhizomaticRobin', email: 'atatle@proton.me' },
    plugins: [
      {
        name: 'gatekeeper',
        description: pkg.description,
        version: pkg.version,
        author: { name: 'RhizomaticRobin', email: 'atatle@proton.me' },
        source: './plugins/gatekeeper',
        category: 'development',
      },
    ],
  };

  fs.writeFileSync(
    path.join(metaDir, 'marketplace.json'),
    JSON.stringify(manifest, null, 2) + '\n'
  );
}

/**
 * Add "gatekeeper@gatekeeper" to enabledPlugins in settings.json.
 */
function enablePlugin(claudeDir, scope) {
  const settingsPath = path.join(claudeDir, 'settings.json');
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    try {
      settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    } catch {
      settings = {};
    }
  }

  if (typeof settings.enabledPlugins !== 'object' || Array.isArray(settings.enabledPlugins)) {
    settings.enabledPlugins = {};
  }

  settings.enabledPlugins['gatekeeper@gatekeeper'] = true;

  fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');
  console.log(`  ${green}✓${reset} Enabled plugin in ${scope} settings`);
}

/**
 * Install the plugin to the resolved directory.
 */
function install(isGlobal) {
  const src = path.join(__dirname, '..');

  // Priority: explicit --config-dir > CLAUDE_CONFIG_DIR env > default ~/.claude
  const configDir = expandTilde(explicitConfigDir) || expandTilde(process.env.CLAUDE_CONFIG_DIR);
  const claudeDir = isGlobal
    ? (configDir || path.join(os.homedir(), '.claude'))
    : path.join(process.cwd(), '.claude');

  const marketplaceDir = path.join(claudeDir, 'plugins', 'marketplaces', 'gatekeeper');
  const destDir = path.join(marketplaceDir, 'plugins', 'gatekeeper');

  const locationLabel = destDir.replace(os.homedir(), '~');
  console.log(`  Installing to ${crimson}${locationLabel}${reset}\n`);

  // Clean up old-style installation at plugins/gatekeeper (pre-marketplace)
  const oldDestDir = path.join(claudeDir, 'plugins', 'gatekeeper');
  if (fs.existsSync(oldDestDir) && !oldDestDir.includes('marketplaces')) {
    fs.rmSync(oldDestDir, { recursive: true });
    console.log(`  ${green}✓${reset} Removed old installation at plugins/gatekeeper`);
  }

  // Remove existing marketplace installation for clean install
  if (fs.existsSync(destDir) || isSymlink(destDir)) {
    const stat = fs.lstatSync(destDir);
    if (stat.isSymbolicLink()) {
      fs.unlinkSync(destDir);
      console.log(`  ${green}✓${reset} Removed existing symlink`);
    } else {
      fs.rmSync(destDir, { recursive: true });
      console.log(`  ${green}✓${reset} Removed previous installation`);
    }
  }

  // Create marketplace structure
  createMarketplaceJson(marketplaceDir);

  // Copy plugin directory
  copyPluginDirectory(src, destDir);
  console.log(`  ${green}✓${reset} Copied plugin directory`);

  // Make scripts executable
  const execCount = makeScriptsExecutable(destDir);
  console.log(`  ${green}✓${reset} Made ${execCount} scripts executable`);

  // Verify installation
  const failures = verifyInstallation(destDir);
  if (failures.length > 0) {
    console.error(`\n  ${yellow}Installation incomplete!${reset} Missing files:`);
    for (const f of failures) {
      console.error(`    ${yellow}✗${reset} ${f}`);
    }
    process.exit(1);
  }
  console.log(`  ${green}✓${reset} Verified installation`);

  // Register marketplace and enable plugin
  registerMarketplace(claudeDir, marketplaceDir);
  enablePlugin(claudeDir, isGlobal ? 'global' : 'local');

  // Set up evolve-mcp server (install fastmcp Python dependency)
  setupEvolveMcp(destDir);

  console.log(`
  ${green}Done!${reset} Launch Claude Code and run ${crimson}/gatekeeper:help${reset}.
`);
}

/**
 * Check if a path is a symlink (even if target doesn't exist).
 */
function isSymlink(p) {
  try {
    fs.lstatSync(p);
    return fs.lstatSync(p).isSymbolicLink();
  } catch {
    return false;
  }
}

/**
 * Prompt user interactively for install location.
 */
function promptLocation() {
  if (!process.stdin.isTTY) {
    console.log(`  ${yellow}Non-interactive terminal detected, defaulting to global install${reset}\n`);
    install(true);
    return;
  }

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  let answered = false;

  rl.on('close', () => {
    if (!answered) {
      answered = true;
      console.log(`\n  ${yellow}Input stream closed, defaulting to global install${reset}\n`);
      install(true);
    }
  });

  const configDir = expandTilde(explicitConfigDir) || expandTilde(process.env.CLAUDE_CONFIG_DIR);
  const globalPath = configDir || path.join(os.homedir(), '.claude');
  const globalLabel = globalPath.replace(os.homedir(), '~');

  console.log(`  ${yellow}Where would you like to install?${reset}

  ${crimson}1${reset}) Global ${dim}(${globalLabel}/plugins/marketplaces/gatekeeper)${reset} - available in all projects
  ${crimson}2${reset}) Local  ${dim}(./.claude/plugins/marketplaces/gatekeeper)${reset} - this project only
`);

  rl.question(`  Choice ${dim}[1]${reset}: `, (answer) => {
    answered = true;
    rl.close();
    const choice = answer.trim() || '1';
    install(choice !== '2');
  });
}

// Export functions for testing
module.exports = { copyPluginDirectory, verifyInstallation, setupEvolveMcp };

// Main — only run when executed directly (not when required/imported for testing)
if (require.main === module) {
  if (hasGlobal && hasLocal) {
    console.error(`  ${yellow}Cannot specify both --global and --local${reset}`);
    process.exit(1);
  } else if (explicitConfigDir && hasLocal) {
    console.error(`  ${yellow}Cannot use --config-dir with --local${reset}`);
    process.exit(1);
  } else if (hasGlobal) {
    install(true);
  } else if (hasLocal) {
    install(false);
  } else {
    promptLocation();
  }
}
