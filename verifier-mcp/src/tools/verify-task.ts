/**
 * verify_task tool - Spawn a verifier agent for a specific task
 *
 * Security model:
 * - Token is generated at call time (NOT at setup time)
 * - Token file is written just before spawning the verifier (fetch-completion-token.sh needs it)
 * - Token file did NOT exist before this MCP tool was called
 * - This prevents executor agents from reading the secret file before calling verify_task
 * - The executor never sees or touches the verifier prompt.
 */
import { query } from "@anthropic-ai/claude-agent-sdk";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { resolveApiKey, buildQueryEnv, noApiKeyError } from "./resolve-api-key.js";

export interface VerifyTaskInput {
  task_id: string;
  plan_file?: string;
}

export interface VerifyTaskResult {
  task_id: string;
  status: "PASS" | "FAIL" | "ERROR";
  token?: string;
  details: string;
  durationMs: number;
}

export async function executeVerifyTask(
  input: VerifyTaskInput,
  serverCwd: string
): Promise<VerifyTaskResult> {
  const startTime = Date.now();

  // Pre-flight: Resolve API key from env or OAuth credentials.
  // The Agent SDK's query() needs a key to spawn Claude Code subprocesses.
  const apiKey = resolveApiKey();
  if (!apiKey) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: noApiKeyError(),
      durationMs: Date.now() - startTime,
    };
  }

  const planFile = input.plan_file
    ? path.resolve(serverCwd, input.plan_file)
    : path.join(serverCwd, ".claude", "plan", "plan.yaml");

  // 1. Verify plan.yaml exists
  if (!fs.existsSync(planFile)) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Plan file not found: ${planFile}`,
      durationMs: Date.now() - startTime,
    };
  }

  // Derive project root from plan file path (plan is at <project>/.claude/plan/plan.yaml)
  const projectRoot = path.resolve(path.dirname(planFile), "..", "..");

  // 2. Find session directory: try .claude/vgl-sessions/task-{id}/ first, fall back to .claude/
  const taskSessionDir = path.join(
    projectRoot,
    ".claude",
    "vgl-sessions",
    `task-${input.task_id}`
  );
  const fallbackDir = path.join(projectRoot, ".claude");

  let sessionDir: string;
  if (fs.existsSync(taskSessionDir)) {
    sessionDir = taskSessionDir;
  } else if (fs.existsSync(fallbackDir)) {
    sessionDir = fallbackDir;
  } else {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `No session directory found. Tried: ${taskSessionDir} and ${fallbackDir}`,
      durationMs: Date.now() - startTime,
    };
  }

  // 3. Read verifier-prompt.local.md
  const verifierPromptPath = path.join(sessionDir, "verifier-prompt.local.md");
  if (!fs.existsSync(verifierPromptPath)) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Verifier prompt not found at: ${verifierPromptPath}. Was setup-verifier-loop.sh run?`,
      durationMs: Date.now() - startTime,
    };
  }

  let verifierPrompt: string;
  try {
    verifierPrompt = fs.readFileSync(verifierPromptPath, "utf-8");
  } catch (err: unknown) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Failed to read verifier prompt: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  if (!verifierPrompt.trim()) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Verifier prompt is empty at: ${verifierPromptPath}`,
      durationMs: Date.now() - startTime,
    };
  }

  // 4. Generate one-time token and write token file just before spawning
  // Token file did NOT exist before this call — agents can't pre-read it
  const token = `VGL_COMPLETE_${crypto.randomBytes(16).toString("hex")}`;
  const tokenFilePath = path.join(sessionDir, "verifier-token.secret");

  // Read existing test command data if present (from setup), otherwise create minimal file
  let testCmdB64 = "";
  let testCmdHash = "";
  if (fs.existsSync(tokenFilePath)) {
    // If file exists from a previous verify_task call, read test command data
    try {
      const existing = fs.readFileSync(tokenFilePath, "utf-8");
      const b64Line = existing.split("\n").find(l => l.startsWith("TEST_CMD_B64:"));
      const hashLine = existing.split("\n").find(l => l.startsWith("TEST_CMD_HASH:"));
      if (b64Line) testCmdB64 = b64Line.replace("TEST_CMD_B64:", "");
      if (hashLine) testCmdHash = hashLine.replace("TEST_CMD_HASH:", "");
    } catch {
      // ignore read errors
    }
  }

  // Write fresh token file (fetch-completion-token.sh reads this)
  try {
    let tokenFileContent = token + "\n";
    if (testCmdB64 && testCmdHash) {
      tokenFileContent += `TEST_CMD_B64:${testCmdB64}\nTEST_CMD_HASH:${testCmdHash}\n`;
    }
    fs.writeFileSync(tokenFilePath, tokenFileContent, { mode: 0o600 });
  } catch (err: unknown) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Failed to write token file: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  // 5. Spawn Claude Code via query() with locked-down config
  const options: Partial<Options> = {
    cwd: projectRoot,
    env: buildQueryEnv(),
    allowedTools: [
      "Read", "Bash", "Grep", "Glob",
      // Playwright MCP tools for visual verification
      "mcp__playwright__browser_navigate",
      "mcp__playwright__browser_snapshot",
      "mcp__playwright__browser_click",
      "mcp__playwright__browser_type",
      "mcp__playwright__browser_fill_form",
      "mcp__playwright__browser_take_screenshot",
      "mcp__playwright__browser_console_messages",
      "mcp__playwright__browser_evaluate",
      "mcp__playwright__browser_wait_for",
      "mcp__playwright__browser_close",
    ],
    disallowedTools: ["Write", "Edit", "Task", "WebFetch", "WebSearch"],
    model: "claude-opus-4-6",
    permissionMode: "dontAsk",
    maxTurns: 50,
    persistSession: false,
    mcpServers: {
      playwright: {
        command: "npx",
        args: ["@playwright/mcp"],
      },
    } as Options["mcpServers"],
    settingSources: [],
  };

  let resultText = "";
  let isError = false;

  try {
    for await (const message of query({
      prompt: verifierPrompt,
      options,
    })) {
      if (message.type === "result") {
        if (message.subtype === "success") {
          resultText = message.result;
        } else {
          isError = true;
          resultText =
            message.errors.map(String).join("\n") ||
            `Verifier error [${message.subtype}]`;
        }
        break;
      }
    }
  } catch (err: unknown) {
    // Clean up token file on crash
    try { fs.unlinkSync(tokenFilePath); } catch { /* ignore */ }
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Verifier agent crashed: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  if (isError || !resultText) {
    // Clean up token file on FAIL — must not be readable after failure
    try { fs.unlinkSync(tokenFilePath); } catch { /* ignore */ }
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: resultText || "Verifier produced no output",
      durationMs: Date.now() - startTime,
    };
  }

  // 6. Parse result for PASS/FAIL + validate token
  // The verifier gets the token via fetch-completion-token.sh (which reads the file we wrote)
  const passMatch = resultText.includes(token);
  if (passMatch) {
    // Token file stays on PASS — orchestrator reads it to validate
    return {
      task_id: input.task_id,
      status: "PASS",
      token,
      details: resultText,
      durationMs: Date.now() - startTime,
    };
  }

  // Not PASS — clean up token file so agents can't read it
  try { fs.unlinkSync(tokenFilePath); } catch { /* ignore */ }

  // Check for explicit FAIL/denial markers
  const failMatch = resultText.match(/VERIFICATION_FAILED|TOKEN.DENIED|TESTS_FAILED|<verification-complete>\s*FAIL/i);
  if (failMatch) {
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: resultText,
      durationMs: Date.now() - startTime,
    };
  }

  // No clear PASS or FAIL — return the full output as FAIL
  return {
    task_id: input.task_id,
    status: "FAIL",
    details: resultText,
    durationMs: Date.now() - startTime,
  };
}
