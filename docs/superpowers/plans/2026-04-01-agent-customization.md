# Agent Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable AI employees to use custom skills, automate social media via Playwright, and generate images/video via external APIs -- all packaged as genes with MCP servers.

**Architecture:** Each capability is a gene manifest containing a SKILL.md, MCP server definition, tool allow-list, and server scripts. The existing gene install pipeline deploys skills and scripts to the pod's PVC via `kubectl exec`. A new `sync_mcp_servers()` method bridges the gap between `InstanceMcpServer` DB records and the pod's `openclaw.json`.

**Tech Stack:** Python (FastAPI backend), Node.js (@modelcontextprotocol/sdk + Playwright), Python (mcp SDK + httpx)

**Spec:** `docs/superpowers/specs/2026-04-01-agent-customization-design.md`

---

## File Structure

### Phase 1: MCP Sync Fix

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py` | Add abstract `sync_mcp_servers()` method |
| Modify | `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py` | Implement `sync_mcp_servers()` |
| Modify | `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py` | Add no-op `sync_mcp_servers()` |
| Modify | `nodeskclaw-backend/app/services/gene_service.py` | Call `sync_mcp_servers()` after MCP injection and on uninstall |
| Create | `nodeskclaw-backend/tests/test_mcp_sync.py` | Unit tests for MCP sync |

### Phase 2: Social Media Browser MCP Server

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js` | MCP server entry point with bootstrap |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json` | Node.js dependencies |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js` | Persistent browser context pool |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js` | X.com tool implementations |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js` | Reddit tool implementations |
| Create | `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js` | Substack tool implementations |
| Create | `nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json` | Gene manifest |
| Create | `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md` | SKILL.md for the gene |

### Phase 3: Media Generator MCP Server

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py` | MCP server entry point with bootstrap |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/requirements.txt` | Python dependencies |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py` | Provider registry |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai_images.py` | OpenAI DALL-E + Vision |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway_video.py` | Runway video generation |
| Create | `nodeskclaw-backend/app/data/gene_manifests/media-generator.json` | Gene manifest |
| Create | `nodeskclaw-backend/app/data/gene_skills/media-generator.md` | SKILL.md for the gene |

### Phase 4: Behavioral Skills

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md` | SKILL.md template |
| Create | `nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md` | SKILL.md template |
| Create | `nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md` | SKILL.md template |

---

## Task 1: Add `sync_mcp_servers()` to the abstract adapter

**Files:**
- Modify: `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py:23-59`
- Modify: `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
"""Tests for MCP server sync between DB records and openclaw.json."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.runtime.openclaw_gene_install_adapter import OpenClawGeneInstallAdapter


@pytest.mark.asyncio
async def test_sync_mcp_servers_writes_config():
    """sync_mcp_servers should write mcpServers section into openclaw.json."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    mcp_records = [
        MagicMock(
            name="social-media-browser",
            transport="stdio",
            command="node",
            url=None,
            args=["/root/.deskclaw/tools/social-media-browser/server.js"],
            env={"COOKIES_PATH": "/root/.deskclaw/cookies/"},
            is_active=True,
        ),
    ]

    fs.read_text = AsyncMock(return_value=json.dumps({"skills": {}}))
    fs.write_text = AsyncMock()

    await adapter.sync_mcp_servers(fs, mcp_records)

    written = fs.write_text.call_args[0]
    assert written[0] == ".openclaw/openclaw.json"
    config = json.loads(written[1])
    assert "mcpServers" in config
    assert "social-media-browser" in config["mcpServers"]
    srv = config["mcpServers"]["social-media-browser"]
    assert srv["transport"] == "stdio"
    assert srv["command"] == "node"
    assert srv["args"] == ["/root/.deskclaw/tools/social-media-browser/server.js"]
    assert srv["env"]["COOKIES_PATH"] == "/root/.deskclaw/cookies/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py::test_sync_mcp_servers_writes_config -v`
Expected: FAIL with `AttributeError: 'OpenClawGeneInstallAdapter' object has no attribute 'sync_mcp_servers'`

- [ ] **Step 3: Add abstract method to `GeneInstallAdapter`**

In `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py`, add after the `post_remove_cleanup` method (line 59):

```python
    @abstractmethod
    async def sync_mcp_servers(self, fs: "RemoteFS", mcp_records: list) -> None:
        """Sync active MCP server records into runtime config.

        Args:
            fs: Remote filesystem handle.
            mcp_records: List of InstanceMcpServer model instances.
        """
```

- [ ] **Step 4: Add no-op to `NoopGeneInstallAdapter`**

In `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py`, add:

```python
    async def sync_mcp_servers(self, fs: RemoteFS, mcp_records: list) -> None:
        pass
```

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-backend/app/services/runtime/gene_install_adapter.py \
        nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "refactor(gene): GeneInstallAdapter 新增 sync_mcp_servers 抽象方法"
```

---

## Task 2: Implement `sync_mcp_servers()` in `OpenClawGeneInstallAdapter`

**Files:**
- Modify: `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py:26-142`
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Implement `sync_mcp_servers`**

In `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py`, add after `apply_config` (after line 92):

```python
    async def sync_mcp_servers(self, fs: RemoteFS, mcp_records: list) -> None:
        """Sync active InstanceMcpServer records into openclaw.json mcpServers section."""
        try:
            config = await self._read_config(fs)
        except ValueError:
            logger.warning("sync_mcp_servers: openclaw.json 解析失败，跳过 MCP 同步")
            return

        mcp_servers: dict = {}
        for rec in mcp_records:
            if not rec.is_active:
                continue
            entry: dict = {"transport": rec.transport}
            if rec.command:
                entry["command"] = rec.command
            if rec.url:
                entry["url"] = rec.url
            if rec.args:
                entry["args"] = rec.args
            if rec.env:
                entry["env"] = rec.env
            mcp_servers[rec.name] = entry

        config["mcpServers"] = mcp_servers
        await self._write_config(fs, config)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py::test_sync_mcp_servers_writes_config -v`
Expected: PASS

- [ ] **Step 3: Write test for empty records (cleans up stale entries)**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
@pytest.mark.asyncio
async def test_sync_mcp_servers_empty_clears_section():
    """sync_mcp_servers with empty list should write empty mcpServers."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    existing_config = {
        "skills": {},
        "mcpServers": {
            "old-server": {"transport": "stdio", "command": "old"}
        },
    }
    fs.read_text = AsyncMock(return_value=json.dumps(existing_config))
    fs.write_text = AsyncMock()

    await adapter.sync_mcp_servers(fs, [])

    config = json.loads(fs.write_text.call_args[0][1])
    assert config["mcpServers"] == {}
```

