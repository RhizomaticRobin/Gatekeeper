/**
 * Resolve an Anthropic API key for the Agent SDK's query() function.
 *
 * Priority:
 * 1. ANTHROPIC_API_KEY env var (explicit API key)
 * 2. CONTAINER_API_KEY env var (container/managed environments)
 * 3. OAuth access token from ~/.claude/.credentials.json (subscription users on bare metal)
 *
 * The Claude Agent SDK's query() spawns a separate Claude Code subprocess
 * that needs an API key to authenticate. Subscription (OAuth) auth doesn't
 * automatically propagate to these subprocesses.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

interface ClaudeCredentials {
  claudeAiOauth?: {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
  };
}

export interface ResolvedApiKey {
  key: string;
  source: "env" | "container" | "oauth";
}

// Diagnostic info collected during resolution (for error messages)
let lastDiag = "";

/**
 * Attempt to resolve an API key from env, container key, or OAuth credentials.
 * Returns the key and its source, or null if no key could be found.
 */
export function resolveApiKey(): ResolvedApiKey | null {
  const diag: string[] = [];

  // 1. ANTHROPIC_API_KEY env var (explicit)
  if (process.env.ANTHROPIC_API_KEY) {
    return { key: process.env.ANTHROPIC_API_KEY, source: "env" };
  }
  diag.push("ANTHROPIC_API_KEY: not set");

  // 2. CONTAINER_API_KEY (container/managed environments like Claude.ai sandbox)
  if (process.env.CONTAINER_API_KEY) {
    return { key: process.env.CONTAINER_API_KEY, source: "container" };
  }
  diag.push("CONTAINER_API_KEY: not set");

  // 3. OAuth credentials from Claude Code's credential store (bare metal)
  const home = os.homedir();
  const credPath = path.join(home, ".claude", ".credentials.json");

  try {
    if (!fs.existsSync(credPath)) {
      diag.push(`${credPath}: not found`);
      lastDiag = diag.join("\n");
      return null;
    }

    const raw = fs.readFileSync(credPath, "utf-8");
    const creds: ClaudeCredentials = JSON.parse(raw);
    const oauth = creds.claudeAiOauth;

    if (!oauth?.accessToken) {
      diag.push(`${credPath}: no accessToken`);
      lastDiag = diag.join("\n");
      return null;
    }

    // Check if token is expired (with 60s buffer)
    if (oauth.expiresAt) {
      const nowMs = Date.now();
      if (oauth.expiresAt < nowMs + 60_000) {
        diag.push(`${credPath}: token expired`);
        lastDiag = diag.join("\n");
        return null;
      }
    }

    return { key: oauth.accessToken, source: "oauth" };
  } catch (err: unknown) {
    diag.push(`${credPath}: ${err instanceof Error ? err.message : String(err)}`);
    lastDiag = diag.join("\n");
    return null;
  }
}

/**
 * Build the env object for query() options.
 * Injects ANTHROPIC_API_KEY if not already set.
 */
export function buildQueryEnv(): Record<string, string | undefined> {
  const env = { ...process.env };

  if (!env.ANTHROPIC_API_KEY) {
    const resolved = resolveApiKey();
    if (resolved) {
      env.ANTHROPIC_API_KEY = resolved.key;
    }
  }

  return env;
}

/**
 * Format an error message when no API key could be resolved.
 */
export function noApiKeyError(): string {
  return [
    "No Anthropic API key available. The Agent SDK needs authentication to spawn",
    "independent verification agents.",
    "",
    "Tried:",
    "  1. ANTHROPIC_API_KEY env var — not set",
    "  2. CONTAINER_API_KEY env var — not set",
    "  3. ~/.claude/.credentials.json — no valid OAuth token found",
    "",
    "Diagnostics:",
    lastDiag || "  (none)",
    "",
    "To fix (pick one):",
    "  • Set ANTHROPIC_API_KEY=sk-ant-... before starting Claude Code",
    "  • Log in to Claude Code (OAuth token read automatically on bare metal)",
  ].join("\n");
}
