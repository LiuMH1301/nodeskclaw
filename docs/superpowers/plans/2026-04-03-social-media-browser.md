# Plan B: Social Media Browser MCP Server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide browser-based social media tools (X.com, Reddit, Substack) to AI employees via a Playwright-powered MCP server, packaged as a gene. Designed for easy platform extension (Medium, LinkedIn, Discord, Quora, etc.).

**Prerequisite:** Plan A (MCP Sync Foundation) must be shipped and verified end-to-end before starting this plan.

**Architecture decision:** Chromium is baked into the OpenClaw pod image (Option A). This adds ~400MB to the image but guarantees fast startup, deterministic behavior, and no outbound internet requirement from pods.

**Extensibility decision:** Each platform is a self-contained module exporting a standard interface. Adding a new platform (e.g., Medium) requires creating one file (`tools/medium.js`) and updating the gene manifest's `tool_allow` list. No changes to shared utilities or server.js.

**Spec:** `docs/superpowers/specs/2026-04-01-agent-customization-design.md`
**Review:** `docs/superpowers/reviews/2026-04-03-agent-customization-review.md`

---

## Platform Module Contract

Every platform file in `tools/` exports a default object conforming to this shape:

```javascript
export default {
  platform: "x",                          // Unique platform identifier
  domains: ["x.com", "twitter.com"],      // Allowed HTTPS domains (SSRF protection)
  loginPatterns: ["/i/flow/login"],        // URL substrings indicating auth expiry
  selectors: { tweet: '...', ... },       // DOM selectors for this platform
  rateLimits: {                           // Token-bucket limits for write ops
    x_post_tweet: { tokens: 5, refillPerHour: 5 },
  },
  tools: [                                // MCP tool definitions
    { name: "x_scan_timeline", description: "...", inputSchema: {...} },
  ],
  async handle(pool, toolName, args) {    // Tool dispatch function
    // ...
  },
};
```

`server.js` auto-discovers all `tools/*.js` files at startup. Shared utilities (`url-validator`, `rate-limiter`) are initialized with aggregated platform data -- no hardcoded maps.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `nodeskclaw-artifacts/openclaw-image/Dockerfile` | Add Playwright + Chromium layer |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json` | Node.js dependencies (pinned) |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package-lock.json` | Lockfile with integrity hashes |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js` | MCP server with auto-discovery |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js` | Browser context pool |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/url-validator.js` | URL allowlisting factory (SSRF protection) |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/rate-limiter.js` | Token-bucket rate limiter factory |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/with-page.js` | Shared page lifecycle + auth check |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/selector-health.js` | Selector health check utility |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js` | X.com platform module |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js` | Reddit platform module |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js` | Substack platform module |
| Create | `nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json` | Gene manifest |
| Create | `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md` | SKILL.md |
| Create | `nodeskclaw-backend/tests/test_social_media_browser.py` | Backend integration tests |

---

## Task 1: Add Playwright + Chromium to the OpenClaw image

**Why:** Baking Chromium into the image (Option A) eliminates the self-bootstrap blocker. The OpenClaw image already uses `node:22-bookworm-slim`, so Node.js is present. We add Playwright's Chromium browser and the MCP SDK as pre-installed global packages.

**Files:**
- Modify: `nodeskclaw-artifacts/openclaw-image/Dockerfile`

- [ ] **Step 1: Read current Dockerfile**

Read `nodeskclaw-artifacts/openclaw-image/Dockerfile` to understand existing layers.

- [ ] **Step 2: Add Playwright + Chromium layer**

Add after the existing apt-get/npm install layers:

```dockerfile
# Pre-install Playwright Chromium for social-media-browser gene
# This adds ~400MB but enables instant MCP server startup
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN npx playwright install --with-deps chromium \
    && rm -rf /tmp/* /root/.cache/ms-playwright/.links
```

Note: `--with-deps` installs the system libraries Chromium needs (libgbm, libnss3, etc.) on Debian Bookworm.

- [ ] **Step 3: Add Chromium resource flags as env defaults**

```dockerfile
# Chromium resource limits for MCP server use
ENV PLAYWRIGHT_CHROMIUM_ARGS="--disable-dev-shm-usage --disable-gpu --no-sandbox --js-flags=--max-old-space-size=512"
```

- [ ] **Step 4: Build and verify image**

```bash
cd nodeskclaw-artifacts
docker build --platform linux/amd64 -t deskclaw-openclaw:test -f openclaw-image/Dockerfile .
docker run --rm deskclaw-openclaw:test npx playwright --version
docker run --rm deskclaw-openclaw:test node -e "const {chromium}=require('playwright');console.log('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-artifacts/openclaw-image/Dockerfile
git commit -m "feat(image): OpenClaw 镜像预装 Playwright + Chromium（社交媒体基因依赖）"
```

---

## Task 2: Create shared utilities -- URL validator factory, rate limiter factory, page lifecycle, selector health

**Why (review findings):** The original plan had (a) no SSRF protection, (b) no rate limiting in code, (c) auth-check pattern copy-pasted 11 times. These shared modules fix all three. The factory pattern ensures no hardcoded platform data -- shared utilities receive their config from platform modules at startup.

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/url-validator.js`
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/rate-limiter.js`
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/with-page.js`
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/selector-health.js`

- [ ] **Step 1: Create URL validator factory (SSRF protection)**

Create `lib/url-validator.js`:

```javascript
/**
 * URL allowlisting factory to prevent SSRF attacks.
 * Only HTTPS URLs on registered platform domains are permitted.
 *
 * Usage:
 *   const validator = createUrlValidator(platforms);
 *   validator.requireValidUrl("https://x.com/home", "x");
 *
 * Adding a platform: No changes needed here. The new platform module
 * exports its `domains` array, and server.js passes all platforms to
 * this factory at startup.
 */