- [ ] **Step 4: Run all MCP sync tests**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Write test for multiple servers and inactive filtering**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
@pytest.mark.asyncio
async def test_sync_mcp_servers_filters_inactive():
    """sync_mcp_servers should skip records with is_active=False."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    mcp_records = [
        MagicMock(
            name="active-server",
            transport="stdio",
            command="node",
            url=None,
            args=None,
            env=None,
            is_active=True,
        ),
        MagicMock(
            name="inactive-server",
            transport="stdio",
            command="python",
            url=None,
            args=None,
            env=None,
            is_active=False,
        ),
    ]

    fs.read_text = AsyncMock(return_value=json.dumps({}))
    fs.write_text = AsyncMock()

    await adapter.sync_mcp_servers(fs, mcp_records)

    config = json.loads(fs.write_text.call_args[0][1])
    assert "active-server" in config["mcpServers"]
    assert "inactive-server" not in config["mcpServers"]
```

- [ ] **Step 6: Run all MCP sync tests**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "feat(gene): OpenClawGeneInstallAdapter 实现 sync_mcp_servers 写入 openclaw.json"
```

---

## Task 3: Wire `sync_mcp_servers()` into gene install and uninstall

**Files:**
- Modify: `nodeskclaw-backend/app/services/gene_service.py:1247-1320` (install path) and `:2210-2245` (uninstall path)
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Write the failing test**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
from unittest.mock import patch, call


@pytest.mark.asyncio
async def test_apply_manifest_actions_calls_sync_for_mcp_genes():
    """_apply_manifest_actions should call sync_mcp_servers when manifest has mcp_servers."""
    from app.services.gene_service import _apply_manifest_actions

    fs = AsyncMock()
    adapter = AsyncMock()

    manifest = {
        "skill": {"name": "test-skill", "content": "test"},
        "mcp_servers": [{"name": "test-mcp", "transport": "stdio", "command": "node"}],
    }

    await _apply_manifest_actions(fs, manifest, adapter)

    adapter.apply_config.assert_not_called()
    adapter.allow_tools.assert_not_called()
    # scripts not in manifest, so deploy_scripts not called via _deploy_gene_scripts
    # But the key assertion: the manifest had mcp_servers, so the flag should be set
    # We verify this indirectly -- the actual sync call happens in _direct_install after _inject_mcp_servers
```

This test verifies the existing behavior of `_apply_manifest_actions`. The actual sync wiring happens in `_direct_install`. Let's write the integration-level test instead:

```python
@pytest.mark.asyncio
async def test_build_mcp_config_from_records():
    """Verify the config dict structure produced by sync_mcp_servers for a full manifest."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()
    fs.read_text = AsyncMock(return_value=json.dumps({
        "skills": {"load": {"extraDirs": ["/root/.openclaw/skills"]}},
        "tools": {"allow": ["nodeskclaw_blackboard"]},
    }))
    fs.write_text = AsyncMock()

    mcp_records = [
        MagicMock(
            name="social-media-browser",
            transport="stdio",
            command="node",
            url=None,
            args=["/root/.deskclaw/tools/social-media-browser/server.js"],
            env={"COOKIES_PATH": "/root/.deskclaw/cookies/"},
            is_active=True,
        ),
        MagicMock(
            name="media-generator",
            transport="stdio",
            command="python",
            url=None,
            args=["/root/.deskclaw/tools/media-generator/server.py"],
            env={"OPENAI_API_KEY": "sk-test"},
            is_active=True,
        ),
    ]

    await adapter.sync_mcp_servers(fs, mcp_records)

    config = json.loads(fs.write_text.call_args[0][1])
    # Existing config preserved
    assert config["skills"]["load"]["extraDirs"] == ["/root/.openclaw/skills"]
    assert config["tools"]["allow"] == ["nodeskclaw_blackboard"]
    # MCP servers added
    assert len(config["mcpServers"]) == 2
    assert config["mcpServers"]["social-media-browser"]["command"] == "node"
    assert config["mcpServers"]["media-generator"]["command"] == "python"
```

- [ ] **Step 2: Run test to verify it passes (this uses existing implementation)**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py -v`
Expected: 4 tests PASS

- [ ] **Step 3: Add sync call to `_direct_install`**

In `nodeskclaw-backend/app/services/gene_service.py`, inside `_direct_install()`, after line 1279 (`await _apply_manifest_actions(fs, manifest, adapter)`), add MCP sync:

```python
                    await _apply_manifest_actions(fs, manifest, adapter)

                    # Sync MCP servers from DB to openclaw.json
                    if manifest.get("mcp_servers"):
                        from app.models.instance_mcp_server import InstanceMcpServer
                        mcp_q = await db.execute(
                            select(InstanceMcpServer).where(
                                InstanceMcpServer.instance_id == instance_id,
                                InstanceMcpServer.is_active.is_(True),
                                not_deleted(InstanceMcpServer),
                            )
                        )
                        await adapter.sync_mcp_servers(fs, list(mcp_q.scalars().all()))

                    await adapter.invalidate_cache(fs, skill_name, "installed")
```

- [ ] **Step 4: Add sync call to `_direct_uninstall`**

In `nodeskclaw-backend/app/services/gene_service.py`, inside `_direct_uninstall()`, after line 2226 (`await adapter.post_remove_cleanup(fs, skill_name)`), add:

```python
                        await adapter.remove_skill(fs, skill_name)
                        await adapter.post_remove_cleanup(fs, skill_name)

                        # Re-sync MCP servers (removes entries from uninstalled gene)
                        from app.models.instance_mcp_server import InstanceMcpServer
                        mcp_q = await db.execute(
                            select(InstanceMcpServer).where(
                                InstanceMcpServer.instance_id == instance_id,
                                InstanceMcpServer.is_active.is_(True),
                                not_deleted(InstanceMcpServer),
                            )
                        )
                        await adapter.sync_mcp_servers(fs, list(mcp_q.scalars().all()))
```

