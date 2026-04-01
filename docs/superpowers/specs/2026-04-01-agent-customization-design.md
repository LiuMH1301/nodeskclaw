# Agent Customization: Custom Skills, Social Media Automation, and Content Generation

Date: 2026-04-01

## Overview

Extend NoDeskClaw AI employees with three new capabilities using the existing gene/MCP architecture:

1. **Custom skills** -- behavioral instructions bundled with MCP tools via gene manifests
2. **Social media automation** -- Playwright-based browser automation for X, Reddit, Substack
3. **Rich content generation** -- image and video generation via external APIs (DALL-E, Runway)

All three capabilities share a single integration pattern: MCP servers packaged as genes. Each gene bundles a SKILL.md (behavioral instructions), an MCP server definition, tool allow-lists, and install scripts. Genes are org_private by default and never published to GeneHub.

## Target Agents

| Agent | Genes | Rationale |
|---|---|---|
| 潮流侦察员 (Trend Scout) | `social-media-browser` + `trend-scout-playbook` | Scans X/Reddit/Substack for trends. Needs browser access but not content generation. |
| 行业研究员 (Industry Researcher) | `industry-researcher-playbook` | Analyzes findings from workspace context (last 30 messages). No browser or media needed. Stays lean (~500MB less RAM). |
| 文案撰写员 (Copywriter) | `social-media-browser` + `media-generator` + `copywriter-playbook` | Produces and publishes marketing content with images/video across platforms. |

## Phase 1: Fix MCP Server Sync Gap

### Problem

`gene_service._inject_mcp_servers()` creates `InstanceMcpServer` rows in the database, but nothing writes them into the running pod's `openclaw.json` `mcpServers` section. Genes with MCP servers install the skill file and scripts, but the MCP tools never become available to the agent at runtime.

### Solution

Add a `sync_mcp_servers()` method to `OpenClawGeneInstallAdapter` in `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py`.

**Behavior:**
1. Query all active `InstanceMcpServer` records for the instance
2. Build the `mcpServers` config dict from those records
3. Merge into `openclaw.json` via the existing `apply_config()` method
4. Call this at the end of `deploy_skill()` when the gene manifest contains `mcp_servers`

**Target config output:**

```json
{
  "mcpServers": {
    "social-media-browser": {
      "transport": "stdio",
      "command": "node",
      "args": ["/root/.deskclaw/tools/social-media-browser/server.js"],
      "env": { "COOKIES_PATH": "/root/.deskclaw/cookies/" }
    }
  }
}
```

**Scope:** ~50 lines in `openclaw_gene_install_adapter.py`. No new files. No API changes.

**Also needed on gene uninstall:** When a gene with `mcp_servers` is removed, `sync_mcp_servers()` should be called again to remove stale entries from `openclaw.json`.

## Phase 2: Social Media Browser MCP Server

### Component

`social-media-browser` -- a Node.js MCP server using `@modelcontextprotocol/sdk` + Playwright.

### Tools

| Tool | Platform | Parameters | Description |
|---|---|---|---|
| `x_scan_timeline` | X | `query` (optional), `count` (default 20) | Scroll home or search timeline, return posts with text + engagement metrics |
| `x_scan_profile` | X | `username`, `count` (default 10) | Scan a user's recent posts |
| `x_post_tweet` | X | `text`, `media_urls` (optional) | Post a tweet |
| `x_reply` | X | `tweet_url`, `text` | Reply to a specific tweet |
| `x_like` | X | `tweet_url` | Like a tweet |
| `reddit_scan_subreddit` | Reddit | `subreddit`, `sort` (hot/new/top), `count` (default 20) | Get posts from a subreddit |
| `reddit_post` | Reddit | `subreddit`, `title`, `body` | Create a post |
| `reddit_reply` | Reddit | `post_url`, `text` | Reply to a post or comment |
| `substack_publish` | Substack | `title`, `body`, `subtitle` (optional) | Publish a draft article |
| `substack_scan_feed` | Substack | `count` (default 20) | Scan feed/notes |

### Architecture

```
OpenClaw Agent Process
  |
  |-- stdio --> social-media-browser MCP server (Node.js)
                  |
                  |-- Playwright (headless Chromium)
                  |     |-- X.com context (cookies from /root/.deskclaw/cookies/x.json)
                  |     |-- Reddit context (cookies from /root/.deskclaw/cookies/reddit.json)
                  |     |-- Substack context (cookies from /root/.deskclaw/cookies/substack.json)
                  |
                  |-- One persistent browser context per platform
```

### Design Decisions

**Browser context pool:** One persistent browser context per platform, created on first tool call for that platform. Contexts stay alive between tool calls. Avoids ~3-5s Chromium startup per action.

**Cookie injection:** At context creation, the MCP server reads cookie JSON files from `/root/.deskclaw/cookies/` and injects them via `context.addCookies()`. Cookie files are standard browser export format (array of `{name, value, domain, path, ...}` objects, as exported by browser extensions like "Cookie Editor").

**Cookie refresh without restart:** Updated cookie files on the PVC are picked up on the next context creation. No pod restart needed. Old contexts are closed and re-created with fresh cookies.

