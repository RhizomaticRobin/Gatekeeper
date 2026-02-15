/**
 * verify_task tool - Spawn a verifier agent for a specific task
 *
 * Security: The executor never sees or touches the verifier prompt.
 * It just calls verify_task(task_id) and the MCP server handles everything.
 */
import { query } from "@anthropic-ai/claude-agent-sdk";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import * as fs from "node:fs";
import * as path from "node:path";

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

  // 2. Find session directory: try .claude/vgl-sessions/task-{id}/ first, fall back to .claude/
  const taskSessionDir = path.join(
    serverCwd,
    ".claude",
    "vgl-sessions",
    `task-${input.task_id}`
  );
  const fallbackDir = path.join(serverCwd, ".claude");

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

  // 4. Spawn Claude Code via query() with locked-down config
  const options: Partial<Options> = {
    cwd: serverCwd,
    allowedTools: ["Read", "Bash", "Grep", "Glob"],
    disallowedTools: ["Write", "Edit", "Task", "WebFetch", "WebSearch"],
    model: "claude-opus-4-6",
    permissionMode: "dontAsk",
    mcpServers: {
      playwright: {
        command: "npx",
        args: ["@playwright/mcp"],
      },
    } as Options["mcpServers"],
    settingSources: ["user", "project", "local"],
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
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Verifier agent crashed: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  if (isError || !resultText) {
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: resultText || "Verifier produced no output",
      durationMs: Date.now() - startTime,
    };
  }

  // 5. Parse result for PASS/FAIL + token
  // Token format: VGL_COMPLETE_<32 hex chars> (128-bit entropy)
  const passMatch = resultText.match(
    /VGL_COMPLETE_([a-f0-9]{32})/
  );
  if (passMatch) {
    return {
      task_id: input.task_id,
      status: "PASS",
      token: passMatch[0], // Full token including VGL_COMPLETE_ prefix
      details: resultText,
      durationMs: Date.now() - startTime,
    };
  }

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