- [ ] **Step 5: Run full test suite**

Run: `cd nodeskclaw-backend && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add nodeskclaw-backend/app/services/gene_service.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "feat(gene): 基因安装/卸载时同步 MCP Server 配置到 openclaw.json"
```

---

## Task 4: Create `social-media-browser` MCP server -- bootstrap and entry point

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json`
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js`

- [ ] **Step 1: Create `package.json`**

Create `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json`:

```json
{
  "name": "social-media-browser",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "playwright": "^1.50.0"
  }
}
```

- [ ] **Step 2: Create `server.js` with bootstrap and MCP skeleton**

Create `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js`:

```javascript
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Self-bootstrap: install deps on first run
if (!fs.existsSync(path.join(__dirname, "node_modules"))) {
  console.error("[social-media-browser] First run -- installing dependencies...");
  execSync("npm install && npx playwright install chromium", {
    cwd: __dirname,
    stdio: "inherit",
    timeout: 300_000,
  });
  console.error("[social-media-browser] Dependencies installed.");
}

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { createBrowserPool } from "./browser-pool.js";
import { xTools, handleXTool } from "./tools/x.js";
import { redditTools, handleRedditTool } from "./tools/reddit.js";
import { substackTools, handleSubstackTool } from "./tools/substack.js";

const COOKIES_PATH = process.env.COOKIES_PATH || "/root/.deskclaw/cookies/";
const pool = createBrowserPool(COOKIES_PATH);

const server = new Server(
  { name: "social-media-browser", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

const ALL_TOOLS = [...xTools, ...redditTools, ...substackTools];

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: ALL_TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    const xToolNames = xTools.map((t) => t.name);
    const redditToolNames = redditTools.map((t) => t.name);
    const substackToolNames = substackTools.map((t) => t.name);

    let result;
    if (xToolNames.includes(name)) {
      result = await handleXTool(pool, name, args);
    } else if (redditToolNames.includes(name)) {
      result = await handleRedditTool(pool, name, args);
    } else if (substackToolNames.includes(name)) {
      result = await handleSubstackTool(pool, name, args);
    } else {
      return {
        content: [{ type: "text", text: JSON.stringify({ error: "unknown_tool", tool: name }) }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: JSON.stringify(result) }],
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: JSON.stringify({ error: err.message }) }],
      isError: true,
    };
  }
});

// Graceful shutdown
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

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/
git commit -m "feat(gene): social-media-browser MCP 服务器入口和依赖清单"
```

---

## Task 5: Create browser context pool

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js`

- [ ] **Step 1: Create `browser-pool.js`**

```javascript
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

/**
 * Manages one persistent browser context per platform.
 * Cookies are loaded from JSON files at context creation time.
 * If cookies expire (detected by login redirect), the context is invalidated
 * and the next call will create a fresh one with refreshed cookie files.
 */
