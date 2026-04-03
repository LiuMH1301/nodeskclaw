"""Media Generator MCP Server -- image and video generation via external APIs.

Provider auto-discovery: all providers/*.py modules (except __init__.py) are
loaded at startup. Each must export PROVIDER (dict) and handle (async function).
"""

from __future__ import annotations

import importlib
import json
import os
import re
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

_API_KEY_RE = re.compile(r"(sk-[a-zA-Z0-9]{8,}|key-[a-zA-Z0-9]{8,}|Bearer\s+\S{8,})")

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/root/.deskclaw/media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# --- Auto-discover provider modules ---
ALLOWED_PROVIDERS = {"openai", "runway"}
PROVIDERS_DIR = Path(__file__).parent / "providers"
providers = []
for file in sorted(PROVIDERS_DIR.glob("*.py")):
    if file.name.startswith("_"):
        continue
    if file.stem not in ALLOWED_PROVIDERS:
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
        if tool.name in TOOL_HANDLERS:
            raise ValueError(f"Duplicate tool name '{tool.name}' across providers")
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
        rand = os.urandom(4).hex()
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

    # Check cost budget (records call before API execution -- intentional fail-closed design:
    # failed API calls still count against budget to prevent abuse via error loops)
    budget = await cost_tracker.check_budget(name)
    if not budget["allowed"]:
        return [TextContent(type="text", text=json.dumps(budget))]

    try:
        result = await handle_fn(name, arguments, ctx)
        return [TextContent(type="text", text=json.dumps(result))]
    except ValueError as e:
        # URL validation errors
        return [TextContent(type="text", text=json.dumps({"error": "validation_error", "message": str(e)}))]
    except Exception as e:
        # Sanitize: don't leak paths or API keys
        safe_msg = _API_KEY_RE.sub("[redacted]", str(e))
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
