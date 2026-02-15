/**
 * Resolve an Anthropic API key for the Agent SDK's query() function.
 *
 * Priority:
 * 1. ANTHROPIC_API_KEY env var (explicit API key)
 * 2. OAuth access token from ~/.claude/.credentials.json (subscription users)
 *
 * The Claude Agent SDK's query() spawns a separate Claude Code subprocess
 * that needs an API key to authenticate. Subscription (OAuth) auth doesn't
 * automatically propagate to these subprocesses, but the OAuth access token
 * (sk-ant-oat01-...) can be used directly as a bearer token.
 *
 * Inspired by OpenClaw's credential sync approach.
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
  source: "env" | "oauth";
}

/**
 * Attempt to resolve an API key from env or OAuth credentials.
 * Returns the key and its source, or null if no key could be found.
 */
export function resolveApiKey(): ResolvedApiKey | null {
  // 1. Check ANTHROPIC_API_KEY env var first
  if (process.env.ANTHROPIC_API_KEY) {
    return { key: process.env.ANTHROPIC_API_KEY, source: "env" };
  }

  // 2. Try reading OAuth credentials from Claude Code's credential store
  const credPath = path.join(os.homedir(), ".claude", ".credentials.json");
  try {
    if (!fs.existsSync(credPath)) return null;

    const raw = fs.readFileSync(credPath, "utf-8");
    const creds: ClaudeCredentials = JSON.parse(raw);
    const oauth = creds.claudeAiOauth;
    if (!oauth?.accessToken) return null;

    // Check if token is expired (with 60s buffer)
    if (oauth.expiresAt) {
      const nowMs = Date.now();
      if (oauth.expiresAt < nowMs + 60_000) {
        // Token expired or about to expire — can't use it
        return null;
      }
    }

    return { key: oauth.accessToken, source: "oauth" };
  } catch {
    // Can't read or parse credentials — fall through
    return null;
  }
}

/**
 * Build the env object for query() options.
 * Injects ANTHROPIC_API_KEY from OAuth credentials if not already set.
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
    "  2. ~/.claude/.credentials.json — no valid OAuth token found",
    "",
    "To fix (pick one):",
    "  • Set ANTHROPIC_API_KEY=sk-ant-... (get one at https://console.anthropic.com/settings/keys)",
    "  • Log in to Claude Code (the OAuth token will be read automatically)",
  ].join("\n");
}
