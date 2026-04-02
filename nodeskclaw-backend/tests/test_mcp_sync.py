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


@pytest.mark.asyncio
async def test_sync_mcp_servers_writes_config():
    """sync_mcp_servers should write mcpServers section into openclaw.json."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    rec = MagicMock(
        transport="stdio",
        command="node",
        url=None,
        args=["/root/.deskclaw/tools/social-media-browser/server.js"],
        env={"COOKIES_PATH": "/root/.deskclaw/cookies/"},
        is_active=True,
    )
    rec.name = "social-media-browser"
    mcp_records = [rec]

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
    # Existing config preserved
    assert config["skills"] == {}


@pytest.mark.asyncio
async def test_sync_mcp_servers_filters_inactive():
    """sync_mcp_servers should skip records with is_active=False."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    active_rec = MagicMock(
        transport="stdio",
        command="node",
        url=None,
        args=None,
        env=None,
        is_active=True,
    )
    active_rec.name = "active-server"

    inactive_rec = MagicMock(
        transport="stdio",
        command="python",
        url=None,
        args=None,
        env=None,
        is_active=False,
    )
    inactive_rec.name = "inactive-server"

    mcp_records = [active_rec, inactive_rec]

    fs.read_text = AsyncMock(return_value=json.dumps({}))
    fs.write_text = AsyncMock()

    await adapter.sync_mcp_servers(fs, mcp_records)

    config = json.loads(fs.write_text.call_args[0][1])
    assert "active-server" in config["mcpServers"]
    assert "inactive-server" not in config["mcpServers"]


@pytest.mark.asyncio
async def test_sync_mcp_servers_skips_on_corrupt_config():
    """sync_mcp_servers should skip gracefully when openclaw.json is corrupt."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()
    fs.read_text = AsyncMock(return_value="NOT VALID JSON {{{")
    fs.write_text = AsyncMock()

    rec = MagicMock(transport="stdio", command="node",
                    url=None, args=None, env=None, is_active=True)
    rec.name = "test"
    mcp_records = [rec]

    # Should not raise
    await adapter.sync_mcp_servers(fs, mcp_records)

    # Should not write anything
    fs.write_text.assert_not_called()


@pytest.mark.asyncio
async def test_inject_mcp_servers_creates_db_records():
    """_inject_mcp_servers should create InstanceMcpServer rows from manifest."""
    from app.services.gene_service import _inject_mcp_servers

    # Mock the DB session
    db = AsyncMock()
    # Make select().where().limit() return no existing record
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {
            "name": "social-media-browser",
            "transport": "stdio",
            "command": "node",
            "args": ["/root/.deskclaw/tools/social-media-browser/server.js"],
            "env": {"COOKIES_PATH": "/root/.deskclaw/cookies/"},
        },
    ]

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers)

    # Should have called db.add with an InstanceMcpServer
    assert db.add.call_count == 1
    added_obj = db.add.call_args[0][0]
    assert added_obj.name == "social-media-browser"
    assert added_obj.instance_id == "inst-123"
    assert added_obj.source_gene_id == "gene-456"
    assert added_obj.transport == "stdio"
    assert added_obj.command == "node"
    assert db.flush.called


@pytest.mark.asyncio
async def test_inject_mcp_servers_skips_existing():
    """_inject_mcp_servers should not duplicate existing MCP server records."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    # Simulate existing record found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()  # existing record
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [{"name": "existing-server", "transport": "stdio", "command": "node"}]

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers)

    # Should NOT call db.add since record already exists
    assert db.add.call_count == 0
    assert db.flush.called


@pytest.mark.asyncio
async def test_sync_preserves_existing_config_and_adds_mcp():
    """Full round-trip: existing openclaw.json config is preserved, MCP servers added."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    existing_config = {
        "skills": {"load": {"extraDirs": ["/root/.openclaw/skills"]}},
        "tools": {"allow": ["nodeskclaw_blackboard", "nodeskclaw_proposals"]},
    }
    fs.read_text = AsyncMock(return_value=json.dumps(existing_config))
    fs.write_text = AsyncMock()

    rec1 = MagicMock(
        transport="stdio",
        command="node",
        url=None,
        args=["/root/.deskclaw/tools/social-media-browser/server.js"],
        env={"COOKIES_PATH": "/root/.deskclaw/cookies/"},
        is_active=True,
    )
    rec1.name = "social-media-browser"

    rec2 = MagicMock(
        transport="stdio",
        command="python",
        url=None,
        args=["/root/.deskclaw/tools/media-generator/server.py"],
        env={"OPENAI_API_KEY": "sk-test"},
        is_active=True,
    )
    rec2.name = "media-generator"

    mcp_records = [rec1, rec2]

    await adapter.sync_mcp_servers(fs, mcp_records)

    config = json.loads(fs.write_text.call_args[0][1])

    # Existing config fully preserved
    assert config["skills"]["load"]["extraDirs"] == ["/root/.openclaw/skills"]
    assert config["tools"]["allow"] == ["nodeskclaw_blackboard", "nodeskclaw_proposals"]

    # MCP servers correctly added
    assert len(config["mcpServers"]) == 2
    assert config["mcpServers"]["social-media-browser"]["command"] == "node"
    assert config["mcpServers"]["social-media-browser"]["transport"] == "stdio"
    assert config["mcpServers"]["media-generator"]["command"] == "python"
    assert config["mcpServers"]["media-generator"]["env"]["OPENAI_API_KEY"] == "sk-test"


@pytest.mark.asyncio
async def test_sync_then_uninstall_removes_entries():
    """Simulates install then uninstall: MCP entries should be fully removed."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    # After install: config has one MCP server
    fs.read_text = AsyncMock(return_value=json.dumps({
        "skills": {},
        "mcpServers": {
            "social-media-browser": {"transport": "stdio", "command": "node"},
        },
    }))
    fs.write_text = AsyncMock()

    # Uninstall: pass empty list (all MCP records were soft-deleted)
    await adapter.sync_mcp_servers(fs, [])

    config = json.loads(fs.write_text.call_args[0][1])
    assert config["mcpServers"] == {}
    assert config["skills"] == {}