export function createBrowserPool(cookiesPath) {
  let browser = null;
  const contexts = new Map(); // platform -> BrowserContext

  async function ensureBrowser() {
    if (!browser || !browser.isConnected()) {
      browser = await chromium.launch({ headless: true });
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
    return JSON.parse(raw);
  }

  async function getContext(platform) {
    if (contexts.has(platform)) {
      return contexts.get(platform);
    }

    const b = await ensureBrowser();
    const cookies = loadCookies(platform);
    if (!cookies) {
      throw new Error(
        JSON.stringify({
          error: "cookies_not_found",
          platform,
          message: `No cookie file found at ${cookieFilePath(platform)}. Please export cookies and place the file.`,
        }),
      );
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

  /**
   * Check if the page was redirected to a login page.
   * Returns an auth_expired error object if so, or null if authenticated.
   */
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
git commit -m "feat(gene): social-media-browser 浏览器上下文池（持久化 + cookie 注入）"
```

---

## Task 6: Create X.com tool implementations

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js`

- [ ] **Step 1: Create `tools/x.js`**

```javascript
const PLATFORM = "x";
const LOGIN_PATTERNS = ["/i/flow/login", "/login"];

export const xTools = [
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
        text: { type: "string", description: "Tweet text (max 280 characters)." },
        media_urls: {
          type: "array",
          items: { type: "string" },
          description: "Optional media URLs to attach.",
        },
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
        text: { type: "string", description: "Reply text." },
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
];

export async function handleXTool(pool, toolName, args) {
  const context = await pool.getContext(PLATFORM);
  const page = await context.newPage();

  try {
    switch (toolName) {
      case "x_scan_timeline":
        return await scanTimeline(pool, page, args);
      case "x_scan_profile":
        return await scanProfile(pool, page, args);
      case "x_post_tweet":
        return await postTweet(pool, page, args);
      case "x_reply":
        return await replyToTweet(pool, page, args);
      case "x_like":
        return await likeTweet(pool, page, args);
      default:
        return { error: "unknown_tool", tool: toolName };
    }
  } finally {
    await page.close();
  }
}

async function scanTimeline(pool, page, { query, count = 20 }) {
  const url = query ? `https://x.com/search?q=${encodeURIComponent(query)}&f=live` : "https://x.com/home";
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  await autoScroll(page, count);

  const posts = await page.evaluate((maxCount) => {
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    for (const article of articles) {
      if (results.length >= maxCount) break;
      const textEl = article.querySelector('[data-testid="tweetText"]');
      const userEl = article.querySelector('[data-testid="User-Name"]');
      const timeEl = article.querySelector("time");
      const link = article.querySelector('a[href*="/status/"]');

      results.push({
        text: textEl?.innerText || "",
        author: userEl?.innerText?.split("\n")?.[0] || "",
        handle: userEl?.innerText?.split("\n")?.[1] || "",
        time: timeEl?.getAttribute("datetime") || "",
        url: link ? `https://x.com${link.getAttribute("href")}` : "",
      });
    }
    return results;
  }, count);

  return { posts, count: posts.length };
}

async function scanProfile(pool, page, { username, count = 10 }) {
  await page.goto(`https://x.com/${username}`, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  await autoScroll(page, count);

  const posts = await page.evaluate((maxCount) => {
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    for (const article of articles) {
      if (results.length >= maxCount) break;
      const textEl = article.querySelector('[data-testid="tweetText"]');
      const timeEl = article.querySelector("time");
      const link = article.querySelector('a[href*="/status/"]');
      results.push({
        text: textEl?.innerText || "",
        time: timeEl?.getAttribute("datetime") || "",
        url: link ? `https://x.com${link.getAttribute("href")}` : "",
      });
    }
    return results;
  }, count);

  return { posts, count: posts.length };
}

async function postTweet(pool, page, { text }) {
  await page.goto("https://x.com/compose/post", { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  const editor = page.locator('[data-testid="tweetTextarea_0"]');
  await editor.click();
  await editor.fill(text);
  await page.locator('[data-testid="tweetButtonInline"]').click();
  await page.waitForTimeout(2000);

  return { success: true, text };
}

async function replyToTweet(pool, page, { tweet_url, text }) {
  await page.goto(tweet_url, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  const replyBox = page.locator('[data-testid="tweetTextarea_0"]');
  await replyBox.click();
  await replyBox.fill(text);
  await page.locator('[data-testid="tweetButtonInline"]').click();
  await page.waitForTimeout(2000);

  return { success: true, tweet_url, text };
}

async function likeTweet(pool, page, { tweet_url }) {
  await page.goto(tweet_url, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  const likeButton = page.locator('[data-testid="like"]');
  if (await likeButton.count() > 0) {
    await likeButton.click();
    return { success: true, tweet_url, action: "liked" };
  }

  return { success: true, tweet_url, action: "already_liked" };
}

async function autoScroll(page, targetCount) {
  let previousHeight = 0;
  let attempts = 0;
  while (attempts < 10) {
    const articles = await page.locator('article[data-testid="tweet"]').count();
    if (articles >= targetCount) break;
    await page.evaluate(() => window.scrollBy(0, window.innerHeight));
    await page.waitForTimeout(1500);
    const currentHeight = await page.evaluate(() => document.body.scrollHeight);
    if (currentHeight === previousHeight) break;
    previousHeight = currentHeight;
    attempts++;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js
git commit -m "feat(gene): social-media-browser X.com 工具实现（扫描/发帖/回复/点赞）"
```

---

## Task 7: Create Reddit tool implementations

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js`

- [ ] **Step 1: Create `tools/reddit.js`**

```javascript
const PLATFORM = "reddit";
const LOGIN_PATTERNS = ["/login", "/account/login"];

export const redditTools = [
  {
    name: "reddit_scan_subreddit",
    description: "Get posts from a subreddit on Reddit.",
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
    description: "Create a new post in a subreddit.",
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
        post_url: { type: "string", description: "Full URL of the post or comment." },
        text: { type: "string", description: "Reply text (markdown)." },
      },
      required: ["post_url", "text"],
    },
  },
];

export async function handleRedditTool(pool, toolName, args) {
  const context = await pool.getContext(PLATFORM);
  const page = await context.newPage();

  try {
    switch (toolName) {
      case "reddit_scan_subreddit":
        return await scanSubreddit(pool, page, args);
      case "reddit_post":
        return await createPost(pool, page, args);
      case "reddit_reply":
        return await replyToPost(pool, page, args);
      default:
        return { error: "unknown_tool", tool: toolName };
    }
  } finally {
    await page.close();
  }
}

async function scanSubreddit(pool, page, { subreddit, sort = "hot", count = 20 }) {
  // Use old.reddit.com for simpler DOM structure
  await page.goto(`https://old.reddit.com/r/${subreddit}/${sort}/`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  const posts = await page.evaluate((maxCount) => {
    const things = document.querySelectorAll("#siteTable .thing.link");
    const results = [];
    for (const thing of things) {
      if (results.length >= maxCount) break;
      const titleEl = thing.querySelector("a.title");
      const scoreEl = thing.querySelector(".score.unvoted");
      const commentsEl = thing.querySelector(".comments");
      const timeEl = thing.querySelector("time");

      results.push({
        title: titleEl?.textContent || "",
        url: titleEl?.href || "",
        score: scoreEl?.textContent || "0",
        comments: commentsEl?.textContent || "0",
        time: timeEl?.getAttribute("datetime") || "",
      });
    }
    return results;
  }, count);

  return { subreddit, sort, posts, count: posts.length };
}

async function createPost(pool, page, { subreddit, title, body }) {
  await page.goto(`https://old.reddit.com/r/${subreddit}/submit?selftext=true`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  await page.fill('textarea[name="title"]', title);

  const textTab = page.locator('li.tabmenu-li a:text("text")');
  if (await textTab.count() > 0) {
    await textTab.click();
  }
  await page.fill('textarea[name="text"]', body);
  await page.click('button[name="submit"]');
  await page.waitForTimeout(3000);

  return { success: true, subreddit, title };
}

async function replyToPost(pool, page, { post_url, text }) {
  // Convert new reddit URLs to old reddit for consistency
  const url = post_url.replace("www.reddit.com", "old.reddit.com");
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  const commentBox = page.locator(".usertext-edit textarea").first();
  await commentBox.fill(text);
  await page.locator('.usertext-edit button[type="submit"]').first().click();
  await page.waitForTimeout(2000);

  return { success: true, post_url, text };
}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js
git commit -m "feat(gene): social-media-browser Reddit 工具实现（扫描/发帖/回复）"
```

---

## Task 8: Create Substack tool implementations

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js`

- [ ] **Step 1: Create `tools/substack.js`**

```javascript
const PLATFORM = "substack";
const LOGIN_PATTERNS = ["/sign-in", "/account/login"];

export const substackTools = [
  {
    name: "substack_publish",
    description: "Publish a draft article on Substack.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", description: "Article title." },
        subtitle: { type: "string", description: "Article subtitle (optional)." },
        body: { type: "string", description: "Article body (rich text / HTML)." },
      },
      required: ["title", "body"],
    },
  },
  {
    name: "substack_scan_feed",
    description: "Scan your Substack feed/inbox for recent posts.",
    inputSchema: {
      type: "object",
      properties: {
        count: { type: "number", description: "Number of posts (default 20).", default: 20 },
      },
    },
  },
];

export async function handleSubstackTool(pool, toolName, args) {
  const context = await pool.getContext(PLATFORM);
  const page = await context.newPage();

  try {
    switch (toolName) {
      case "substack_publish":
        return await publishArticle(pool, page, args);
      case "substack_scan_feed":
        return await scanFeed(pool, page, args);
      default:
        return { error: "unknown_tool", tool: toolName };
    }
  } finally {
    await page.close();
  }
}

async function publishArticle(pool, page, { title, subtitle, body }) {
  // Navigate to the new post editor
  await page.goto("https://substack.com/home", { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  // Click "New post" button from dashboard
  const newPostButton = page.locator('a[href*="/publish/post"]').first();
  if (await newPostButton.count() > 0) {
    await newPostButton.click();
  } else {
    // Fallback: navigate directly
    // User's substack URL is auto-detected from the dashboard
    await page.goto("https://substack.com/publish/post", { waitUntil: "networkidle", timeout: 30_000 });
  }
  await page.waitForTimeout(2000);

  // Fill title
  const titleInput = page.locator('[placeholder*="Title"], .post-title');
  await titleInput.click();
  await titleInput.fill(title);

  // Fill subtitle if provided
  if (subtitle) {
    const subtitleInput = page.locator('[placeholder*="subtitle"], .post-subtitle');
    if (await subtitleInput.count() > 0) {
      await subtitleInput.click();
      await subtitleInput.fill(subtitle);
    }
  }

  // Fill body -- click into the editor area and type
  const editor = page.locator('.ProseMirror, [contenteditable="true"]').first();
  await editor.click();
  await editor.fill(body);

  // Save as draft (not publish immediately -- safety measure)
  // The agent's SKILL.md instructs it to use blackboard for approval before publishing
  await page.waitForTimeout(2000);

  return {
    success: true,
    title,
    status: "draft_saved",
    message: "Article saved as draft. Review in Substack dashboard before publishing.",
  };
}

async function scanFeed(pool, page, { count = 20 }) {
  await page.goto("https://substack.com/inbox", { waitUntil: "networkidle", timeout: 30_000 });

  const authError = pool.checkAuthRedirect(page, PLATFORM, LOGIN_PATTERNS);
  if (authError) {
    await pool.invalidateContext(PLATFORM);
    return authError;
  }

  await page.waitForTimeout(2000);

  const posts = await page.evaluate((maxCount) => {
    const items = document.querySelectorAll('[class*="post-preview"], [class*="inbox-item"]');
    const results = [];
    for (const item of items) {
      if (results.length >= maxCount) break;
      const titleEl = item.querySelector("a");
      const authorEl = item.querySelector('[class*="author"], [class*="pub-name"]');
      const timeEl = item.querySelector("time");

      results.push({
        title: titleEl?.textContent?.trim() || "",
        url: titleEl?.href || "",
        author: authorEl?.textContent?.trim() || "",
        time: timeEl?.getAttribute("datetime") || "",
      });
    }
    return results;
  }, count);

  return { posts, count: posts.length };
}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js
git commit -m "feat(gene): social-media-browser Substack 工具实现（发布草稿/扫描 Feed）"
```

---

## Task 9: Create `social-media-browser` gene manifest and SKILL.md

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p nodeskclaw-backend/app/data/gene_manifests
mkdir -p nodeskclaw-backend/app/data/gene_skills
```

- [ ] **Step 2: Create gene manifest**

Create `nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json`:

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
    "social-media-browser/server.js",
    "social-media-browser/browser-pool.js",
    "social-media-browser/tools/x.js",
    "social-media-browser/tools/reddit.js",
    "social-media-browser/tools/substack.js"
  ]
}
```

- [ ] **Step 3: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/social-media-browser.md`:

```markdown
---
name: social-media-browser
description: Browser-based social media automation for X, Reddit, and Substack
---

# Social Media Browser

You have access to browser-based tools for interacting with X.com, Reddit, and Substack.

## Available Tools

### X.com
- `x_scan_timeline` -- Scan home timeline or search for posts by query
- `x_scan_profile` -- View a specific user's recent posts
- `x_post_tweet` -- Post a new tweet (max 280 characters)
- `x_reply` -- Reply to a specific tweet
- `x_like` -- Like a specific tweet

### Reddit
- `reddit_scan_subreddit` -- Browse posts in a subreddit (hot/new/top)
- `reddit_post` -- Create a new post (use markdown for body)
- `reddit_reply` -- Reply to a post or comment

### Substack
- `substack_publish` -- Create a draft article (saved as draft, not auto-published)
- `substack_scan_feed` -- Scan your inbox for recent posts

## Rate Limits

Follow these guidelines to avoid platform restrictions:
- X.com: No more than 5 tweets per hour, 3 likes per minute
- Reddit: No more than 10 posts per day, 1 post per subreddit per hour
- Substack: No more than 2 articles per day

## Error Handling

If a tool returns `{"error": "auth_expired", "platform": "..."}`, it means the session cookies
have expired. Report this to the user immediately:
> "My session cookies for [platform] have expired. Please export fresh cookies and update the cookie file."

Do NOT retry the same action after an auth_expired error. Wait for the user to refresh cookies.

If a tool returns `{"error": "cookies_not_found", "platform": "..."}`, cookies have not been
configured for that platform. Report this to the user.

## Content Guidelines

- Always review content before posting. Use the workspace blackboard to propose content for
  human review before publishing.
- Never post content that could be controversial, offensive, or off-brand.
- Adapt content format per platform:
  - X: Concise, punchy, use hashtags sparingly (1-3), thread for longer content
  - Reddit: Informative, match subreddit culture, use proper markdown formatting
  - Substack: Long-form, use sections and headers, include a clear thesis
```

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json \
        nodeskclaw-backend/app/data/gene_skills/social-media-browser.md
git commit -m "feat(gene): social-media-browser 基因清单和 SKILL.md"
```

---

## Task 10: Create `media-generator` MCP server

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/requirements.txt`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

Create `nodeskclaw-backend/app/data/gene_scripts/media-generator/requirements.txt`:

```
mcp>=1.0.0
httpx>=0.27.0
```

- [ ] **Step 2: Create `providers/__init__.py`**

Create `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py`:

```python
"""Media generation provider registry."""

from __future__ import annotations

import os

_IMAGE_PROVIDERS: dict[str, type] = {}
_VIDEO_PROVIDERS: dict[str, type] = {}


def register_image_provider(name: str):
    def decorator(cls):
        _IMAGE_PROVIDERS[name] = cls
        return cls
    return decorator


def register_video_provider(name: str):
    def decorator(cls):
        _VIDEO_PROVIDERS[name] = cls
        return cls
    return decorator


def get_image_provider():
    name = os.environ.get("IMAGE_PROVIDER", "openai")
    cls = _IMAGE_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown image provider: {name}. Available: {list(_IMAGE_PROVIDERS)}")
    return cls()


def get_video_provider():
    name = os.environ.get("VIDEO_PROVIDER", "runway")
    cls = _VIDEO_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown video provider: {name}. Available: {list(_VIDEO_PROVIDERS)}")
    return cls()
```

- [ ] **Step 3: Create `server.py`**

Create `nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py`:

```python
"""Media Generator MCP Server -- image and video generation via external APIs."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Self-bootstrap: install deps on first run
try:
    import mcp  # noqa: F401
    import httpx  # noqa: F401
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r",
         str(Path(__file__).parent / "requirements.txt")],
    )

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Import providers after bootstrap
from providers import get_image_provider, get_video_provider
from providers.openai_images import OpenAIImageProvider  # noqa: F401 -- triggers registration
from providers.runway_video import RunwayVideoProvider  # noqa: F401 -- triggers registration

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/root/.deskclaw/media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

server = Server("media-generator")

TOOLS = [
    Tool(
        name="generate_image",
        description="Generate an image from a text prompt using DALL-E 3.",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image generation prompt."},
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1792x1024", "1024x1792"],
                    "default": "1024x1024",
                    "description": "Image size.",
                },
                "style": {
                    "type": "string",
                    "enum": ["natural", "vivid"],
                    "default": "vivid",
                    "description": "Image style.",
                },
            },
            "required": ["prompt"],
        },
    ),
    Tool(
        name="edit_image",
        description="Edit an existing image with a text instruction.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to edit."},
                "prompt": {"type": "string", "description": "Edit instruction."},
            },
            "required": ["image_url", "prompt"],
        },
    ),
    Tool(
        name="generate_video",
        description="Generate a short video from a text prompt.",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video generation prompt."},
                "duration": {
                    "type": "string",
                    "enum": ["5s", "10s"],
                    "default": "5s",
                    "description": "Video duration.",
                },
                "reference_image_url": {
                    "type": "string",
                    "description": "Optional reference image URL.",
                },
            },
            "required": ["prompt"],
        },
    ),
    Tool(
        name="describe_image",
        description="Analyze an image and return a text description. Useful for self-critique before posting.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to describe."},
            },
            "required": ["image_url"],
        },
    ),
]


def _save_path(ext: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    h = hashlib.sha256(ts.encode()).hexdigest()[:8]
    return MEDIA_DIR / f"{ts}-{h}.{ext}"


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    import json

    try:
        if name == "generate_image":
            provider = get_image_provider()
            result = await provider.generate(
                prompt=arguments["prompt"],
                size=arguments.get("size", "1024x1024"),
                style=arguments.get("style", "vivid"),
            )
            save_path = _save_path("png")
            if result.get("image_bytes"):
                save_path.write_bytes(result["image_bytes"])
                result["local_path"] = str(save_path)
                del result["image_bytes"]
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "edit_image":
            provider = get_image_provider()
            result = await provider.edit(
                image_url=arguments["image_url"],
                prompt=arguments["prompt"],
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "generate_video":
            provider = get_video_provider()
            result = await provider.generate(
                prompt=arguments["prompt"],
                duration=arguments.get("duration", "5s"),
                reference_image_url=arguments.get("reference_image_url"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "describe_image":
            provider = get_image_provider()
            result = await provider.describe(image_url=arguments["image_url"])
            return [TextContent(type="text", text=json.dumps(result))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": "unknown_tool", "tool": name}))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/
git commit -m "feat(gene): media-generator MCP 服务器入口、依赖和 provider 注册表"
```

---

## Task 11: Create OpenAI image provider

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai_images.py`

- [ ] **Step 1: Create `openai_images.py`**

```python
"""OpenAI DALL-E 3 image generation + GPT-4o Vision description."""

from __future__ import annotations

import base64
import os

import httpx

from providers import register_image_provider

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


@register_image_provider("openai")
class OpenAIImageProvider:

    async def generate(self, prompt: str, size: str = "1024x1024", style: str = "vivid") -> dict:
        if not OPENAI_API_KEY:
            return {"error": "OPENAI_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "style": style,
                    "response_format": "b64_json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        image_data = data["data"][0]
        image_bytes = base64.b64decode(image_data["b64_json"])
        revised_prompt = image_data.get("revised_prompt", prompt)

        return {
            "url": image_data.get("url", ""),
            "revised_prompt": revised_prompt,
            "image_bytes": image_bytes,
            "size": size,
        }

    async def edit(self, image_url: str, prompt: str) -> dict:
        if not OPENAI_API_KEY:
            return {"error": "OPENAI_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=120) as client:
            # Download the source image
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()

            resp = await client.post(
                f"{OPENAI_BASE_URL}/images/edits",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"image": ("image.png", img_resp.content, "image/png")},
                data={"prompt": prompt, "n": 1, "size": "1024x1024"},
            )
            resp.raise_for_status()
            data = resp.json()

        return {"url": data["data"][0].get("url", ""), "prompt": prompt}

    async def describe(self, image_url: str) -> dict:
        if not OPENAI_API_KEY:
            return {"error": "OPENAI_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe this image in detail. Focus on composition, mood, colors, and subject matter."},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return {"description": data["choices"][0]["message"]["content"]}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai_images.py
git commit -m "feat(gene): media-generator OpenAI DALL-E 3 图片生成 + GPT-4o Vision"
```

---

## Task 12: Create Runway video provider

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway_video.py`

- [ ] **Step 1: Create `runway_video.py`**

```python
"""Runway Gen-3 Alpha video generation provider."""

from __future__ import annotations

import asyncio
import os

import httpx

from providers import register_video_provider

RUNWAY_API_KEY = os.environ.get("RUNWAY_API_KEY", "")
RUNWAY_BASE_URL = os.environ.get("RUNWAY_BASE_URL", "https://api.dev.runwayml.com/v1")


@register_video_provider("runway")
class RunwayVideoProvider:

    async def generate(
        self,
        prompt: str,
        duration: str = "5s",
        reference_image_url: str | None = None,
    ) -> dict:
        if not RUNWAY_API_KEY:
            return {"error": "RUNWAY_API_KEY not configured"}

        duration_seconds = 5 if duration == "5s" else 10

        payload: dict = {
            "promptText": prompt,
            "model": "gen3a_turbo",
            "duration": duration_seconds,
        }
        if reference_image_url:
            payload["promptImage"] = reference_image_url

        async with httpx.AsyncClient(timeout=300) as client:
            # Create task
            resp = await client.post(
                f"{RUNWAY_BASE_URL}/image_to_video",
                headers={
                    "Authorization": f"Bearer {RUNWAY_API_KEY}",
                    "X-Runway-Version": "2024-11-06",
                },
                json=payload,
            )
            resp.raise_for_status()
            task = resp.json()
            task_id = task["id"]

            # Poll for completion
            for _ in range(60):
                poll_resp = await client.get(
                    f"{RUNWAY_BASE_URL}/tasks/{task_id}",
                    headers={
                        "Authorization": f"Bearer {RUNWAY_API_KEY}",
                        "X-Runway-Version": "2024-11-06",
                    },
                )
                poll_resp.raise_for_status()
                status = poll_resp.json()

                if status["status"] == "SUCCEEDED":
                    return {
                        "video_url": status["output"][0],
                        "duration": duration,
                        "prompt": prompt,
                    }

                if status["status"] == "FAILED":
                    return {
                        "error": "video_generation_failed",
                        "reason": status.get("failure", "Unknown error"),
                    }

                await asyncio.sleep(5)

            return {"error": "video_generation_timeout", "task_id": task_id}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway_video.py
git commit -m "feat(gene): media-generator Runway Gen-3 视频生成 provider"
```

---

## Task 13: Create `media-generator` gene manifest and SKILL.md

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/media-generator.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/media-generator.md`

- [ ] **Step 1: Create gene manifest**

Create `nodeskclaw-backend/app/data/gene_manifests/media-generator.json`:

```json
{
  "skill": {
    "name": "media-generator",
    "description": "Image and video generation via external APIs (DALL-E 3, Runway)"
  },
  "tool_allow": [
    "generate_image",
    "edit_image",
    "generate_video",
    "describe_image"
  ],
  "mcp_servers": [
    {
      "name": "media-generator",
      "transport": "stdio",
      "command": "python",
      "args": ["/root/.deskclaw/tools/media-generator/server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "RUNWAY_API_KEY": "${RUNWAY_API_KEY}",
        "IMAGE_PROVIDER": "openai",
        "VIDEO_PROVIDER": "runway"
      }
    }
  ],
  "scripts": [
    "media-generator/requirements.txt",
    "media-generator/server.py",
    "media-generator/providers/__init__.py",
    "media-generator/providers/openai_images.py",
    "media-generator/providers/runway_video.py"
  ]
}
```

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/media-generator.md`:

```markdown
---
name: media-generator
description: Image and video generation via external APIs (DALL-E 3, Runway)
---

# Media Generator

You have access to tools for generating images and videos using external AI services.

## Available Tools

- `generate_image` -- Generate an image from a text prompt using DALL-E 3
  - Sizes: 1024x1024 (square, social posts), 1792x1024 (landscape, headers), 1024x1792 (portrait, stories)
  - Styles: "vivid" (dramatic, hyper-real) or "natural" (more realistic)
- `edit_image` -- Edit an existing image with a text instruction
- `generate_video` -- Generate a short video (5s or 10s) from a text prompt
- `describe_image` -- Get a detailed description of an image (useful for self-critique)

## Platform-Specific Sizing

- X header image: 1792x1024
- X/Reddit post image: 1024x1024
- Instagram story: 1024x1792
- Substack article hero: 1792x1024

## Cost Awareness

These tools call paid APIs. Be mindful of costs:
- Image generation: ~$0.04-0.08 per image
- Image edit: ~$0.04 per edit
- Video generation: ~$0.50 per 5s clip, ~$1.00 per 10s clip
- Image description: ~$0.01 per call

Always confirm with the user before generating video. For images, batch requests when
possible (generate multiple concepts in one session rather than iterating one at a time).

## Quality Workflow

1. Generate image with a detailed prompt
2. Use `describe_image` to evaluate the result
3. If not satisfactory, refine the prompt and regenerate
4. Post the final result to the workspace blackboard for human review before publishing

## Error Handling

If a tool returns `{"error": "OPENAI_API_KEY not configured"}` or similar, report to the user:
> "The API key for [service] is not configured. Please set the environment variable."
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/media-generator.json \
        nodeskclaw-backend/app/data/gene_skills/media-generator.md
git commit -m "feat(gene): media-generator 基因清单和 SKILL.md"
```

---

## Task 14: Create behavioral skill templates

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md`
- Create: `nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md`
- Create: `nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md`

- [ ] **Step 1: Create trend-scout-playbook manifest**

Create `nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json`:

```json
{
  "skill": {
    "name": "trend-scout-playbook",
    "description": "Behavioral playbook for the Trend Scout agent -- scanning and reporting social media trends"
  }
}
```

- [ ] **Step 2: Create trend-scout-playbook SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md`:

```markdown
---
name: trend-scout-playbook
description: Behavioral playbook for the Trend Scout agent
---

# Trend Scout Playbook

You are a trend scout. Your role is to scan social media platforms for emerging trends,
viral content, and industry signals relevant to the team's marketing goals.

## Workflow

1. **Scan** -- Use `x_scan_timeline` and `reddit_scan_subreddit` to browse relevant feeds
2. **Filter** -- Identify posts with high engagement or novel angles
3. **Analyze** -- Assess relevance, sentiment, and potential for the brand
4. **Report** -- Post a structured summary to the workspace blackboard

## Reporting Format

When posting findings to the blackboard, use this structure:

**Trend Report -- [Date]**
- Platform: X / Reddit / Substack
- Topic: [brief description]
- Key posts: [2-3 representative posts with links]
- Engagement: [metrics summary]
- Relevance: [why this matters for our brand]
- Recommended action: [ignore / monitor / act on]

## Scanning Strategy

- Focus on your assigned topics and hashtags
- Check trending topics daily
- Monitor competitor accounts weekly
- Scan relevant subreddits for emerging discussions
- Prioritize content with unusual engagement velocity (rapid growth)

## What NOT to Do

- Do not engage with content (no likes, replies, or retweets) -- your role is observation only
- Do not scan more than 100 posts per session to stay within rate limits
- Do not report on content older than 7 days unless it's resurging
```

- [ ] **Step 3: Create industry-researcher-playbook manifest and SKILL.md**

Create `nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json`:

```json
{
  "skill": {
    "name": "industry-researcher-playbook",
    "description": "Behavioral playbook for the Industry Researcher agent -- deep analysis from scout findings"
  }
}
```

Create `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md`:

```markdown
---
name: industry-researcher-playbook
description: Behavioral playbook for the Industry Researcher agent
---

# Industry Researcher Playbook

You are an industry researcher. Your role is to take trend data from the Trend Scout
and produce deep analysis that the Copywriter can use for content creation.

## Workflow

1. **Consume** -- Read the latest trend reports from the workspace context
2. **Research** -- Analyze trends using frameworks below
3. **Synthesize** -- Produce structured research reports
4. **Share** -- Post findings to the workspace blackboard

## Analysis Frameworks

### Trend Assessment
- What is driving this trend? (technology, culture, regulation, event)
- How mature is it? (emerging / growing / peak / declining)
- Who are the key players and voices?
- What is the addressable audience?

### Competitive Landscape
- Which competitors are already active in this space?
- What angles are they taking?
- Where are the gaps we can fill?

### Content Opportunity
- What questions are people asking about this topic?
- What misconceptions exist that we can correct?
- What unique perspective can we offer?

## Output Format

**Research Brief -- [Topic]**
- Trend summary: [2-3 sentences]
- Maturity: [emerging / growing / peak / declining]
- Key data points: [bullets]
- Competitive positions: [who is saying what]
- Content angles: [3-5 recommended angles for the Copywriter]
- Sources: [links to original posts/data]

## What NOT to Do

- Do not generate content -- that is the Copywriter's role
- Do not scan social media directly -- rely on the Trend Scout's reports
- Do not produce analysis without citing specific data points or sources
```

- [ ] **Step 4: Create copywriter-playbook manifest and SKILL.md**

Create `nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json`:

```json
{
  "skill": {
    "name": "copywriter-playbook",
    "description": "Behavioral playbook for the Copywriter agent -- content creation and publishing"
  }
}
```

Create `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md`:

```markdown
---
name: copywriter-playbook
description: Behavioral playbook for the Copywriter agent
---

# Copywriter Playbook

You are a marketing copywriter. Your role is to produce and publish content across
platforms based on research from the Industry Researcher.

## Workflow

1. **Read** -- Consume the latest research briefs from the workspace context
2. **Plan** -- Choose content angles and target platforms
3. **Create** -- Write content adapted to each platform
4. **Visual** -- Generate supporting images or video using media tools
5. **Review** -- Post drafts to the workspace blackboard for human approval
6. **Publish** -- After approval, publish via social media tools

## Platform Adaptation

### X.com
- Max 280 characters per tweet
- Use threads for longer content (break into 3-5 tweets)
- Include 1-3 relevant hashtags (not more)
- Attach images when possible (1024x1024 for posts)
- Tone: direct, punchy, conversational

### Reddit
- Match the subreddit's culture and rules
- Use markdown formatting
- Lead with value, not promotion
- Be authentic -- Reddit communities detect marketing quickly
- Tone: informative, helpful, genuine

### Substack
- Long-form articles with clear thesis
- Use sections and headers for scannability
- Include a compelling hero image (1792x1024)
- Tone: thoughtful, authoritative, personal

## Content Quality Checklist

Before publishing any content:
- [ ] Based on actual research data (not fabricated)
- [ ] Adapted to platform format and culture
- [ ] Proofread for grammar and clarity
- [ ] Includes relevant visual content
- [ ] Posted to blackboard for human review
- [ ] Human has approved publication

## What NOT to Do

- Never publish without posting to the blackboard for review first
- Never fabricate statistics or quotes
- Never copy content verbatim from sources
- Never post the same content to multiple platforms without adaptation
- Never generate video without confirming cost with the user first
```

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/ \
        nodeskclaw-backend/app/data/gene_skills/
git commit -m "feat(gene): 三个行为技能模板（潮流侦察员/行业研究员/文案撰写员）"
```

---

## Task 15: Run full test suite and verify

- [ ] **Step 1: Run backend tests**

Run: `cd nodeskclaw-backend && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify gene_scripts directory structure**

Run: `find nodeskclaw-backend/app/data/gene_scripts -type f | sort`

Expected output:
```
nodeskclaw-backend/app/data/gene_scripts/_api_client.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_blackboard.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_gene_discovery.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_performance.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_proposals.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_shared_files.py
nodeskclaw-backend/app/data/gene_scripts/deskclaw_topology.py
nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py
nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai_images.py
nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway_video.py
nodeskclaw-backend/app/data/gene_scripts/media-generator/requirements.txt
nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/browser-pool.js
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/package.json
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/server.js
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/reddit.js
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/substack.js
nodeskclaw-backend/app/data/gene_scripts/social-media-browser/tools/x.js
```

- [ ] **Step 3: Verify gene manifests and skills**

Run: `find nodeskclaw-backend/app/data/gene_manifests nodeskclaw-backend/app/data/gene_skills -type f | sort`

Expected output:
```
nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json
nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json
nodeskclaw-backend/app/data/gene_manifests/media-generator.json
nodeskclaw-backend/app/data/gene_manifests/social-media-browser.json
nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json
nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md
nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md
nodeskclaw-backend/app/data/gene_skills/media-generator.md
nodeskclaw-backend/app/data/gene_skills/social-media-browser.md
nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md
```

- [ ] **Step 4: Verify ruff passes**

Run: `cd nodeskclaw-backend && uv run ruff check app/services/runtime/openclaw_gene_install_adapter.py app/services/runtime/gene_install_adapter.py app/services/gene_service.py`
Expected: No errors

- [ ] **Step 5: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "chore: 最终验证和修复"
```
