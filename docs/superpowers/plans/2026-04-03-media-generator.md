# Plan C: Media Generator MCP Server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide image generation (DALL-E 3), image editing, image description (GPT-4o Vision), and video generation (Runway Gen-3) to AI employees via a Python MCP server, packaged as a gene. Designed for easy provider extension (Midjourney, Stable Diffusion, Flux, etc.).

**Prerequisites:**
- Plan A (MCP Sync Foundation) must be shipped and verified.
- Prerequisite Task 0 (`${VAR}` env resolution) must be completed before Task 5.

**Architecture decisions:**
- **Provider module contract** (mirrors Plan B's platform module pattern): each provider is a self-contained Python module exporting a standard interface. Adding a new provider = one file + manifest update.
- **Server-side cost budget**: hard limits on API spend per hour, enforced in code (not just SKILL.md prose).
- **Python deps baked into image**: `mcp` and `httpx` pre-installed in the OpenClaw image alongside the Playwright layer (Plan B). Avoids the undefined `--target .deps` bootstrap problem.

**Spec:** `docs/superpowers/specs/2026-04-01-agent-customization-design.md`
**Review:** `docs/superpowers/reviews/2026-04-03-agent-customization-review.md`

---

## Provider Module Contract

Every provider file in `providers/` exports a standard dict and an async `handle` function:

```python
# providers/openai.py

PROVIDER = {
    "name": "openai",
    "allowed_domains": [
        "api.openai.com",
        "oaidalleapiprodscus.blob.core.windows.net",
    ],
    "env_keys": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
    "tools": [
        Tool(name="generate_image", description="...", inputSchema={...}),
        Tool(name="describe_image", description="...", inputSchema={...}),
    ],
    "cost_limits": {
        "generate_image": {"cost_per_call": 0.04, "max_per_hour": 25},
        "edit_image":     {"cost_per_call": 0.04, "max_per_hour": 25},
        "describe_image": {"cost_per_call": 0.005, "max_per_hour": 100},
    },
}

async def handle(tool_name: str, args: dict, ctx: ProviderContext) -> dict:
    """Dispatch tool call. ctx provides validated URLs, cost tracking, media dir."""
    ...
```

`server.py` auto-discovers all `providers/*.py` modules (excluding `__init__.py`) at startup. Shared utilities (URL validator, cost tracker) are initialized from aggregated provider data -- no hardcoded maps.

**Security decisions (learned from Plan B security audit):**
- **httpx redirect protection**: All `httpx.AsyncClient` instances created with `follow_redirects=False`. API keys in Authorization headers must never leak to redirect targets.
- **Base URL validation**: `OPENAI_BASE_URL` and similar env vars are validated against `allowed_domains` before use -- prevents env-var-based API key theft.
- **Subdomain suffix matching**: URL validator uses `.endswith(f".{domain}")` (same as Plan B), not exact match -- future CDN subdomains are covered.
- **Userinfo rejection**: URLs with `user:pass@host` are rejected (port from Plan B fix).
- **Input length limits**: All prompt/text fields have max length validation to prevent resource exhaustion.
- **Image size cap**: `_read_image_bytes` enforces 20MB limit to prevent OOM.
- **Error sanitization**: Only redacts sensitive strings > 8 chars to avoid aggressive false-positive replacement.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `nodeskclaw-backend/app/services/gene_service.py` | Add `${VAR}` resolution in `_inject_mcp_servers` |
| Modify | `nodeskclaw-artifacts/openclaw-image/Dockerfile` | Add Python MCP deps layer |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py` | MCP server with auto-discovery |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/url_validator.py` | URL allowlist factory (SSRF protection) |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/cost_tracker.py` | Server-side cost budget enforcer |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/__init__.py` | Package marker |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py` | Package marker (empty) |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai.py` | OpenAI DALL-E 3 + GPT-4o Vision |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway.py` | Runway Gen-3 video generation |
| Create | `nodeskclaw-backend/app/data/gene_manifests/media-generator.json` | Gene manifest |
| Create | `nodeskclaw-backend/app/data/gene_skills/media-generator.md` | SKILL.md |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/test_url_validator.py` | URL validator unit tests |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/test_cost_tracker.py` | Cost tracker unit tests |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/__init__.py` | Package marker |
| Create | `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/conftest.py` | sys.path fix for imports |
| Create | `nodeskclaw-backend/tests/test_media_generator.py` | Backend-side tests (manifest, env resolution) |

---

## Prerequisite Task 0: Add `${VAR}` environment variable resolution to `_inject_mcp_servers`

**Why:** Gene manifests use `${OPENAI_API_KEY}` placeholders in MCP server env blocks. Without resolution, literal `${...}` strings are written to `openclaw.json` and the MCP server gets broken env vars. This is a **cross-cutting infrastructure feature** that benefits all genes with env-dependent MCP servers (media-generator, and future genes).

**Files:**
- Modify: `nodeskclaw-backend/app/services/gene_service.py` (in `_inject_mcp_servers`)
- Create: `nodeskclaw-backend/tests/test_media_generator.py` (env resolution tests only)

- [ ] **Step 1: Write the failing test**

Create `nodeskclaw-backend/tests/test_media_generator.py`:

```python
"""Tests for media-generator gene: env var resolution, manifest validity."""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# --- ${VAR} Resolution Tests ---

@pytest.mark.asyncio
async def test_inject_mcp_servers_resolves_env_placeholders():
    """_inject_mcp_servers should resolve ${VAR} placeholders from instance env_vars."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {
            "name": "media-generator",
            "transport": "stdio",
            "command": "python",
            "args": ["/root/.deskclaw/tools/media-generator/server.py"],
            "env": {
                "OPENAI_API_KEY": "${OPENAI_API_KEY}",
                "RUNWAY_API_KEY": "${RUNWAY_API_KEY}",
                "STATIC_VAR": "no-placeholder",
            },
        },
    ]

    instance_env = {
        "OPENAI_API_KEY": "sk-test-openai-key",
        "RUNWAY_API_KEY": "rw-test-runway-key",
    }

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers, instance_env)

    added_obj = db.add.call_args[0][0]
    assert added_obj.env["OPENAI_API_KEY"] == "sk-test-openai-key"
    assert added_obj.env["RUNWAY_API_KEY"] == "rw-test-runway-key"
    assert added_obj.env["STATIC_VAR"] == "no-placeholder"


@pytest.mark.asyncio
async def test_inject_mcp_servers_unresolved_placeholder_becomes_empty():
    """Unresolved ${VAR} placeholders should become empty strings with a warning."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "env": {"MISSING_KEY": "${MISSING_KEY}"},
        },
    ]

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers, {})

    added_obj = db.add.call_args[0][0]
    assert added_obj.env["MISSING_KEY"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd nodeskclaw-backend && uv run pytest tests/test_media_generator.py::test_inject_mcp_servers_resolves_env_placeholders -v
```

Expected: FAIL -- `_inject_mcp_servers` does not accept `instance_env` parameter yet.

- [ ] **Step 3: Add env resolution to `_inject_mcp_servers`**

In `nodeskclaw-backend/app/services/gene_service.py`, modify `_inject_mcp_servers`:

```python
_ENV_PLACEHOLDER_RE = re.compile(r"^\$\{(\w+)\}$")


async def _inject_mcp_servers(
    db: AsyncSession,
    instance_id: str,
    gene_id: str,
    mcp_servers: list[dict],
    instance_env: dict[str, str] | None = None,
) -> None:
    """Create InstanceMcpServer rows, resolving ${VAR} placeholders in env."""
    env_vars = instance_env or {}

    for mcp_def in mcp_servers:
        name = mcp_def.get("name", "")
        if not name:
            continue

        # Check for existing (skip if already present)
        existing = await db.execute(
            select(InstanceMcpServer).where(
                InstanceMcpServer.instance_id == instance_id,
                InstanceMcpServer.name == name,
                not_deleted(InstanceMcpServer),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        # Resolve ${VAR} placeholders in env dict (immutable)
        raw_env = mcp_def.get("env") or {}
        resolved_env = {}
        for key, val in raw_env.items():
            match = _ENV_PLACEHOLDER_RE.match(str(val))
            if match:
                var_name = match.group(1)
                resolved_val = env_vars.get(var_name, "")
                if not resolved_val:
                    logger.warning(
                        "MCP env placeholder ${%s} unresolved for server %s",
                        var_name, name,
                    )
                resolved_env[key] = resolved_val
            else:
                resolved_env[key] = val

        mcp = InstanceMcpServer(
            id=str(uuid.uuid4()),
            instance_id=instance_id,
            name=name,
            transport=mcp_def.get("transport", "stdio"),
            command=mcp_def.get("command"),
            url=mcp_def.get("url"),
            args=mcp_def.get("args"),
            env=resolved_env,
            source="gene",
            source_gene_id=gene_id,
        )
        db.add(mcp)
    await db.flush()
```

- [ ] **Step 4: Update `_direct_install` call site to pass instance env**

Where `_inject_mcp_servers` is called in `_direct_install`:

```python
                    if mcp_defs:
                        inst_env = instance.env_vars or {}
                        await _inject_mcp_servers(db, instance_id, gene_id, mcp_defs, inst_env)
```

- [ ] **Step 5: Run tests**

```bash
cd nodeskclaw-backend && uv run pytest tests/test_media_generator.py -v
```

- [ ] **Step 6: Commit**

```bash
git add nodeskclaw-backend/app/services/gene_service.py \
        nodeskclaw-backend/tests/test_media_generator.py
git commit -m "feat(gene): _inject_mcp_servers 支持 \${VAR} 环境变量占位符解析"
```

---

## Task 1: Add Python MCP deps to the OpenClaw image

**Why:** The media-generator MCP server is Python-based and needs `mcp` and `httpx`. Baking them into the image (like Plan B bakes Chromium) avoids the undefined `--target .deps` bootstrap problem. No runtime `pip install` needed.

**Files:**
- Modify: `nodeskclaw-artifacts/openclaw-image/Dockerfile`

- [ ] **Step 1: Read current Dockerfile**

Read `nodeskclaw-artifacts/openclaw-image/Dockerfile` to understand existing layers. If Plan B's Playwright layer is already present, add the Python layer after it.

- [ ] **Step 2: Add Python MCP deps layer**

```dockerfile
# Pre-install Python MCP deps for media-generator gene
# pip install into a known path; gene server adds it to sys.path
RUN pip install --no-cache-dir --target /opt/gene-python-deps \
    mcp==1.0.0 \
    httpx==0.27.2
ENV GENE_PYTHON_DEPS=/opt/gene-python-deps
```

Note: If Python is not already in the image, add `python3 python3-pip` to the apt-get layer first. The `node:22-bookworm-slim` base image includes Python 3 via Debian but may not have pip.

- [ ] **Step 3: Verify**

```bash
docker run --rm deskclaw-openclaw:test python3 -c "import sys; sys.path.insert(0,'/opt/gene-python-deps'); import mcp; import httpx; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-artifacts/openclaw-image/Dockerfile
git commit -m "feat(image): OpenClaw 镜像预装 Python MCP 依赖（media-generator 基因依赖）"
```

---

## Task 2: Create shared utilities -- URL validator factory, cost tracker

**Why:** Same rationale as Plan B: shared utilities receive config from provider modules at startup (factory pattern). No hardcoded provider data.

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/__init__.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/url_validator.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/cost_tracker.py`

- [ ] **Step 1: Create package marker**

Create empty `lib/__init__.py`.

- [ ] **Step 2: Create URL validator factory (SSRF protection)**

Create `lib/url_validator.py`:

```python
"""
URL allowlist factory for SSRF protection.

Usage:
    validator = create_url_validator(providers)
    validator.require_valid_url("https://api.openai.com/v1/images")

Adding a provider: No changes here. The new provider module declares its
allowed_domains, and server.py passes all providers to this factory.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def create_url_validator(providers: list[dict], local_media_dir: str) -> "UrlValidator":
    """Build validator from aggregated provider configs."""
    allowed_domains: list[str] = []
    for p in providers:
        for domain in p.get("allowed_domains", []):
            allowed_domains.append(domain)

    resolved_media_dir = str(Path(local_media_dir).resolve())

    return UrlValidator(allowed_domains, resolved_media_dir)


class UrlValidator:
    """Immutable URL validator. Created once at startup, never mutated."""

    def __init__(self, allowed_domains: list[str], media_dir: str) -> None:
        self._allowed_domains = tuple(allowed_domains)
        self._media_dir = media_dir

    def _matches_domain(self, hostname: str) -> bool:
        """Check hostname against allowlist with subdomain suffix matching."""
        for d in self._allowed_domains:
            if hostname == d or hostname.endswith(f".{d}"):
                return True
        return False

    def validate_url(self, url: str) -> dict:
        """Returns {"valid": True, "url": normalized} or {"valid": False, "error": ...}."""
        # Local file path
        if url.startswith("/"):
            return self._validate_local_path(url)

        # Remote URL
        try:
            parsed = urlparse(url)
        except Exception:
            return {"valid": False, "error": "invalid_url", "message": f"Cannot parse URL: {url}"}

        if parsed.scheme != "https":
            return {"valid": False, "error": "invalid_protocol", "message": "Only HTTPS URLs are allowed."}

        # Reject URLs with userinfo (e.g. https://user:pass@host/)
        if parsed.username or parsed.password:
            return {"valid": False, "error": "invalid_url", "message": "URLs with credentials are not allowed."}

        if not self._matches_domain(parsed.hostname or ""):
            return {
                "valid": False,
                "error": "domain_not_allowed",
                "message": f"Domain {parsed.hostname} is not in the allowlist.",
            }

        return {"valid": True, "url": url}

    def require_valid_url(self, url: str) -> str:
        """Returns validated URL or raises ValueError."""
        result = self.validate_url(url)
        if not result["valid"]:
            raise ValueError(result["message"])
        return result.get("url", url)

    def _validate_local_path(self, path: str) -> dict:
        """Validate local file path against media directory (path traversal protection)."""
        try:
            resolved = str(Path(path).resolve())
        except Exception:
            return {"valid": False, "error": "invalid_path", "message": "Cannot resolve path."}

        if not resolved.startswith(self._media_dir):
            return {
                "valid": False,
                "error": "path_traversal",
                "message": "Path must be within the media directory.",
            }

        return {"valid": True, "url": resolved}
```

- [ ] **Step 3: Create cost tracker (server-side budget enforcer)**

Create `lib/cost_tracker.py`:

```python
"""
Server-side cost budget enforcer.

Prevents runaway API spend by tracking estimated cost per tool per hour.
Cost limits are declared by each provider module -- no hardcoded values here.

Usage:
    tracker = create_cost_tracker(providers)
    tracker.check_budget("generate_image")  # -> {"allowed": True} or {"allowed": False, ...}

Adding a provider: No changes here. The new provider module declares its
cost_limits, and server.py passes all providers to this factory.
"""

from __future__ import annotations

import time


def create_cost_tracker(providers: list[dict], budget_multiplier: float = 1.0) -> "CostTracker":
    """Build tracker from aggregated provider cost_limits."""
    limits: dict[str, dict] = {}
    for p in providers:
        for tool_name, config in p.get("cost_limits", {}).items():
            limits[tool_name] = {
                "cost_per_call": config["cost_per_call"],
                "max_per_hour": int(config["max_per_hour"] * budget_multiplier),
            }
    return CostTracker(limits)


class CostTracker:
    """Tracks API call counts per hour. Mutable state (intentional exception)."""

    def __init__(self, limits: dict[str, dict]) -> None:
        self._limits = limits
        # Mutable: call counts per tool, reset hourly
        self._counts: dict[str, list] = {}  # tool -> [timestamp, ...]

    def check_budget(self, tool_name: str) -> dict:
        """Check if a tool call is within budget. Returns {"allowed": True/False, ...}."""
        limit = self._limits.get(tool_name)
        if not limit:
            return {"allowed": True}

        now = time.time()
        one_hour_ago = now - 3600

        # Get recent calls (immutable filter)
        recent = [t for t in self._counts.get(tool_name, []) if t > one_hour_ago]
        self._counts[tool_name] = recent

        if len(recent) >= limit["max_per_hour"]:
            estimated_spend = len(recent) * limit["cost_per_call"]
            return {
                "allowed": False,
                "error": "budget_exceeded",
                "tool": tool_name,
                "calls_this_hour": len(recent),
                "max_per_hour": limit["max_per_hour"],
                "estimated_spend_usd": round(estimated_spend, 2),
                "message": (
                    f"Budget limit reached for {tool_name}: "
                    f"{len(recent)}/{limit['max_per_hour']} calls this hour "
                    f"(~${estimated_spend:.2f}). Wait for the budget window to reset."
                ),
            }

        # Record this call
        self._counts[tool_name] = [*recent, now]
        return {
            "allowed": True,
            "calls_this_hour": len(recent) + 1,
            "max_per_hour": limit["max_per_hour"],
            "estimated_cost_usd": round(limit["cost_per_call"], 4),
        }
```

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/lib/
git commit -m "feat(gene): media-generator 共享工具库（URL 校验工厂 + 成本预算追踪器）"
```

---

## Task 3: Create MCP server entry point with auto-discovery

**Key design:** Server auto-discovers provider modules from `providers/*.py` at startup. No manual imports per provider. Adding a new provider requires zero changes to this file.

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py`

- [ ] **Step 1: Create `server.py` with auto-discovery**

```python
"""Media Generator MCP Server -- image and video generation via external APIs.

Provider auto-discovery: all providers/*.py modules (except __init__.py) are
loaded at startup. Each must export PROVIDER (dict) and handle (async function).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Add image-baked deps to path
_gene_deps = os.environ.get("GENE_PYTHON_DEPS", "/opt/gene-python-deps")
if Path(_gene_deps).exists():
    sys.path.insert(0, _gene_deps)

# Add this directory to path for relative imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from lib.url_validator import create_url_validator
from lib.cost_tracker import create_cost_tracker

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/root/.deskclaw/media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# --- Auto-discover provider modules ---
PROVIDERS_DIR = Path(__file__).parent / "providers"
providers = []
for file in sorted(PROVIDERS_DIR.glob("*.py")):
    if file.name.startswith("_"):
        continue
    mod = importlib.import_module(f"providers.{file.stem}")
    providers.append({"module": mod, **mod.PROVIDER})

# --- Initialize shared utilities from aggregated provider data ---
url_validator = create_url_validator(providers, str(MEDIA_DIR))
cost_tracker = create_cost_tracker(providers)

# --- Build tool registry ---
ALL_TOOLS = []
TOOL_HANDLERS: dict[str, tuple] = {}  # tool_name -> (handle_fn, provider_config)
for p in providers:
    for tool in p["tools"]:
        ALL_TOOLS.append(tool)
        TOOL_HANDLERS[tool.name] = (p["module"].handle, p)

# --- Provider context (passed to handlers) ---
@dataclass(frozen=True)
class ProviderContext:
    """Immutable context passed to provider handle functions."""

    url_validator: object
    cost_tracker: object
    media_dir: Path

    def save_path(self, ext: str) -> Path:
        """Generate a unique save path for media files."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        rand = os.urandom(8).hex()[:8]
        return self.media_dir / f"{ts}-{rand}.{ext}"

    def validate_base_url(self, base_url: str) -> str:
        """Validate provider base URL against allowed domains (prevents env-var API key theft)."""
        self.url_validator.require_valid_url(base_url)
        return base_url


ctx = ProviderContext(url_validator=url_validator, cost_tracker=cost_tracker, media_dir=MEDIA_DIR)

# --- MCP server setup ---
server = Server("media-generator")


@server.list_tools()
async def list_tools():
    return ALL_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler_entry = TOOL_HANDLERS.get(name)
    if not handler_entry:
        return [TextContent(type="text", text=json.dumps({"error": "unknown_tool", "tool": name}))]

    handle_fn, _provider_config = handler_entry

    # Check cost budget
    budget = cost_tracker.check_budget(name)
    if not budget["allowed"]:
        return [TextContent(type="text", text=json.dumps(budget))]

    try:
        result = await handle_fn(name, arguments, ctx)
        return [TextContent(type="text", text=json.dumps(result))]
    except ValueError as e:
        # URL validation errors
        return [TextContent(type="text", text=json.dumps({"error": "validation_error", "message": str(e)}))]
    except Exception as e:
        # Sanitize: don't leak paths or API keys (only redact strings > 8 chars to avoid false positives)
        safe_msg = str(e)
        for sensitive in [str(Path.home()), str(MEDIA_DIR), os.environ.get("OPENAI_API_KEY", ""), os.environ.get("RUNWAY_API_KEY", "")]:
            if sensitive and len(sensitive) > 8:
                safe_msg = safe_msg.replace(sensitive, "[redacted]")
        safe_msg = safe_msg[:200]
        return [TextContent(type="text", text=json.dumps({"error": "internal_error", "message": safe_msg}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/server.py
git commit -m "feat(gene): media-generator MCP 服务器（自动发现 provider + 成本预算 + 错误脱敏）"
```

---

## Task 4: Create OpenAI provider module (DALL-E 3 + GPT-4o Vision)

**This is the reference implementation for the provider module contract.**

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/__init__.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/openai.py`

- [ ] **Step 1: Create empty `providers/__init__.py`**

- [ ] **Step 2: Create `providers/openai.py`**

```python
"""
OpenAI provider module: DALL-E 3 image generation + GPT-4o Vision description.

To add a new provider, copy this file's structure:
1. Export PROVIDER dict with: name, allowed_domains, env_keys, tools, cost_limits
2. Export async handle(tool_name, args, ctx) function
3. Place in providers/<name>.py
4. Add tool names to gene manifest's tool_allow
That's it -- server.py auto-discovers this file.
"""

from __future__ import annotations

import base64
import os

import httpx
from mcp.types import Tool


PROVIDER = {
    "name": "openai",
    "allowed_domains": [
        "api.openai.com",
        "oaidalleapiprodscus.blob.core.windows.net",
    ],
    "env_keys": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
    "tools": [
        Tool(
            name="generate_image",
            description="Generate an image from a text prompt using DALL-E 3. Cost: ~$0.04 per image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Image generation prompt."},
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "default": "1024x1024",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["natural", "vivid"],
                        "default": "vivid",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="edit_image",
            description="Edit an existing image with a text instruction. Cost: ~$0.04 per edit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL or local path of the image to edit."},
                    "prompt": {"type": "string", "description": "Edit instruction."},
                },
                "required": ["image_url", "prompt"],
            },
        ),
        Tool(
            name="describe_image",
            description="Analyze an image and return a text description using GPT-4o Vision. Cost: ~$0.005.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL or local path of the image."},
                },
                "required": ["image_url"],
            },
        ),
    ],
    "cost_limits": {
        "generate_image": {"cost_per_call": 0.04, "max_per_hour": 25},
        "edit_image": {"cost_per_call": 0.04, "max_per_hour": 25},
        "describe_image": {"cost_per_call": 0.005, "max_per_hour": 100},
    },
}


def _api_key() -> str:
    """Read API key at call time (supports rotation without restart)."""
    return os.environ.get("OPENAI_API_KEY", "")


MAX_PROMPT_LENGTH = 4000
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


def _base_url(ctx) -> str:
    """Read and validate base URL at call time. Prevents env-var-based API key theft."""
    url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ctx.validate_base_url(url)
    return url


def _safe_client(timeout: int = 60) -> httpx.AsyncClient:
    """Create httpx client with security defaults: no redirect following."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


async def _read_image_bytes(url: str, ctx) -> bytes:
    """Read image bytes from validated URL or local path. Max 20MB."""
    ctx.url_validator.require_valid_url(url)

    if url.startswith("/"):
        from pathlib import Path
        data = Path(url).read_bytes()
        if len(data) > MAX_IMAGE_SIZE:
            raise ValueError(f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit.")
        return data

    async with _safe_client(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        if len(resp.content) > MAX_IMAGE_SIZE:
            raise ValueError(f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit.")
        content_type = resp.headers.get("content-type", "")
        if content_type and not content_type.startswith("image/"):
            raise ValueError(f"Expected image content, got {content_type}.")
        return resp.content


async def handle(tool_name: str, args: dict, ctx) -> dict:
    """Dispatch OpenAI tool calls."""
    api_key = _api_key()
    if not api_key:
        return {"error": "OPENAI_API_KEY not configured"}

    if tool_name == "generate_image":
        return await _generate_image(api_key, args, ctx)
    elif tool_name == "edit_image":
        return await _edit_image(api_key, args, ctx)
    elif tool_name == "describe_image":
        return await _describe_image(api_key, args, ctx)
    else:
        return {"error": "unknown_tool", "tool": tool_name}


async def _generate_image(api_key: str, args: dict, ctx) -> dict:
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    size = args.get("size", "1024x1024")
    style = args.get("style", "vivid")
    base = _base_url(ctx)

    async with _safe_client(timeout=120) as client:
        resp = await client.post(
            f"{base}/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
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

    save_path = ctx.save_path("png")
    save_path.write_bytes(image_bytes)

    return {
        "local_path": str(save_path),
        "revised_prompt": image_data.get("revised_prompt", prompt),
        "size": size,
    }


async def _edit_image(api_key: str, args: dict, ctx) -> dict:
    image_url = args["image_url"]
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    img_bytes = await _read_image_bytes(image_url, ctx)
    base = _base_url(ctx)

    async with _safe_client(timeout=120) as client:
        resp = await client.post(
            f"{base}/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"image": ("image.png", img_bytes, "image/png")},
            data={"prompt": prompt, "n": 1, "size": "1024x1024"},
        )
        resp.raise_for_status()
        data = resp.json()

    return {"url": data["data"][0].get("url", ""), "prompt": prompt}


async def _describe_image(api_key: str, args: dict, ctx) -> dict:
    image_url = args["image_url"]
    ctx.url_validator.require_valid_url(image_url)

    content = [
        {"type": "text", "text": "Describe this image in detail. Focus on composition, mood, colors, and subject matter."},
    ]
    if image_url.startswith("/"):
        from pathlib import Path
        img_bytes = Path(image_url).read_bytes()
        if len(img_bytes) > MAX_IMAGE_SIZE:
            return {"error": "invalid_input", "message": f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit."}
        encoded = base64.b64encode(img_bytes).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
    else:
        content.append({"type": "image_url", "image_url": {"url": image_url}})

    base = _base_url(ctx)

    async with _safe_client(timeout=60) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return {"description": data["choices"][0]["message"]["content"]}
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/
git commit -m "feat(gene): media-generator OpenAI provider（DALL-E 3 生成/编辑 + GPT-4o 图片描述）"
```

---

## Task 5: Create Runway video provider module

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway.py`

- [ ] **Step 1: Create `providers/runway.py`**

Same provider module contract. Key specifics:

```python
PROVIDER = {
    "name": "runway",
    "allowed_domains": [
        "api.dev.runwayml.com",
    ],
    "env_keys": ["RUNWAY_API_KEY"],
    "tools": [
        Tool(
            name="generate_video",
            description="Generate a short video from a text prompt using Runway Gen-3. Cost: ~$0.50 per 5s video. IMPORTANT: Confirm cost with user before generating.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Video generation prompt."},
                    "duration": {
                        "type": "string",
                        "enum": ["5s", "10s"],
                        "default": "5s",
                    },
                    "reference_image_url": {
                        "type": "string",
                        "description": "Optional reference image URL or local path.",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ],
    "cost_limits": {
        "generate_video": {"cost_per_call": 0.50, "max_per_hour": 5},
    },
}
```

Full implementation:

```python
"""
Runway Gen-3 provider module: video generation from text/image prompts.

Same provider module contract as openai.py. See that file for the pattern.
"""

from __future__ import annotations

import asyncio
import os

import httpx
from mcp.types import Tool

MAX_PROMPT_LENGTH = 2000
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB

PROVIDER = {
    "name": "runway",
    "allowed_domains": [
        "api.dev.runwayml.com",
    ],
    "env_keys": ["RUNWAY_API_KEY"],
    "tools": [
        Tool(
            name="generate_video",
            description="Generate a short video from a text prompt using Runway Gen-3. Cost: ~$0.50 per 5s video. IMPORTANT: Confirm cost with user before generating.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Video generation prompt."},
                    "duration": {
                        "type": "string",
                        "enum": ["5s", "10s"],
                        "default": "5s",
                    },
                    "reference_image_url": {
                        "type": "string",
                        "description": "Optional reference image URL or local path.",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ],
    "cost_limits": {
        "generate_video": {"cost_per_call": 0.50, "max_per_hour": 5},
    },
}

API_BASE = "https://api.dev.runwayml.com/v1"
POLL_INTERVAL = 5  # seconds
MAX_POLL_ITERATIONS = 60  # 5 minutes total


def _api_key() -> str:
    return os.environ.get("RUNWAY_API_KEY", "")


def _safe_client(timeout: int = 60) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


async def handle(tool_name: str, args: dict, ctx) -> dict:
    """Dispatch Runway tool calls."""
    api_key = _api_key()
    if not api_key:
        return {"error": "RUNWAY_API_KEY not configured"}

    if tool_name == "generate_video":
        return await _generate_video(api_key, args, ctx)
    else:
        return {"error": "unknown_tool", "tool": tool_name}


async def _generate_video(api_key: str, args: dict, ctx) -> dict:
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    duration = args.get("duration", "5s")
    duration_seconds = 10 if duration == "10s" else 5

    # Build request payload
    payload = {
        "promptText": prompt,
        "model": "gen3a_turbo",
        "duration": duration_seconds,
    }

    # Optional reference image
    ref_url = args.get("reference_image_url")
    if ref_url:
        ctx.url_validator.require_valid_url(ref_url)
        # If local path, read and would need to upload -- for now, only support URL refs
        if not ref_url.startswith("/"):
            payload["promptImage"] = ref_url

    # Submit generation task
    async with _safe_client(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/image_to_video",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Runway-Version": "2024-11-06",
            },
            json=payload,
        )
        resp.raise_for_status()
        task = resp.json()

    task_id = task.get("id")
    if not task_id:
        return {"error": "api_error", "message": "No task ID returned from Runway API."}

    # Poll for completion
    for _ in range(MAX_POLL_ITERATIONS):
        await asyncio.sleep(POLL_INTERVAL)

        async with _safe_client(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Runway-Version": "2024-11-06",
                },
            )
            resp.raise_for_status()
            status = resp.json()

        state = status.get("status", "")
        if state == "SUCCEEDED":
            output_url = (status.get("output", []) or [""])[0]
            if not output_url:
                return {"error": "api_error", "message": "Video generated but no output URL returned."}

            # Download and save video
            async with _safe_client(timeout=120) as client:
                video_resp = await client.get(output_url)
                video_resp.raise_for_status()

            save_path = ctx.save_path("mp4")
            save_path.write_bytes(video_resp.content)

            return {
                "local_path": str(save_path),
                "duration": duration,
                "task_id": task_id,
                "prompt": prompt,
            }

        if state == "FAILED":
            failure = status.get("failure", "Unknown failure")
            return {"error": "generation_failed", "message": str(failure)[:200], "task_id": task_id}

    return {"error": "timeout", "message": f"Video generation timed out after {MAX_POLL_ITERATIONS * POLL_INTERVAL}s.", "task_id": task_id}
```

- [ ] **Step 2: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/providers/runway.py
git commit -m "feat(gene): media-generator Runway Gen-3 视频生成 provider"
```

---

## Task 6: Create gene manifest and SKILL.md

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/media-generator.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/media-generator.md`

- [ ] **Step 1: Create gene manifest**

```json
{
  "skill": {
    "name": "media-generator",
    "description": "Image and video generation via external APIs (DALL-E 3, Runway Gen-3)"
  },
  "tool_allow": [
    "generate_image",
    "edit_image",
    "describe_image",
    "generate_video"
  ],
  "mcp_servers": [
    {
      "name": "media-generator",
      "transport": "stdio",
      "command": "python3",
      "args": ["/root/.deskclaw/tools/media-generator/server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "OPENAI_BASE_URL": "${OPENAI_BASE_URL}",
        "RUNWAY_API_KEY": "${RUNWAY_API_KEY}",
        "MEDIA_DIR": "/root/.deskclaw/media"
      }
    }
  ],
  "scripts": [
    "media-generator/server.py",
    "media-generator/lib/__init__.py",
    "media-generator/lib/url_validator.py",
    "media-generator/lib/cost_tracker.py",
    "media-generator/providers/__init__.py",
    "media-generator/providers/openai.py",
    "media-generator/providers/runway.py"
  ]
}
```

Note: `${OPENAI_API_KEY}`, `${OPENAI_BASE_URL}`, and `${RUNWAY_API_KEY}` are resolved at install time by the `_inject_mcp_servers` env resolution (Prerequisite Task 0). `MEDIA_DIR` is a static value. When adding a new provider, update `tool_allow` and `scripts`.

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/media-generator.md`:

```markdown
---
name: media-generator
description: Image and video generation tools via DALL-E 3 and Runway Gen-3
---

# Media Generator

You have access to image and video generation tools powered by external APIs.

## Available Tools

| Tool | Provider | Cost | Description |
|------|----------|------|-------------|
| generate_image | DALL-E 3 | ~$0.04 | Generate an image from a text prompt |
| edit_image | DALL-E 3 | ~$0.04 | Edit an existing image with instructions |
| describe_image | GPT-4o | ~$0.005 | Analyze an image and describe it |
| generate_video | Runway Gen-3 | ~$0.50 | Generate a short video from a prompt |

## Cost Budgets (server-enforced)

API calls have hard budget limits enforced server-side. These cannot be bypassed.

| Tool | Max per hour | Max cost/hour |
|------|-------------|---------------|
| generate_image | 25 | ~$1.00 |
| edit_image | 25 | ~$1.00 |
| describe_image | 100 | ~$0.50 |
| generate_video | 5 | ~$2.50 |

If you receive a `budget_exceeded` error, wait for the budget window to reset.

## Workflow

1. **Plan** -- Decide what media you need based on the content strategy
2. **Generate** -- Create images or video with descriptive prompts
3. **Review** -- Use `describe_image` to self-critique generated images
4. **Iterate** -- Regenerate or edit if quality is insufficient
5. **Save** -- Generated media is auto-saved to the media directory

## Image Generation Tips

- Be specific in prompts: include style, mood, composition, colors
- Use `1792x1024` for landscape/hero images, `1024x1792` for portrait/stories
- Use `style: "natural"` for photorealistic, `style: "vivid"` for artistic

## Video Generation

- ALWAYS confirm cost with the user before generating video
- Use a reference image when possible for better results
- 5s videos are cheaper and faster; use 10s only when needed
- Video generation takes 1-5 minutes -- inform the user of the wait

## What NOT to Do

- Never generate video without confirming cost with the user first
- Never generate more than 10 images in a single batch without user approval
- Never fabricate that an image was generated -- if generation fails, report the error
- Never use describe_image as a substitute for actually reading text in an image
- Never ignore budget_exceeded errors -- they protect against cost overruns
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/media-generator.json \
        nodeskclaw-backend/app/data/gene_skills/media-generator.md
git commit -m "feat(gene): media-generator 基因清单和 SKILL.md（含成本预算表 + 视频生成审批流程）"
```

---

## Task 7: Tests

**Testing strategy:**
- **Python unit tests in `gene_scripts/media-generator/tests/`**: test url_validator and cost_tracker directly (these are standalone Python modules)
- **Python integration tests in `tests/test_media_generator.py`**: test manifest validity, env resolution, and run gene_scripts tests via subprocess
- **No direct imports from `gene_scripts` in backend tests**: gene_scripts are standalone, not part of the backend package

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/__init__.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/test_url_validator.py`
- Create: `nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/test_cost_tracker.py`
- Modify: `nodeskclaw-backend/tests/test_media_generator.py`

- [ ] **Step 1: Create conftest.py for import path setup**

Create `gene_scripts/media-generator/tests/conftest.py`:

```python
"""Fix sys.path so tests can import from lib/ and providers/ without package install."""

import sys
from pathlib import Path

# Add gene_scripts/media-generator to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 3: Create URL validator unit tests**

Create `gene_scripts/media-generator/tests/test_url_validator.py`:

```python
"""Unit tests for URL validator factory."""

import pytest
from lib.url_validator import create_url_validator

MOCK_PROVIDERS = [
    {"allowed_domains": ["api.openai.com", "oaidalleapiprodscus.blob.core.windows.net"]},
    {"allowed_domains": ["api.dev.runwayml.com"]},
]


@pytest.fixture
def validator(tmp_path):
    media_dir = str(tmp_path / "media")
    (tmp_path / "media").mkdir()
    return create_url_validator(MOCK_PROVIDERS, media_dir)


def test_allows_openai_domain(validator):
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is True


def test_allows_runway_domain(validator):
    result = validator.validate_url("https://api.dev.runwayml.com/v1/tasks")
    assert result["valid"] is True


def test_rejects_http(validator):
    result = validator.validate_url("http://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "invalid_protocol"


def test_rejects_unknown_domain(validator):
    result = validator.validate_url("https://evil.com/steal")
    assert result["valid"] is False
    assert result["error"] == "domain_not_allowed"


def test_rejects_internal_ip(validator):
    result = validator.validate_url("https://169.254.169.254/metadata")
    assert result["valid"] is False


def test_allows_local_media_path(validator, tmp_path):
    media_file = tmp_path / "media" / "test.png"
    media_file.write_bytes(b"fake")
    result = validator.validate_url(str(media_file))
    assert result["valid"] is True


def test_rejects_path_traversal(validator, tmp_path):
    traversal = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    result = validator.validate_url(traversal)
    assert result["valid"] is False
    assert result["error"] == "path_traversal"


def test_rejects_url_encoded_traversal(validator, tmp_path):
    """Path.resolve() handles this -- %2e%2e in raw string won't match media dir."""
    result = validator.validate_url("/root/.deskclaw/media/%2e%2e/%2e%2e/etc/passwd")
    assert result["valid"] is False


def test_rejects_urls_with_userinfo(validator):
    result = validator.validate_url("https://user:pass@api.openai.com/v1")
    assert result["valid"] is False
    assert result["error"] == "invalid_url"


def test_accepts_subdomain_of_allowed_domain(validator):
    result = validator.validate_url("https://cdn.api.openai.com/files/123")
    assert result["valid"] is True


def test_path_traversal_error_does_not_leak_media_dir(validator, tmp_path):
    traversal = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    result = validator.validate_url(traversal)
    assert "media directory" in result["message"]
    assert str(tmp_path) not in result["message"]


def test_require_valid_url_raises_on_invalid(validator):
    with pytest.raises(ValueError):
        validator.require_valid_url("http://evil.com/bad")
```

- [ ] **Step 4: Create cost tracker unit tests**

Create `gene_scripts/media-generator/tests/test_cost_tracker.py`:

```python
"""Unit tests for cost tracker."""

import time
from unittest.mock import patch

from lib.cost_tracker import create_cost_tracker


MOCK_PROVIDERS = [
    {
        "cost_limits": {
            "generate_image": {"cost_per_call": 0.04, "max_per_hour": 3},
            "generate_video": {"cost_per_call": 0.50, "max_per_hour": 2},
        },
    },
]


def test_allows_within_budget():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    result = tracker.check_budget("generate_image")
    assert result["allowed"] is True
    assert result["calls_this_hour"] == 1


def test_blocks_over_budget():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    tracker.check_budget("generate_image")
    tracker.check_budget("generate_image")
    tracker.check_budget("generate_image")
    result = tracker.check_budget("generate_image")
    assert result["allowed"] is False
    assert result["error"] == "budget_exceeded"
    assert result["calls_this_hour"] == 3


def test_allows_unknown_tool():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    result = tracker.check_budget("unknown_tool")
    assert result["allowed"] is True


def test_budget_resets_after_hour():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    # Fill budget
    for _ in range(3):
        tracker.check_budget("generate_image")

    # Simulate 1 hour passing
    future = time.time() + 3601
    with patch("lib.cost_tracker.time") as mock_time:
        mock_time.time.return_value = future
        result = tracker.check_budget("generate_image")
    assert result["allowed"] is True


def test_budget_multiplier():
    tracker = create_cost_tracker(MOCK_PROVIDERS, budget_multiplier=2.0)
    # Should allow 6 calls (3 * 2.0)
    for _ in range(6):
        result = tracker.check_budget("generate_image")
        assert result["allowed"] is True
    result = tracker.check_budget("generate_image")
    assert result["allowed"] is False


def test_reports_estimated_spend():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    for _ in range(3):
        tracker.check_budget("generate_video")
    result = tracker.check_budget("generate_video")
    assert result["allowed"] is False
    assert result["estimated_spend_usd"] > 0
```

- [ ] **Step 5: Add backend-side manifest and subprocess tests**

Append to `nodeskclaw-backend/tests/test_media_generator.py`:

```python
import subprocess
from pathlib import Path

MANIFESTS_DIR = Path(__file__).parent.parent / "app/data/gene_manifests"
SKILLS_DIR = Path(__file__).parent.parent / "app/data/gene_skills"
SCRIPTS_DIR = Path(__file__).parent.parent / "app/data/gene_scripts"


def test_manifest_exists_and_valid():
    manifest_path = MANIFESTS_DIR / "media-generator.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["skill"]["name"] == "media-generator"
    assert len(manifest["tool_allow"]) == 4
    assert len(manifest["mcp_servers"]) == 1
    assert manifest["mcp_servers"][0]["transport"] == "stdio"
    # Verify ${VAR} placeholders are present (resolved at install time)
    env = manifest["mcp_servers"][0]["env"]
    assert env["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"


def test_all_scripts_exist():
    manifest_path = MANIFESTS_DIR / "media-generator.json"
    manifest = json.loads(manifest_path.read_text())
    for script in manifest["scripts"]:
        assert (SCRIPTS_DIR / script).exists(), f"Script not found: {script}"


def test_skill_md_exists_and_has_required_sections():
    skill_path = SKILLS_DIR / "media-generator.md"
    assert skill_path.exists()
    content = skill_path.read_text()
    assert content.startswith("---")
    assert "name: media-generator" in content
    assert "## Workflow" in content
    assert "## What NOT to Do" in content
    assert "budget" in content.lower()


def test_gene_scripts_unit_tests():
    """Run standalone unit tests inside gene_scripts/media-generator/."""
    scripts_dir = SCRIPTS_DIR / "media-generator"
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=scripts_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Gene scripts tests failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 6: Run all tests**

```bash
# Run gene_scripts tests directly
cd nodeskclaw-backend/app/data/gene_scripts/media-generator && python3 -m pytest tests/ -v

# Run backend tests
cd nodeskclaw-backend && uv run pytest tests/test_media_generator.py -v
```

- [ ] **Step 7: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_scripts/media-generator/tests/ \
        nodeskclaw-backend/tests/test_media_generator.py
git commit -m "test(gene): media-generator 单元测试（URL 校验/成本追踪/清单校验 + 子进程集成）"
```

---

## Task 8: Verify end-to-end

- [ ] **Step 1: Run full backend test suite**

```bash
cd nodeskclaw-backend && uv run pytest tests/ -v
```

- [ ] **Step 2: Verify directory structure**

```bash
find nodeskclaw-backend/app/data/gene_scripts/media-generator -type f | sort
```

Expected:
```
lib/__init__.py
lib/cost_tracker.py
lib/url_validator.py
providers/__init__.py
providers/openai.py
providers/runway.py
server.py
tests/__init__.py
tests/conftest.py
tests/test_cost_tracker.py
tests/test_url_validator.py
```

- [ ] **Step 3: Verify Docker build (manual)**

```bash
cd nodeskclaw-artifacts
docker build --platform linux/amd64 -t deskclaw-openclaw:test -f openclaw-image/Dockerfile .
docker run --rm deskclaw-openclaw:test python3 -c "import sys; sys.path.insert(0,'/opt/gene-python-deps'); import mcp; import httpx; print('OK')"
```

- [ ] **Step 4: Commit if fixups needed**

```bash
git add -A && git commit -m "chore: Plan C 最终验证和修复"
```

---

## Adding a New Provider (Developer Guide)

When you need to add a new provider (e.g., Midjourney, Stable Diffusion, Flux):

### 1. Create the provider module

Create `providers/<name>.py` following the contract:

```python
from mcp.types import Tool

PROVIDER = {
    "name": "<name>",
    "allowed_domains": ["<api-domain>", "<cdn-domain>"],
    "env_keys": ["<NAME>_API_KEY"],
    "tools": [
        Tool(name="<name>_generate", description="...", inputSchema={...}),
    ],
    "cost_limits": {
        "<name>_generate": {"cost_per_call": 0.XX, "max_per_hour": N},
    },
}

async def handle(tool_name: str, args: dict, ctx) -> dict:
    # Use ctx.url_validator, ctx.cost_tracker, ctx.save_path()
    ...
```

### 2. Update gene manifest

Add the new tool names to `tool_allow` and the new file to `scripts` in `gene_manifests/media-generator.json`. Add any new `${VAR}` env placeholders.

### 3. Add tests

Add unit tests in `tests/test_<name>_provider.py` for provider-specific logic.

**That's it.** No changes to `server.py`, `lib/url_validator.py`, or `lib/cost_tracker.py`.

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| API key leakage via httpx redirects | **CRITICAL** | `follow_redirects=False` on all httpx clients; auth headers never sent to redirect targets |
| API key theft via env var `OPENAI_BASE_URL` | **CRITICAL** | `validate_base_url()` checks base URL against `allowed_domains` before making requests |
| API key leakage via error messages | HIGH | Multi-pattern sanitization in server.py (only redacts strings > 8 chars); keys read per-call, not stored in module state |
| SSRF via `image_url` / `reference_image_url` | HIGH | URL allowlist factory with subdomain suffix matching; userinfo rejection; `Path.resolve()` for path traversal |
| OOM via oversized image downloads | HIGH | 20MB size cap in `_read_image_bytes`; Content-Type validation |
| Resource exhaustion via long prompts | HIGH | `MAX_PROMPT_LENGTH` enforced (4000 DALL-E, 2000 Runway) |
| Cost overrun from generation loops | HIGH | Server-side cost tracker with per-tool hourly budgets; `budget_exceeded` error blocks further calls |
| Python dep conflicts with OpenClaw runtime | MEDIUM | Deps baked into `/opt/gene-python-deps` (isolated from system Python) |
| Runway API timeout (5-minute video gen) | LOW | 300s total poll timeout (60 iterations * 5s); async sleep does not block event loop |
| `${VAR}` placeholder not resolved | MEDIUM | `_inject_mcp_servers` logs warning; MCP server gets empty string and returns clear error |

## Acceptance Criteria

- [ ] `_inject_mcp_servers` resolves `${VAR}` placeholders from instance env_vars
- [ ] Unresolved placeholders become empty strings with a logged warning
- [ ] URL validation blocks non-allowlisted domains, userinfo URLs, and path traversal
- [ ] URL validator supports subdomain suffix matching (e.g. `cdn.api.openai.com` matches `api.openai.com`)
- [ ] All httpx clients use `follow_redirects=False`
- [ ] `OPENAI_BASE_URL` env var is validated against `allowed_domains` before use
- [ ] Image downloads capped at 20MB with Content-Type validation
- [ ] Prompt/text inputs have max length validation
- [ ] Cost tracker blocks API calls exceeding hourly budget
- [ ] API keys are read from `os.environ` at call time, not import time
- [ ] Error messages do not leak file paths or API keys (only redacts strings > 8 chars)
- [ ] `ProviderContext` is a frozen dataclass (immutable)
- [ ] Adding a new provider requires only: 1 `providers/*.py` file + manifest update
- [ ] Gene scripts unit tests pass independently (`python3 -m pytest tests/`)
- [ ] Backend manifest and integration tests pass
- [ ] Gene manifest references all script files that exist on disk