**Auth failure handling:** If a platform redirects to a login page, the tool returns a structured error:
```json
{ "error": "auth_expired", "platform": "x", "message": "Session cookies expired. Please export fresh cookies." }
```
The agent's SKILL.md instructs it to report this to the user via workspace chat rather than attempting auto-login.

**Resource cost:** ~300-500MB RAM for headless Chromium. Pods have 4Gi limit with ~2Gi used by OpenClaw. Fits comfortably.

### Playwright Installation

Playwright and Chromium are not baked into the OpenClaw pod image. Instead, the gene's install script handles first-time setup on the PVC:

```bash
# Runs once during gene installation via gene_service._apply_manifest_actions()
cd /root/.deskclaw/tools/social-media-browser
npm install
npx playwright install chromium
```

This downloads Chromium (~200MB) to the PVC at `/root/.deskclaw/tools/social-media-browser/node_modules/`. It survives pod restarts because the PVC is persistent. First-time install takes ~2 minutes. Subsequent pod restarts skip this step.

### Gene Manifest

```json
{
  "skill": {
    "name": "social-media-browser",
    "content": "<<SKILL.md content>>"
  },
  "tool_allow": [
    "x_scan_timeline", "x_scan_profile", "x_post_tweet",
    "x_reply", "x_like", "reddit_scan_subreddit",
    "reddit_post", "reddit_reply",
    "substack_publish", "substack_scan_feed"
  ],
  "mcp_servers": [{
    "name": "social-media-browser",
    "transport": "stdio",
    "command": "node",
    "args": ["/root/.deskclaw/tools/social-media-browser/server.js"],
    "env": {
      "COOKIES_PATH": "/root/.deskclaw/cookies/"
    }
  }],
  "scripts": [
    "social-media-browser/server.js",
    "social-media-browser/package.json",
    "social-media-browser/tools/x.js",
    "social-media-browser/tools/reddit.js",
    "social-media-browser/tools/substack.js",
    "social-media-browser/install.sh"
  ]
}
```

### SKILL.md Content Guidelines

The skill file teaches the agent:
- Which tool to use per platform and action
- Rate limiting etiquette: no more than 5 tweets/hour, 10 Reddit posts/day
- Content formatting per platform: X (280 chars, hashtags), Reddit (markdown, subreddit rules awareness), Substack (long-form, sections)
- How to handle `auth_expired` errors (report to user, stop retrying)
- When NOT to post (e.g., controversial topics, off-brand content)

## Phase 3: Media Generator MCP Server

### Component

`media-generator` -- a Python MCP server using `mcp` SDK + `httpx`.

### Tools

| Tool | Backend API | Parameters | Description |
|---|---|---|---|
| `generate_image` | OpenAI DALL-E 3 | `prompt`, `size` (1024x1024/1792x1024/1024x1792), `style` (natural/vivid) | Generate image from text prompt |
| `edit_image` | OpenAI Images | `image_url`, `prompt` | Edit an existing image with instruction |
| `generate_video` | Runway Gen-3 / Kling | `prompt`, `duration` (5s/10s), `reference_image_url` (optional) | Generate short video from text/image |
| `describe_image` | OpenAI Vision | `image_url` | Analyze image, return description. For self-critique before posting. |

### Architecture

```
OpenClaw Agent Process
  |
  |-- stdio --> media-generator MCP server (Python)
                  |
                  |-- httpx --> OpenAI API (images, vision)
                  |-- httpx --> Runway/Kling API (video)
                  |
                  |-- saves to /root/.deskclaw/media/
                  |-- uploads to workspace shared files
```

### Design Decisions

**Stateless HTTP calls.** No GPU, no local models. Each tool call is an API request. ~50MB RAM for the Python process.

**Output pipeline.** Generated media saved to `/root/.deskclaw/media/{timestamp}-{hash}.{ext}`, then uploaded to workspace shared files via the backend API. Tool returns both the temporary external URL and the persistent workspace file path.

**API key injection.** Keys provided as env vars in the gene manifest: `OPENAI_API_KEY`, `RUNWAY_API_KEY`. These are passed through to the MCP server process via stdio env.

**Cost guardrails via SKILL.md.** No hard enforcement in code. The skill instructs the agent:
- Confirm with user before generating video (~$0.50 per 5s clip)
- Prefer 1024x1024 for social media thumbnails
- Use `describe_image` to self-critique before posting
- Batch image generation requests when possible

**Pluggable backends.** Provider selection via env var `IMAGE_PROVIDER` (default: `openai`), `VIDEO_PROVIDER` (default: `runway`). Swapping providers is a config change, not a code change.

### Python Dependencies Installation

Handled at gene install time via install script on the PVC:

```bash
cd /root/.deskclaw/tools/media-generator
pip install mcp httpx
```

Python is already available in the OpenClaw image.

### Gene Manifest

```json
{
  "skill": {
    "name": "media-generator",
    "content": "<<SKILL.md content>>"
  },
  "tool_allow": [
    "generate_image", "edit_image",
    "generate_video", "describe_image"
  ],
  "mcp_servers": [{
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
  }],
  "scripts": [
    "media-generator/server.py",
    "media-generator/providers/__init__.py",
    "media-generator/providers/openai_images.py",
    "media-generator/providers/runway_video.py",
    "media-generator/requirements.txt",
    "media-generator/install.sh"
  ]
}
```