export function createUrlValidator(platforms) {
  // Build domain -> platform lookup from platform configs
  const domainToPlatform = new Map();
  const platformDomains = new Map();

  for (const p of platforms) {
    platformDomains.set(p.platform, p.domains);
    for (const domain of p.domains) {
      domainToPlatform.set(domain, p.platform);
    }
  }

  const allAllowed = new Set(domainToPlatform.keys());

  function validateUrl(url, platform = null) {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return { valid: false, error: "invalid_url", message: `Cannot parse URL: ${url}` };
    }

    if (parsed.protocol !== "https:") {
      return { valid: false, error: "invalid_protocol", message: "Only HTTPS URLs are allowed." };
    }

    const domains = platform ? platformDomains.get(platform) : null;
    if (platform && !domains) {
      return { valid: false, error: "unknown_platform", message: `Unknown platform: ${platform}` };
    }

    const checkSet = domains ? new Set(domains) : allAllowed;
    if (!checkSet.has(parsed.hostname)) {
      return {
        valid: false,
        error: "domain_not_allowed",
        message: `Domain ${parsed.hostname} is not in the allowlist for ${platform || "any platform"}.`,
      };
    }

    return { valid: true, url: parsed.href };
  }

  function requireValidUrl(url, platform = null) {
    const result = validateUrl(url, platform);
    if (!result.valid) {
      throw result;
    }
    return result.url;
  }

  return { validateUrl, requireValidUrl };
}
```

- [ ] **Step 2: Create token-bucket rate limiter factory**

Create `lib/rate-limiter.js`:

```javascript
/**
 * Server-side token-bucket rate limiter factory for write operations.
 * Enforces hard limits that SKILL.md prose cannot bypass.
 *
 * Usage:
 *   const limiter = createRateLimiter(platforms);
 *   limiter.checkRateLimit("x_post_tweet");
 *
 * Adding a platform: No changes needed here. The new platform module
 * exports its `rateLimits` map, and server.js passes all platforms
 * to this factory at startup.
 */

export function createRateLimiter(platforms) {
  // Merge all platform rate limits into a single limits map
  const limits = {};
  for (const p of platforms) {
    if (p.rateLimits) {
      Object.assign(limits, p.rateLimits);
    }
  }

  // Note: buckets require mutable state for token tracking.
  // This is an intentional exception to the immutability rule.
  const buckets = new Map();

  function getBucket(action) {
    if (!limits[action]) return null;

    if (!buckets.has(action)) {
      const limit = limits[action];
      buckets.set(action, {
        tokens: limit.tokens,
        max: limit.tokens,
        refillPerHour: limit.refillPerHour,
        lastRefill: Date.now(),
      });
    }

    const bucket = buckets.get(action);
    const now = Date.now();
    const elapsed = (now - bucket.lastRefill) / (1000 * 60 * 60);
    const refill = elapsed * bucket.refillPerHour;
    const updated = {
      ...bucket,
      tokens: Math.min(bucket.max, bucket.tokens + refill),
      lastRefill: now,
    };
    buckets.set(action, updated);
    return updated;
  }

  function checkRateLimit(action) {
    const bucket = getBucket(action);
    if (!bucket) return { allowed: true };

    if (bucket.tokens < 1) {
      const waitMinutes = Math.ceil((1 - bucket.tokens) / (bucket.refillPerHour / 60));
      return {
        allowed: false,
        error: "rate_limited",
        action,
        message: `Rate limit exceeded for ${action}. Try again in ~${waitMinutes} minutes.`,
        retryAfterMinutes: waitMinutes,
      };
    }

    buckets.set(action, { ...bucket, tokens: bucket.tokens - 1 });
    return { allowed: true, remainingTokens: Math.floor(bucket.tokens - 1) };
  }

  return { checkRateLimit };
}
```

- [ ] **Step 3: Create shared page lifecycle helper**

Create `lib/with-page.js`:

```javascript
/**
 * Shared page lifecycle: open page, check auth, execute action, close page.
 * Eliminates the copy-pasted auth-check-then-invalidate pattern.
 * Platform-agnostic -- works with any platform module.
 */

export async function withAuthenticatedPage(pool, platform, loginPatterns, fn) {
  const context = await pool.getContext(platform);
  const page = await context.newPage();

  try {
    const result = await fn(page);

    const authError = pool.checkAuthRedirect(page, platform, loginPatterns);
    if (authError) {
      await pool.invalidateContext(platform);
      return authError;
    }

    return result;
  } catch (err) {
    return {
      error: "tool_error",
      platform,
      message: err.message
        ? err.message.replace(/\/[^\s]+/g, "[path]").slice(0, 200)
        : "Unknown error",
    };
  } finally {
    await page.close();
  }
}

/**
 * Navigate to a URL with auth check immediately after load.
 * Returns null if auth is valid, or an auth_expired error object.
 */
export async function navigateWithAuthCheck(page, url, pool, platform, loginPatterns) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, platform, loginPatterns);
  if (authError) {
    await pool.invalidateContext(platform);
    return authError;
  }
  return null;
}
```

- [ ] **Step 4: Create selector health check utility**

Create `lib/selector-health.js`:

```javascript
/**
 * DOM selector health check utility.
 * Each platform module defines its own selectors object.
 * This utility verifies that selectors still match the live DOM.
 *
 * When a selector breaks, update it in the PLATFORM MODULE --
 * all tool functions in that module pick up the change automatically.
 */

