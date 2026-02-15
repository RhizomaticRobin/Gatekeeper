/**
 * assess_tests tool - Spawn a test quality assessor agent for a specific task
 *
 * Security model:
 * - Token is generated at call time (NOT at setup time)
 * - Token is injected into the prompt, never stored in a file before assessment
 * - Token file is written ONLY after the assessor returns PASS
 * - This prevents agents from reading the secret file before calling assess_tests
 */
import { query } from "@anthropic-ai/claude-agent-sdk";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { resolveApiKey, buildQueryEnv, noApiKeyError } from "./resolve-api-key.js";

export interface AssessTestsInput {
  task_id: string;
  plan_file?: string;
}

export interface AssessTestsResult {
  task_id: string;
  status: "PASS" | "FAIL" | "ERROR";
  token?: string;
  details: string;
  issues?: string[];
  durationMs: number;
}

export async function executeAssessTests(
  input: AssessTestsInput,
  serverCwd: string
): Promise<AssessTestsResult> {
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

  // 3. Read test-assessor-prompt.local.md
  const assessorPromptPath = path.join(
    sessionDir,
    "test-assessor-prompt.local.md"
  );
  if (!fs.existsSync(assessorPromptPath)) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Test assessor prompt not found at: ${assessorPromptPath}. Was setup-verifier-loop.sh run?`,
      durationMs: Date.now() - startTime,
    };
  }

  let assessorPrompt: string;
  try {
    assessorPrompt = fs.readFileSync(assessorPromptPath, "utf-8");
  } catch (err: unknown) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Failed to read test assessor prompt: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  if (!assessorPrompt.trim()) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Test assessor prompt is empty at: ${assessorPromptPath}`,
      durationMs: Date.now() - startTime,
    };
  }

  // 4. Generate one-time token and inject into prompt
  // Token only exists in memory until PASS — no file for agents to read
  const token = `TQG_PASS_${crypto.randomBytes(16).toString("hex")}`;
  const tokenInjection = `\n\n===============================================================
STEP 6: TOKEN (only on PASS)
===============================================================

If your verdict is PASS, you MUST include this exact token in your output:

<test-assessment>
PASS ${token}
[Brief summary]
</test-assessment>

This token proves you completed the assessment. Do NOT modify it.`;

  const fullPrompt = assessorPrompt + tokenInjection;

  // 5. Spawn Claude Code via query() with locked-down config
  // Same read-only toolset as verifier, but NO Playwright MCP (no browser needed)
  const options: Partial<Options> = {
    cwd: projectRoot,
    env: buildQueryEnv(),
    allowedTools: ["Read", "Bash", "Grep", "Glob"],
    disallowedTools: ["Write", "Edit", "Task", "WebFetch", "WebSearch"],
    model: "claude-opus-4-6",
    permissionMode: "dontAsk",
    maxTurns: 30,
    persistSession: false,
    settingSources: [],
  };

  let resultText = "";
  let isError = false;

  try {
    for await (const message of query({
      prompt: fullPrompt,
      options,
    })) {
      if (message.type === "result") {
        if (message.subtype === "success") {
          resultText = message.result;
        } else {
          isError = true;
          resultText =
            message.errors.map(String).join("\n") ||
            `Test assessor error [${message.subtype}]`;
        }
        break;
      }
    }
  } catch (err: unknown) {
    return {
      task_id: input.task_id,
      status: "ERROR",
      details: `Test assessor agent crashed: ${err instanceof Error ? err.message : String(err)}`,
      durationMs: Date.now() - startTime,
    };
  }

  if (isError || !resultText) {
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: resultText || "Test assessor produced no output",
      durationMs: Date.now() - startTime,
    };
  }

  // 6. Parse result for PASS/FAIL + validate token
  const passMatch = resultText.match(
    /<test-assessment>\s*PASS/i
  );
  if (passMatch) {
    // Validate the assessor echoed back the exact token we injected
    const tokenMatch = resultText.includes(token);
    if (tokenMatch) {
      // Write token file NOW (after PASS) so orchestrator can validate later
      const tokenFilePath = path.join(sessionDir, "test-assessor-token.secret");
      try {
        fs.writeFileSync(tokenFilePath, token + "\n", { mode: 0o600 });
      } catch {
        // Non-fatal: orchestrator can still use the token from the MCP response
      }

      return {
        task_id: input.task_id,
        status: "PASS",
        token,
        details: resultText,
        durationMs: Date.now() - startTime,
      };
    }
    // PASS but wrong/missing token — assessor may have hallucinated
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: `Assessor said PASS but did not echo the correct token. Output: ${resultText}`,
      durationMs: Date.now() - startTime,
    };
  }

  // Not PASS — clean up any stale token file so agents can't read it
  const tokenFilePath = path.join(sessionDir, "test-assessor-token.secret");
  try { fs.unlinkSync(tokenFilePath); } catch { /* ignore if doesn't exist */ }

  // Check for explicit FAIL markers
  const failMatch = resultText.match(
    /<test-assessment>\s*FAIL/i
  );
  if (failMatch) {
    // Extract specific issues from the output
    const issues = extractIssues(resultText);
    return {
      task_id: input.task_id,
      status: "FAIL",
      details: resultText,
      issues: issues.length > 0 ? issues : undefined,
      durationMs: Date.now() - startTime,
    };
  }

  // No clear PASS or FAIL — return full output as FAIL
  return {
    task_id: input.task_id,
    status: "FAIL",
    details: resultText,
    durationMs: Date.now() - startTime,
  };
}

/**
 * Extract individual issue lines from the assessor output.
 * Looks for lines starting with "- " after the FAIL marker.
 */
function extractIssues(text: string): string[] {
  const issues: string[] = [];
  const failIndex = text.search(/<test-assessment>\s*FAIL/i);
  if (failIndex === -1) return issues;

  const afterFail = text.slice(failIndex);
  const lines = afterFail.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") && trimmed.length > 2) {
      issues.push(trimmed.slice(2));
    }
  }
  return issues;
}
