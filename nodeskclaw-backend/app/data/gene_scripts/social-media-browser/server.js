import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { createBrowserPool } from "./browser-pool.js";
import { createUrlValidator } from "./lib/url-validator.js";
import { createRateLimiter } from "./lib/rate-limiter.js";

const COOKIES_PATH = process.env.COOKIES_PATH || "/root/.deskclaw/cookies/";

// --- Auto-discover platform modules from tools/ directory ---
const TOOLS_DIR = path.join(path.dirname(new URL(import.meta.url).pathname), "tools");
const platformFiles = fs.readdirSync(TOOLS_DIR).filter((f) => f.endsWith(".js"));

const platforms = [];
for (const file of platformFiles) {
  const mod = await import(pathToFileURL(path.join(TOOLS_DIR, file)).href);
  platforms.push(mod.default);
}

// Build platform -> domains lookup for cookie validation
const platformDomainsMap = new Map();
for (const p of platforms) {
  platformDomainsMap.set(p.platform, p.domains);
}

const pool = createBrowserPool(COOKIES_PATH, platformDomainsMap);

// --- Initialize shared utilities from aggregated platform data ---
const urlValidator = createUrlValidator(platforms);
const rateLimiter = createRateLimiter(platforms);

// --- Build tool registry ---
const ALL_TOOLS = platforms.flatMap((p) => p.tools);
const TOOL_HANDLERS = new Map();
for (const p of platforms) {
  for (const t of p.tools) {
    TOOL_HANDLERS.set(t.name, p.handle);
  }
}

// Build rate-limited action set from platform rateLimits keys
const RATE_LIMITED_ACTIONS = new Set();
for (const p of platforms) {
  if (p.rateLimits) {
    for (const action of Object.keys(p.rateLimits)) {
      RATE_LIMITED_ACTIONS.add(action);
    }
  }
}

// --- MCP server setup ---
const server = new Server(
  { name: "social-media-browser", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: ALL_TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  // Check rate limit for write operations (tool name matches rateLimits key)
  if (RATE_LIMITED_ACTIONS.has(name)) {
    const limit = rateLimiter.checkRateLimit(name);
    if (!limit.allowed) {
      return {
        content: [{ type: "text", text: JSON.stringify(limit) }],
        isError: true,
      };
    }
  }

  const handler = TOOL_HANDLERS.get(name);
  if (!handler) {
    return {
      content: [{ type: "text", text: JSON.stringify({ error: "unknown_tool", tool: name }) }],
      isError: true,
    };
  }

  try {
    const result = await handler(pool, name, args, { urlValidator, rateLimiter });
    return {
      content: [{ type: "text", text: JSON.stringify(result) }],
      isError: !!result.error,
    };
  } catch (err) {
    const safeMessage = (err.message || "Unknown error")
      .replace(/\/[^\s]+/g, "[path]")
      .slice(0, 200);
    return {
      content: [{ type: "text", text: JSON.stringify({ error: "internal_error", message: safeMessage }) }],
      isError: true,
    };
  }
});

process.on("SIGINT", async () => {
  await pool.closeAll();
  process.exit(0);
});
process.on("SIGTERM", async () => {
  await pool.closeAll();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);