## Phase 4: Behavioral Skills (User-Authored)

Three pure-instruction genes with no MCP servers or tools. The user writes these based on their marketing playbooks.

### `trend-scout-playbook` (for 潮流侦察员)

Teaches the agent:
- How to identify trending topics on X and Reddit
- Analysis framework for evaluating trend relevance to the brand
- How to summarize findings for the workspace (posted to blackboard)
- Scanning frequency and focus areas

### `industry-researcher-playbook` (for 行业研究员)

Teaches the agent:
- How to consume scout findings from workspace context
- Deep analysis methodology (IDP, competitive analysis, market sizing)
- Output format and structure for research reports
- When to request more data vs. when to synthesize

### `copywriter-playbook` (for 文案撰写员)

Teaches the agent:
- Brand voice and tone guidelines
- Content adaptation per platform (X: punchy, Reddit: informative, Substack: long-form)
- When to include images/video and what style to request
- Publishing approval workflow (post to blackboard for review before publishing)

### Gene Manifest (same pattern for all three)

```json
{
  "skill": {
    "name": "trend-scout-playbook",
    "content": "<<SKILL.md with your custom instructions>>"
  }
}
```

## Implementation Dependencies

```
Phase 1: MCP sync fix
  |
  +---> Phase 2: social-media-browser (depends on Phase 1)
  |
  +---> Phase 3: media-generator (depends on Phase 1)

Phase 4: behavioral skills (independent, can start anytime)
```

Phases 2 and 3 are independent of each other and can be built in parallel after Phase 1.

## Resource Impact

| Agent | Current RAM | After genes | Notes |
|---|---|---|---|
| 潮流侦察员 | ~2Gi | ~2.5Gi | +Chromium (~500MB) |
| 行业研究员 | ~2Gi | ~2Gi | No change (no browser/media genes) |
| 文案撰写员 | ~2Gi | ~2.6Gi | +Chromium (~500MB) + media-generator (~50MB) |

All within the 4Gi pod memory limit. Cluster-level: memory requests stay at 2Gi per pod (unchanged), only limits matter if actual usage spikes.

## User Responsibilities

- Export session cookies for X, Reddit, and Substack (using a browser extension like "Cookie Editor") and place them on each agent's PVC at `/root/.deskclaw/cookies/{platform}.json`
- Provide OpenAI API key (required for image generation and vision)
- Optionally provide Runway or Kling API key for video generation
- Author the three behavioral SKILL.md playbooks

## Implementation Detail: Gene Scripts and Post-Deploy Installation

The current `scripts` field in gene manifests reads files from a **server-side directory** (`nodeskclaw-backend/app/data/gene_scripts/`), not from the manifest JSON payload. `deploy_scripts()` writes them as flat text files to `.deskclaw/tools/` on the PVC. There is no post-deploy command execution (no `npm install`, `pip install`, etc.).

This requires two changes:

### 1. MCP server source code placement

All MCP server source files (`.js`, `.py`, `package.json`, `requirements.txt`) must be placed in subdirectories under `nodeskclaw-backend/app/data/gene_scripts/`:

```
nodeskclaw-backend/app/data/gene_scripts/
  social-media-browser/
    server.js
    package.json
    tools/x.js
    tools/reddit.js
    tools/substack.js
  media-generator/
    server.py
    requirements.txt
    providers/__init__.py
    providers/openai_images.py
    providers/runway_video.py
```

The existing `_deploy_gene_scripts()` function already handles subdirectory paths (iterates `script_names` list and reads from `scripts_dir / name`). The `deploy_scripts()` adapter writes to `.deskclaw/tools/{filename}` preserving the path structure.

### 2. Post-deploy commands via self-bootstrapping

Rather than extending `_apply_manifest_actions` with a new `post_install_commands` field (which would require shell execution in the NFS context -- complex and risky), each MCP server self-bootstraps on first run:

**social-media-browser/server.js:**
```javascript
// On startup, check if node_modules exists. If not, run npm install + playwright install.
if (!fs.existsSync(path.join(__dirname, 'node_modules'))) {
  execSync('npm install && npx playwright install chromium', { cwd: __dirname, stdio: 'inherit' });
}
```

**media-generator/server.py:**
```python
# On startup, check if dependencies are available. If not, pip install.
try:
    import mcp
    import httpx
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r",
        str(Path(__file__).parent / "requirements.txt")])
```

First launch takes ~2 minutes (Playwright) or ~30 seconds (pip). Subsequent launches are instant since dependencies persist on the PVC.

## Out of Scope

- Workflow orchestration (sequential agent task chaining) -- identified as a gap in prior analysis, separate project
- Context management (token counting/truncation) -- separate project
- Circuit breaker silent drop fix -- separate bug fix
- Auto-login or CAPTCHA solving -- deliberately excluded, use pre-baked cookies
- Frontend/portal UI changes -- genes are installed via API, no UI changes needed