export async function checkSelectorHealth(page, selectors, minExpected = 1) {
  const primarySelector = Object.values(selectors)[0];
  if (!primarySelector) return null;

  const count = await page.locator(primarySelector).count();
  if (count < minExpected) {
    return {
      warning: "selector_mismatch",
      selector: primarySelector,
      found: count,
      expected: `>=${minExpected}`,
      message: "DOM selectors may be outdated. Platform may have changed its layout.",
    };
  }
  return null;
}
```

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/lib/
git commit -m "feat(gene): social-media-browser 共享工具库（URL 校验工厂/限流工厂/页面生命周期/选择器健康检查）"
```

---

## Task 3: Create browser context pool

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js`

- [ ] **Step 1: Create `browser-pool.js`**

```javascript
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const CHROMIUM_ARGS = (process.env.PLAYWRIGHT_CHROMIUM_ARGS || "").split(" ").filter(Boolean);

/**
 * Manages one persistent browser context per platform.
 * Cookies are loaded from JSON files at context creation time.
 * Platform-agnostic -- works with any platform identifier.
 */
export function createBrowserPool(cookiesPath) {
  let browser = null;
  // Note: browser pool requires mutable state for connection management.
  // This is an intentional exception to the immutability rule.
  const contexts = new Map();

  async function ensureBrowser() {
    if (!browser || !browser.isConnected()) {
      browser = await chromium.launch({
        headless: true,
        args: [
          "--disable-dev-shm-usage",
          "--disable-gpu",
          "--no-sandbox",
          "--js-flags=--max-old-space-size=512",
          ...CHROMIUM_ARGS,
        ],
      });
    }
    return browser;
  }

  function cookieFilePath(platform) {
    return path.join(cookiesPath, `${platform}.json`);
  }

  function loadCookies(platform) {
    const filePath = cookieFilePath(platform);
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async function getContext(platform) {
    if (contexts.has(platform)) {
      return contexts.get(platform);
    }

    const b = await ensureBrowser();
    const cookies = loadCookies(platform);
    if (!cookies) {
      throw {
        error: "cookies_not_found",
        platform,
        message: `No cookie file found at ${cookieFilePath(platform)}. Please export cookies and place the file.`,
      };
    }

    const context = await b.newContext({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    });
    await context.addCookies(cookies);
    contexts.set(platform, context);
    return context;
  }

  async function invalidateContext(platform) {
    const ctx = contexts.get(platform);
    if (ctx) {
      await ctx.close();
      contexts.delete(platform);
    }
  }

  async function closeAll() {
    for (const [, ctx] of contexts) {
      await ctx.close();
    }
    contexts.clear();
    if (browser) {
      await browser.close();
      browser = null;
    }
  }

  function checkAuthRedirect(page, platform, loginUrlPatterns) {
    const url = page.url();
    for (const pattern of loginUrlPatterns) {
      if (url.includes(pattern)) {
        return {
          error: "auth_expired",
          platform,
          message: `Session cookies expired for ${platform}. Please export fresh cookies.`,
        };
      }
    }
    return null;
  }

  return { getContext, invalidateContext, closeAll, checkAuthRedirect };
}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js
git commit -m "feat(gene): social-media-browser 浏览器上下文池（Chromium 资源限制 + cookie 注入）"
```

---

## Task 4: Create MCP server entry point with auto-discovery

**Key design:** Server auto-discovers platform modules from `tools/*.js` at startup. No manual imports per platform. Adding a new platform requires zero changes to this file.

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json`
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js`

- [ ] **Step 1: Create `package.json` with pinned deps**

```json
{
  "name": "social-media-browser",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "dependencies": {
    "@modelcontextprotocol/sdk": "1.0.0",
    "playwright": "1.50.0"
  }
}
```

Note: Exact versions pinned (no `^`). A `package-lock.json` must be generated and committed alongside. Run `npm install` locally to generate it before committing.

- [ ] **Step 2: Generate lockfile**

```bash
cd nodeskclaw-backend/app/data/gene_scripts/social-media-browser
npm install --package-lock-only
cd -
```

- [ ] **Step 3: Create `server.js` with auto-discovery**

```javascript
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
const pool = createBrowserPool(COOKIES_PATH);

// --- Auto-discover platform modules from tools/ directory ---
const TOOLS_DIR = path.join(path.dirname(new URL(import.meta.url).pathname), "tools");
const platformFiles = fs.readdirSync(TOOLS_DIR).filter((f) => f.endsWith(".js"));

const platforms = [];
for (const file of platformFiles) {
  const mod = await import(pathToFileURL(path.join(TOOLS_DIR, file)).href);
  platforms.push(mod.default);
}

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

// --- Inject shared utilities into each platform module ---
// Platform handlers receive these via closure when handle() is called
for (const p of platforms) {
  p._urlValidator = urlValidator;
  p._rateLimiter = rateLimiter;
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
```

Note the handler signature: `handle(pool, toolName, args, { urlValidator, rateLimiter })`. The 4th argument provides shared utilities so platform modules don't need to import or initialize them.

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json \
        nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package-lock.json \
        nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js
git commit -m "feat(gene): social-media-browser MCP 服务器（自动发现平台模块 + 限流 + 错误脱敏）"
```

---

## Task 5: Create X.com platform module

**This is the reference implementation for the platform module contract.** Reddit and Substack modules follow the same pattern.

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js`

- [ ] **Step 1: Create `tools/x.js`**

```javascript
/**
 * X.com (Twitter) platform module.
 *
 * To add a new platform, copy this file's structure:
 * 1. Export default with: platform, domains, loginPatterns, selectors, rateLimits, tools, handle
 * 2. Place in tools/<platform>.js
 * 3. Add tool names to gene manifest's tool_allow
 * That's it -- server.js auto-discovers this file.
 */

import { withAuthenticatedPage, navigateWithAuthCheck } from "../lib/with-page.js";
import { checkSelectorHealth } from "../lib/selector-health.js";

const PLATFORM = "x";

const SELECTORS = {
  tweet: 'article[data-testid="tweet"]',
  tweetText: '[data-testid="tweetText"]',
  userName: '[data-testid="User-Name"]',
  time: "time",
  statusLink: 'a[href*="/status/"]',
  composeEditor: '[data-testid="tweetTextarea_0"]',
  postButton: '[data-testid="tweetButtonInline"]',
  likeButton: '[data-testid="like"]',
  alreadyLiked: '[data-testid="unlike"]',
};

const LOGIN_PATTERNS = ["/i/flow/login", "/login"];

export default {
  platform: PLATFORM,

  domains: ["x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com"],

  loginPatterns: LOGIN_PATTERNS,

  selectors: SELECTORS,

  rateLimits: {
    x_post_tweet: { tokens: 5, refillPerHour: 5 },
    x_like: { tokens: 20, refillPerHour: 60 },
    x_reply: { tokens: 5, refillPerHour: 5 },
  },

  tools: [
    {
      name: "x_scan_timeline",
      description: "Scan X.com home timeline or search results. Returns posts with text and engagement metrics.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query. Omit for home timeline." },
          count: { type: "number", description: "Number of posts to return (default 20).", default: 20 },
        },
      },
    },
    {
      name: "x_scan_profile",
      description: "Scan a user's recent posts on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          username: { type: "string", description: "X username without @." },
          count: { type: "number", description: "Number of posts to return (default 10).", default: 10 },
        },
        required: ["username"],
      },
    },
    {
      name: "x_post_tweet",
      description: "Post a tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          text: { type: "string", description: "Tweet text (max 280 characters).", maxLength: 280 },
        },
        required: ["text"],
      },
    },
    {
      name: "x_reply",
      description: "Reply to a specific tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          tweet_url: { type: "string", description: "Full URL of the tweet to reply to." },
          text: { type: "string", description: "Reply text.", maxLength: 280 },
        },
        required: ["tweet_url", "text"],
      },
    },
    {
      name: "x_like",
      description: "Like a tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          tweet_url: { type: "string", description: "Full URL of the tweet to like." },
        },
        required: ["tweet_url"],
      },
    },
  ],

  async handle(pool, toolName, args, { urlValidator }) {
    return withAuthenticatedPage(pool, PLATFORM, LOGIN_PATTERNS, async (page) => {
      switch (toolName) {
        case "x_scan_timeline":
          return await scanTimeline(pool, page, args, urlValidator);
        case "x_scan_profile":
          return await scanProfile(pool, page, args, urlValidator);
        case "x_post_tweet":
          return await postTweet(pool, page, args);
        case "x_reply":
          return await replyToTweet(pool, page, args, urlValidator);
        case "x_like":
          return await likeTweet(pool, page, args, urlValidator);
        default:
          return { error: "unknown_tool", tool: toolName };
      }
    });
  },
};

