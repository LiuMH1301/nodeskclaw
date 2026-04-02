"""Tests for MCP server sync and gene script deployment."""

import json
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.services.runtime.openclaw_gene_install_adapter import OpenClawGeneInstallAdapter


@pytest.mark.asyncio
async def test_deploy_scripts_creates_nested_directories():
    """deploy_scripts should create parent directories for nested script paths."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    scripts = {
        "social-media-browser/server.js": "// server code",
        "social-media-browser/tools/x.js": "// x tools",
        "social-media-browser/tools/reddit.js": "// reddit tools",
    }

    await adapter.deploy_scripts(fs, scripts)

    # Should have created the base dir plus each unique parent dir
    mkdir_paths = [c.args[0] for c in fs.mkdir.call_args_list]
    assert ".deskclaw/tools" in mkdir_paths
    assert ".deskclaw/tools/social-media-browser" in mkdir_paths
    assert ".deskclaw/tools/social-media-browser/tools" in mkdir_paths

    # All files should be written
    write_paths = [c.args[0] for c in fs.write_text.call_args_list]
    assert ".deskclaw/tools/social-media-browser/server.js" in write_paths
    assert ".deskclaw/tools/social-media-browser/tools/x.js" in write_paths
    assert ".deskclaw/tools/social-media-browser/tools/reddit.js" in write_paths
