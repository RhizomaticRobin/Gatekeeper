/**
 * Build the env object for query() options.
 *
 * The Agent SDK's query() spawns a separate Claude Code subprocess.
 * The subprocess needs its own API authentication — it can't inherit the
 * parent's managed/subscription auth in container environments.
 *
 * Auth resolution chain:
 *   1. ANTHROPIC_API_KEY already in env → use as-is
 *   2. ~/.claude/.credentials.json OAuth token → inject as ANTHROPIC_API_KEY
 *   3. Fall through — subprocess handles auth on its own
 *
 * The credentials file is created by the cc-setup installer with an OAuth
 * token (sk-ant-oat01-...) that works as both a Bearer token and API key.
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

/**
 * Build env for the query() subprocess.
 * Tries multiple auth strategies in order of preference.
 */
export function buildQueryEnv(): Record<string, string | undefined> {
  const env = { ...process.env };

  // Remove CLAUDECODE to prevent "nested session" detection.
  // The Agent SDK spawns `claude` as a subprocess — if CLAUDECODE=1 is inherited,
  // the subprocess refuses to start ("cannot be launched inside another session").
  delete env.CLAUDECODE;

  // Strategy 1: ANTHROPIC_API_KEY already set → use as-is
  if (env.ANTHROPIC_API_KEY) {
    return env;
  }

  // Strategy 2: OAuth token from credentials file
  // Written by cc-setup/install.sh or `claude /login`
  try {
    const credPath = path.join(os.homedir(), ".claude", ".credentials.json");
    if (fs.existsSync(credPath)) {
      const raw = fs.readFileSync(credPath, "utf-8");
      const creds: ClaudeCredentials = JSON.parse(raw);
      const oauth = creds.claudeAiOauth;

      if (oauth?.accessToken) {
        // Check expiry if present (skip check if no expiresAt)
        if (oauth.expiresAt) {
          const nowMs = Date.now();
          if (oauth.expiresAt <= nowMs + 60_000) {
            // Token expired — fall through
            return env;
          }
        }
        // Inject OAuth token AND route through model-proxy
        // The proxy will handle opus → Anthropic, non-opus → CCR → z.ai
        env.ANTHROPIC_API_KEY = oauth.accessToken;
        env.ANTHROPIC_BASE_URL = "http://127.0.0.1:3457";
        return env;
      }
    }
  } catch {
    // Can't read credentials — fall through
  }

  // Strategy 3: Fall through — subprocess handles auth on its own
  return env;
}
