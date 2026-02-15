/**
 * Verifier MCP Server - exposes only the verify_task tool
 *
 * This server exists solely to provide a secure, opaque verification interface.
 * The executor calls verify_task(task_id) and the server handles everything:
 * reading plan.yaml, loading the pre-generated verifier prompt, spawning
 * Claude Code with locked-down tools/model. The executor never sees the
 * verifier prompt.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { executeVerifyTask } from "./tools/verify-task.js";
import { executeAssessTests } from "./tools/assess-tests.js";

declare const __PKG_VERSION__: string;
const SERVER_VERSION = typeof __PKG_VERSION__ !== "undefined" ? __PKG_VERSION__ : "0.0.0-dev";

export function createServer(serverCwd: string): McpServer {
  const server = new McpServer({
    name: "verifier-mcp",
    version: SERVER_VERSION,
  });

  // Only tool: verify_task - Spawn a verifier agent for a specific task
  server.tool(
    "verify_task",
    `Verify a task by spawning an independent verifier agent. The verifier reads the pre-generated verifier prompt, runs tests, performs Playwright visual verification, and returns PASS/FAIL with a completion token.

Security: The caller never sees or touches the verifier prompt. It just provides a task_id and the MCP server handles everything internally — reading plan.yaml, loading the verifier prompt, spawning Claude Code with locked-down tools/model.`,
    {
      task_id: z
        .string()
        .describe("Task ID from plan.yaml (e.g., '1.1')"),
      plan_file: z
        .string()
        .optional()
        .describe(
          "Path to plan.yaml (default: .claude/plan/plan.yaml). Relative paths resolved from server cwd."
        ),
    },
    async (args) => {
      try {
        const result = await executeVerifyTask(args, serverCwd);
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(result, null, 2),
            },
          ],
          isError: result.status === "ERROR",
        };
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        return {
          content: [
            {
              type: "text" as const,
              text: `Error: ${message}`,
            },
          ],
          isError: true,
        };
      }
    }
  );

  // Second tool: assess_tests - Spawn a test quality assessor agent
  server.tool(
    "assess_tests",
    `Assess test quality by spawning an independent test assessor agent. The assessor reads the pre-generated test assessor prompt, inspects test files for comprehensiveness, alignment with must_haves, and quality, then returns PASS/FAIL with detailed feedback.

Security: The caller never sees or touches the assessor prompt. It just provides a task_id and the MCP server handles everything internally — reading plan.yaml, loading the assessor prompt, spawning Claude Code with locked-down read-only tools.`,
    {
      task_id: z
        .string()
        .describe("Task ID from plan.yaml (e.g., '1.1')"),
      plan_file: z
        .string()
        .optional()
        .describe(
          "Path to plan.yaml (default: .claude/plan/plan.yaml). Relative paths resolved from server cwd."
        ),
    },
    async (args) => {
      try {
        const result = await executeAssessTests(args, serverCwd);
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(result, null, 2),
            },
          ],
          isError: result.status === "ERROR",
        };
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        return {
          content: [
            {
              type: "text" as const,
              text: `Error: ${message}`,
            },
          ],
          isError: true,
        };
      }
    }
  );

  return server;
}