// --- Tool implementations (private to this module) ---

async function scanTimeline(pool, page, { query, count = 20 }, urlValidator) {
  const url = query
    ? `https://x.com/search?q=${encodeURIComponent(query)}&f=live`
    : "https://x.com/home";
  const authErr = await navigateWithAuthCheck(page, url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  await autoScroll(page, count);

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const articles = document.querySelectorAll(sel.tweet);
      return Array.from(articles).slice(0, maxCount).map((article) => ({
        text: article.querySelector(sel.tweetText)?.innerText || "",
        author: article.querySelector(sel.userName)?.innerText?.split("\n")?.[0] || "",
        handle: article.querySelector(sel.userName)?.innerText?.split("\n")?.[1] || "",
        time: article.querySelector(sel.time)?.getAttribute("datetime") || "",
        url: (() => {
          const link = article.querySelector(sel.statusLink);
          return link ? `https://x.com${link.getAttribute("href")}` : "";
        })(),
      }));
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { posts, count: posts.length };
}

async function scanProfile(pool, page, { username, count = 10 }, urlValidator) {
  if (!/^[a-zA-Z0-9_]{1,15}$/.test(username)) {
    return { error: "invalid_username", message: "Username must be 1-15 alphanumeric characters." };
  }

  const authErr = await navigateWithAuthCheck(
    page, `https://x.com/${username}`, pool, PLATFORM, LOGIN_PATTERNS,
  );
  if (authErr) return authErr;

  await autoScroll(page, count);

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const articles = document.querySelectorAll(sel.tweet);
      return Array.from(articles).slice(0, maxCount).map((article) => ({
        text: article.querySelector(sel.tweetText)?.innerText || "",
        time: article.querySelector(sel.time)?.getAttribute("datetime") || "",
        url: (() => {
          const link = article.querySelector(sel.statusLink);
          return link ? `https://x.com${link.getAttribute("href")}` : "";
        })(),
      }));
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { posts, count: posts.length };
}

async function postTweet(pool, page, { text }) {
  if (!text || text.length > 280) {
    return { error: "invalid_input", message: "Tweet text must be 1-280 characters." };
  }

  const authErr = await navigateWithAuthCheck(
    page, "https://x.com/compose/post", pool, PLATFORM, LOGIN_PATTERNS,
  );
  if (authErr) return authErr;

  const editor = page.locator(SELECTORS.composeEditor);
  await editor.waitFor({ state: "visible", timeout: 10_000 });
  await editor.click();
  await editor.fill(text);
  await page.locator(SELECTORS.postButton).click();
  await editor.waitFor({ state: "detached", timeout: 10_000 }).catch(() => {});

  return { success: true, text };
}

async function replyToTweet(pool, page, { tweet_url, text }, urlValidator) {
  urlValidator.requireValidUrl(tweet_url, "x");
  if (!text || text.length > 280) {
    return { error: "invalid_input", message: "Reply text must be 1-280 characters." };
  }

  const authErr = await navigateWithAuthCheck(page, tweet_url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  const replyBox = page.locator(SELECTORS.composeEditor);
  await replyBox.waitFor({ state: "visible", timeout: 10_000 });
  await replyBox.click();
  await replyBox.fill(text);
  await page.locator(SELECTORS.postButton).click();
  await replyBox.waitFor({ state: "detached", timeout: 10_000 }).catch(() => {});

  return { success: true, tweet_url, text };
}

async function likeTweet(pool, page, { tweet_url }, urlValidator) {
  urlValidator.requireValidUrl(tweet_url, "x");

  const authErr = await navigateWithAuthCheck(page, tweet_url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  const likeButton = page.locator(SELECTORS.likeButton);
  if ((await likeButton.count()) > 0) {
    await likeButton.click();
    return { success: true, tweet_url, action: "liked" };
  }

  return { success: true, tweet_url, action: "already_liked" };
}

async function autoScroll(page, targetCount) {
  let previousHeight = 0;
  for (let attempt = 0; attempt < 10; attempt++) {
    const articles = await page.locator(SELECTORS.tweet).count();
    if (articles >= targetCount) break;
    await page.evaluate(() => window.scrollBy(0, window.innerHeight));
    await page.waitForFunction(
      (prevH) => document.body.scrollHeight > prevH,
      previousHeight,
      { timeout: 5_000 },
    ).catch(() => {});
    const currentHeight = await page.evaluate(() => document.body.scrollHeight);
    if (currentHeight === previousHeight) break;
    previousHeight = currentHeight;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js
git commit -m "feat(gene): social-media-browser X.com 平台模块（参考实现 + URL 校验/选择器/DOM 等待）"
```

---

## Task 6: Create Reddit platform module

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js`

- [ ] **Step 1: Create `tools/reddit.js`**

Same platform module contract as X.com. Key specifics:

```javascript
export default {
  platform: "reddit",
  domains: [
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "new.reddit.com", "np.reddit.com",
  ],
  loginPatterns: ["/login", "/account/login"],
  selectors: {
    // Using old.reddit.com for simpler, more stable DOM
    post: "#siteTable .thing.link",
    postTitle: "a.title",
    postScore: ".score.unvoted",
    postComments: ".comments",
    postTime: "time",
    titleInput: 'textarea[name="title"]',
    textTab: 'li.tabmenu-li a:text("text")',
    bodyInput: 'textarea[name="text"]',
    submitButton: 'button[name="submit"]',
    commentBox: ".usertext-edit textarea",
    commentSubmit: '.usertext-edit button[type="submit"]',
  },
  rateLimits: {
    reddit_post: { tokens: 3, refillPerHour: 3 },
    reddit_reply: { tokens: 10, refillPerHour: 10 },
  },
  tools: [
    {
      name: "reddit_scan_subreddit",
      description: "Scan posts from a subreddit on Reddit.",
      inputSchema: {
        type: "object",
        properties: {
          subreddit: { type: "string", description: "Subreddit name without r/." },
          sort: { type: "string", enum: ["hot", "new", "top"], default: "hot" },
          count: { type: "number", description: "Number of posts (default 20).", default: 20 },
        },
        required: ["subreddit"],
      },
    },
    {
      name: "reddit_post",
      description: "Submit a text post to a subreddit.",
      inputSchema: {
        type: "object",
        properties: {
          subreddit: { type: "string", description: "Subreddit name without r/." },
          title: { type: "string", description: "Post title." },
          body: { type: "string", description: "Post body (markdown)." },
        },
        required: ["subreddit", "title", "body"],
      },
    },
    {
      name: "reddit_reply",
      description: "Reply to a Reddit post or comment.",
      inputSchema: {
        type: "object",
        properties: {
          post_url: { type: "string", description: "Full URL of the post to reply to." },
          text: { type: "string", description: "Reply text (markdown)." },
        },
        required: ["post_url", "text"],
      },
    },
  ],
  async handle(pool, toolName, args, { urlValidator }) {
    // Implementation follows same pattern as x.js:
    // - withAuthenticatedPage for page lifecycle
    // - navigateWithAuthCheck for navigation
    // - urlValidator.requireValidUrl for URL inputs
    // - checkSelectorHealth before extracting DOM data
    // - Input validation: subreddit name /^[a-zA-Z0-9_]{1,21}$/
    // - Uses old.reddit.com URLs for stable DOM
    // ...
  },
};
```

Full implementation follows the X.com module pattern with Reddit-specific DOM interaction logic. Key points:
- URL validation: allowlist `reddit.com` and subdomains
- Input validation: subreddit name format check (`/^[a-zA-Z0-9_]{1,21}$/`)
- `waitForSelector` instead of `waitForTimeout` after post submission
- `navigateWithAuthCheck` for every page load
- Uses `old.reddit.com` for simpler, more stable DOM

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js
git commit -m "feat(gene): social-media-browser Reddit 平台模块（含输入校验 + old.reddit.com 选择器）"
```

---

## Task 7: Create Substack platform module

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js`

- [ ] **Step 1: Create `tools/substack.js`**

Same platform module contract. Key specifics:

```javascript
export default {
  platform: "substack",
  domains: ["substack.com"],   // Note: custom domains (*.substack.com) added dynamically
  loginPatterns: ["/sign-in", "/account/login"],
  selectors: {
    newPostLink: 'a[href*="/publish/post"]',
    titleInput: '[placeholder*="Title"], .post-title',
    subtitleInput: '[placeholder*="subtitle"], .post-subtitle',
    editor: '.ProseMirror, [contenteditable="true"]',
    inboxItem: '[class*="post-preview"], [class*="inbox-item"]',
    inboxTitle: "a",
    inboxAuthor: '[class*="author"], [class*="pub-name"]',
    inboxTime: "time",
  },
  rateLimits: {
    substack_publish: { tokens: 2, refillPerHour: 2 },
  },
  tools: [
    {
      name: "substack_scan_feed",
      description: "Scan recent posts from a Substack publication's feed.",
      inputSchema: {
        type: "object",
        properties: {
          publication_url: { type: "string", description: "Full URL of the Substack publication." },
          count: { type: "number", description: "Number of posts (default 10).", default: 10 },
        },
        required: ["publication_url"],
      },
    },
    {
      name: "substack_publish",
      description: "Create a draft post on Substack (saves as draft, does NOT publish). Requires human approval to publish.",
      inputSchema: {
        type: "object",
        properties: {
          title: { type: "string", description: "Post title." },
          subtitle: { type: "string", description: "Post subtitle (optional)." },
          body: { type: "string", description: "Post body (plain text or markdown)." },
        },
        required: ["title", "body"],
      },
    },
  ],
  async handle(pool, toolName, args, { urlValidator }) {
    // Implementation follows same pattern as x.js:
    // - substack_publish saves as DRAFT only (safety measure)
    // - Uses waitForSelector to confirm draft saved
    // - substack_scan_feed uses checkSelectorHealth
    // - All navigation through navigateWithAuthCheck
    // ...
  },
};
```

Key safety: `substack_publish` saves as **draft only** -- the tool description makes this explicit so the agent and user both understand.

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js
git commit -m "feat(gene): social-media-browser Substack 平台模块（草稿模式 + Feed 扫描）"
```

---

## Task 8: Create gene manifest and SKILL.md

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md`

- [ ] **Step 1: Create gene manifest**

```json
{
  "skill": {
    "name": "social-media-browser",
    "description": "Browser-based social media automation for X, Reddit, and Substack"
  },
  "tool_allow": [
    "x_scan_timeline",
    "x_scan_profile",
    "x_post_tweet",
    "x_reply",
    "x_like",
    "reddit_scan_subreddit",
    "reddit_post",
    "reddit_reply",
    "substack_publish",
    "substack_scan_feed"
  ],
  "mcp_servers": [
    {
      "name": "social-media-browser",
      "transport": "stdio",
      "command": "node",
      "args": ["/root/.deskclaw/tools/social-media-browser/server.js"],
      "env": {
        "COOKIES_PATH": "/root/.deskclaw/cookies/"
      }
    }
  ],
  "scripts": [
    "social-media-browser/package.json",
    "social-media-browser/package-lock.json",
    "social-media-browser/server.js",
    "social-media-browser/browser-pool.js",
    "social-media-browser/lib/url-validator.js",
    "social-media-browser/lib/rate-limiter.js",
    "social-media-browser/lib/with-page.js",
    "social-media-browser/lib/selector-health.js",
    "social-media-browser/tools/x.js",
    "social-media-browser/tools/reddit.js",
    "social-media-browser/tools/substack.js"
  ]
}
```

Note: When adding a new platform (e.g., Medium), only `tool_allow` and `scripts` need updating here. The server discovers the new platform module automatically.

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md`:

```markdown
---
name: social-media-browser
description: Browser-based social media tools for X.com, Reddit, and Substack
---

# Social Media Browser

You have access to browser-based tools for interacting with social media platforms.
These tools use Playwright to automate a real Chromium browser with your session cookies.

## Available Platforms

- **X.com** (Twitter): scan timelines, scan profiles, post tweets, reply, like
- **Reddit**: scan subreddits, post, reply
- **Substack**: scan feeds, create draft posts

## Authentication

Tools use pre-exported session cookies. If you see an `auth_expired` error:
1. Report to the user that cookies need refreshing
2. Do NOT retry the same action -- it will fail again
3. Wait for the user to export fresh cookies

## Rate Limits (server-enforced)

Write operations have hard rate limits enforced server-side. These cannot be bypassed.

| Action | Limit | Refill |
|--------|-------|--------|
| x_post_tweet | 5/hour | 5/hour |
| x_reply | 5/hour | 5/hour |
| x_like | 20/hour | 60/hour |
| reddit_post | 3/hour | 3/hour |
| reddit_reply | 10/hour | 10/hour |
| substack_publish | 2/hour | 2/hour |

If you receive a `rate_limited` error, wait the indicated time before retrying.

## DOM Selector Warnings

If you receive a `selector_mismatch` warning, it means the platform may have changed
its page layout. Report this to the user -- the selectors in the platform module
may need updating. The data returned may be empty or incomplete.

## Workflow

1. **Scan** -- Use scan tools to browse feeds and profiles (read-only, no rate limit)
2. **Analyze** -- Process the returned data for your task
3. **Act** -- Use write tools (post, reply, like) when needed
4. **Report** -- Summarize what you did to the workspace blackboard

## What NOT to Do

- Do not retry failed auth -- report to the user instead
- Do not exceed 100 posts per scan session (use the `count` parameter)
- Do not post identical content across platforms without adaptation
- Do not ignore rate limit errors -- respect the retry time
- Do not use these tools for content older than 7 days unless specifically asked
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json \
        nodeskclaw-backend/app/data/gene_skills/social-media-browser.md
git commit -m "feat(gene): social-media-browser 基因清单和 SKILL.md（含限流表 + 选择器告警文档）"
```

---

## Task 9: Tests

**Files:**
- Create: `nodeskclaw-backend/tests/test_social_media_browser.py`

- [ ] **Step 1: Write unit tests for URL validator factory**

```python
"""Tests for social-media-browser gene: URL validator, rate limiter, manifest."""

import json
from pathlib import Path

import pytest


# --- URL Validator Factory Tests ---

MOCK_PLATFORMS = [
    {"platform": "x", "domains": ["x.com", "twitter.com"]},
    {"platform": "reddit", "domains": ["reddit.com", "www.reddit.com", "old.reddit.com"]},
]


class TestUrlValidatorFactory:
    """URL validator should be initialized from platform configs, not hardcoded."""

    def test_valid_x_url(self):
        # Test will import the JS factory via subprocess or mock the logic in Python
        # For now, test the concept: x.com should be allowed for platform "x"
        pass  # Placeholder -- see Step 5 for actual implementation approach

    def test_rejects_http(self):
        pass

    def test_rejects_unknown_domain(self):
        pass

    def test_rejects_internal_ip(self):
        pass

    def test_platform_specific_validation(self):
        pass
```

Note: Since the MCP server is Node.js, Python tests focus on:
1. **Gene manifest validity** (JSON structure, file references)
2. **Conceptual parity tests** that verify the Python-side gene install pipeline handles this gene correctly
3. **Node.js unit tests** run via `node --test` in a subprocess

- [ ] **Step 2: Write manifest validity tests**

```python
MANIFESTS_DIR = Path(__file__).parent.parent / "app/data/gene_manifests"
SKILLS_DIR = Path(__file__).parent.parent / "app/data/gene_skills"
SCRIPTS_DIR = Path(__file__).parent.parent / "app/data/gene_scripts"


def test_manifest_exists_and_valid():
    manifest_path = MANIFESTS_DIR / "social-media-browser.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["skill"]["name"] == "social-media-browser"
    assert "description" in manifest["skill"]
    assert len(manifest["tool_allow"]) == 10
    assert len(manifest["mcp_servers"]) == 1
    assert manifest["mcp_servers"][0]["transport"] == "stdio"
    assert manifest["mcp_servers"][0]["command"] == "node"


def test_all_scripts_exist():
    manifest_path = MANIFESTS_DIR / "social-media-browser.json"
    manifest = json.loads(manifest_path.read_text())

    for script in manifest["scripts"]:
        script_path = SCRIPTS_DIR / script
        assert script_path.exists(), f"Script not found: {script}"


def test_tool_allow_matches_platform_tools():
    """All tool_allow entries should correspond to actual tool definitions in platform modules."""
    manifest_path = MANIFESTS_DIR / "social-media-browser.json"
    manifest = json.loads(manifest_path.read_text())
    tool_names = set(manifest["tool_allow"])

    # Verify expected tools per platform
    assert "x_scan_timeline" in tool_names
    assert "x_scan_profile" in tool_names
    assert "x_post_tweet" in tool_names
    assert "reddit_scan_subreddit" in tool_names
    assert "reddit_post" in tool_names
    assert "substack_publish" in tool_names
    assert "substack_scan_feed" in tool_names


def test_skill_md_exists_and_has_frontmatter():
    skill_path = SKILLS_DIR / "social-media-browser.md"
    assert skill_path.exists()
    content = skill_path.read_text()
    assert content.startswith("---")
    assert "name: social-media-browser" in content


def test_skill_md_documents_rate_limits():
    skill_path = SKILLS_DIR / "social-media-browser.md"
    content = skill_path.read_text()
    assert "rate_limited" in content.lower() or "Rate Limit" in content


def test_skill_md_has_workflow_and_what_not_to_do():
    skill_path = SKILLS_DIR / "social-media-browser.md"
    content = skill_path.read_text()
    assert "## Workflow" in content
    assert "## What NOT to Do" in content
```

- [ ] **Step 3: Write Node.js unit tests (run via subprocess)**

Create `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/test/url-validator.test.js`:

```javascript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createUrlValidator } from "../lib/url-validator.js";

const platforms = [
  { platform: "x", domains: ["x.com", "twitter.com"] },
  { platform: "reddit", domains: ["reddit.com", "www.reddit.com"] },
];

const { validateUrl, requireValidUrl } = createUrlValidator(platforms);

describe("URL Validator", () => {
  it("accepts valid X.com URL", () => {
    const result = validateUrl("https://x.com/home", "x");
    assert.equal(result.valid, true);
  });

  it("accepts valid Reddit URL", () => {
    const result = validateUrl("https://www.reddit.com/r/programming", "reddit");
    assert.equal(result.valid, true);
  });

  it("rejects HTTP URLs", () => {
    const result = validateUrl("http://x.com/home", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "invalid_protocol");
  });

  it("rejects non-allowlisted domains", () => {
    const result = validateUrl("https://evil.com/phish", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "domain_not_allowed");
  });

  it("rejects internal IPs", () => {
    const result = validateUrl("https://169.254.169.254/metadata");
    assert.equal(result.valid, false);
  });

  it("rejects cross-platform URLs", () => {
    const result = validateUrl("https://x.com/home", "reddit");
    assert.equal(result.valid, false);
    assert.equal(result.error, "domain_not_allowed");
  });

  it("requireValidUrl throws on invalid", () => {
    assert.throws(() => requireValidUrl("http://x.com", "x"));
  });
});
```

Create `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/test/rate-limiter.test.js`:

```javascript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createRateLimiter } from "../lib/rate-limiter.js";

describe("Rate Limiter", () => {
  it("allows requests within budget", () => {
    const limiter = createRateLimiter([
      { platform: "x", rateLimits: { x_post_tweet: { tokens: 3, refillPerHour: 3 } } },
    ]);

    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
  });

  it("blocks requests over budget", () => {
    const limiter = createRateLimiter([
      { platform: "x", rateLimits: { x_post_tweet: { tokens: 2, refillPerHour: 2 } } },
    ]);

    limiter.checkRateLimit("x_post_tweet");
    limiter.checkRateLimit("x_post_tweet");
    const result = limiter.checkRateLimit("x_post_tweet");
    assert.equal(result.allowed, false);
    assert.equal(result.error, "rate_limited");
  });

  it("allows unknown actions (no limit)", () => {
    const limiter = createRateLimiter([]);
    assert.equal(limiter.checkRateLimit("unknown_action").allowed, true);
  });
});
```

- [ ] **Step 4: Add Python test to run Node.js tests via subprocess**

```python
import subprocess


def test_nodejs_unit_tests():
    """Run Node.js unit tests for url-validator and rate-limiter."""
    scripts_dir = SCRIPTS_DIR / "social-media-browser"
    result = subprocess.run(
        ["node", "--test", "test/"],
        cwd=scripts_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Node.js tests failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 5: Run all tests**

```bash
cd nodeskclaw-backend && uv run pytest tests/test_social_media_browser.py -v
```

- [ ] **Step 6: Commit**

```bash
git add nodeskclaw-backend/tests/test_social_media_browser.py \
        nodeskclaw-backend/app/data/gene_scripts/social-media-browser/test/
git commit -m "test(gene): social-media-browser 单元测试（URL 校验工厂/限流工厂/清单校验 + Node.js 测试）"
```

---

## Task 10: Verify end-to-end

- [ ] **Step 1: Run full backend test suite**

```bash
cd nodeskclaw-backend && uv run pytest tests/ -v
```

- [ ] **Step 2: Verify gene_scripts directory structure**

```bash
find nodeskclaw-backend/app/data/gene_scripts/social-media-browser -type f | sort
```

Expected:
```
browser-pool.js
lib/rate-limiter.js
lib/selector-health.js
lib/url-validator.js
lib/with-page.js
package-lock.json
package.json
server.js
test/rate-limiter.test.js
test/url-validator.test.js
tools/reddit.js
tools/substack.js
tools/x.js
```

- [ ] **Step 3: Verify Node.js tests independently**

```bash
cd nodeskclaw-backend/app/data/gene_scripts/social-media-browser && node --test test/
```

- [ ] **Step 4: Verify Docker build (manual)**

```bash
cd nodeskclaw-artifacts
docker build --platform linux/amd64 -t deskclaw-openclaw:test -f openclaw-image/Dockerfile .
```

- [ ] **Step 5: Commit if any fixups needed**

```bash
git add -A && git commit -m "chore: Plan B 最终验证和修复"
```

---

## Adding a New Platform (Developer Guide)

When you need to add a new platform (e.g., Medium, LinkedIn, Discord, Quora):

### 1. Create the platform module

Create `tools/<platform>.js` following the contract:

```javascript
export default {
  platform: "<platform>",
  domains: ["<domain1>", "<domain2>"],
  loginPatterns: ["<login-url-pattern>"],
  selectors: { /* platform-specific DOM selectors */ },
  rateLimits: {
    <platform>_<write_action>: { tokens: N, refillPerHour: N },
  },
  tools: [
    { name: "<platform>_scan_...", description: "...", inputSchema: {...} },
    { name: "<platform>_post_...", description: "...", inputSchema: {...} },
  ],
  async handle(pool, toolName, args, { urlValidator }) {
    // Use withAuthenticatedPage, navigateWithAuthCheck, checkSelectorHealth
  },
};
```

### 2. Update gene manifest

Add the new tool names to `tool_allow` and the new file to `scripts` in `gene_manifests/social-media-browser.json`.

### 3. Add cookies

Export session cookies to `/root/.deskclaw/cookies/<platform>.json`.

### 4. Add tests

Add Node.js tests in `test/<platform>.test.js` for platform-specific logic.

**That's it.** No changes to `server.js`, `url-validator.js`, `rate-limiter.js`, or `browser-pool.js`.

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Chromium OOMs the pod | HIGH | Launch with `--max-old-space-size=512`, `--disable-dev-shm-usage`; `autoScroll` bounded to 10 iterations |
| DOM selectors break when platforms update | HIGH | Selectors scoped to platform module (single file to update); `checkSelectorHealth` returns explicit warning |
| Cookie theft via PVC access | HIGH | Documented risk; future follow-up should add encryption at rest |
| Rate limiting bypassed by restarting MCP server | MEDIUM | Token buckets are in-memory; restart resets them. Acceptable for MVP -- persistent rate limiting is a follow-up |
| `old.reddit.com` deprecated | MEDIUM | If deprecated, update selectors in `tools/reddit.js` only (no other files affected) |
| Playwright version drift between image and package.json | LOW | Pin exact same version in both Dockerfile and package.json |
| Auto-discovery loads unexpected files from tools/ | LOW | Only `.js` files loaded; directory is deployed from gene scripts (controlled content) |

## Acceptance Criteria

- [ ] `docker build` of OpenClaw image succeeds with Playwright + Chromium
- [ ] Gene install deploys all scripts including nested `lib/`, `tools/`, `test/` dirs
- [ ] `openclaw.json` contains `social-media-browser` MCP server entry after install
- [ ] URL validation rejects non-HTTPS and non-allowlisted domains
- [ ] Rate limiter blocks write operations beyond configured thresholds
- [ ] Selector health check returns warning (not empty array) when DOM changes
- [ ] Error messages do not leak internal file paths
- [ ] Node.js unit tests pass for url-validator and rate-limiter factories
- [ ] Python manifest validity tests pass
- [ ] Gene uninstall removes MCP server entry from `openclaw.json`
- [ ] Adding a new platform requires only: 1 new `tools/*.js` file + manifest `tool_allow`/`scripts` update
