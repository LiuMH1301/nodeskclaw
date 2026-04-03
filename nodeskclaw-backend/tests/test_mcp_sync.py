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


@pytest.mark.asyncio
async def test_uninstall_flush_excludes_soft_deleted_mcp_rows():
    """After soft-deleting MCP rows, the remaining query must NOT include them."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {"name": "server-a", "transport": "stdio", "command": "node"},
    ]
    await _inject_mcp_servers(db, "inst-1", "gene-1", mcp_servers)
    assert db.add.call_count == 1

    added = db.add.call_args[0][0]
    assert added.name == "server-a"
    assert db.flush.called

    # Simulate: existing record found (soft-deleted and re-queried should skip)
    mock_result2 = MagicMock()
    mock_result2.scalar_one_or_none.return_value = MagicMock()
    db.execute = AsyncMock(return_value=mock_result2)
    db.add.reset_mock()
    await _inject_mcp_servers(db, "inst-1", "gene-1", mcp_servers)
    assert db.add.call_count == 0


@pytest.mark.asyncio
async def test_partial_env_placeholder_logs_warning_not_crash():
    """'Bearer ${TOKEN}' is a partial placeholder -- should warn, not crash."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {
            "name": "api-server",
            "transport": "stdio",
            "command": "node",
            "env": {"AUTH": "Bearer ${TOKEN}"},
        },
    ]

    # Should not crash on partial placeholder
    await _inject_mcp_servers(db, "inst-1", "gene-1", mcp_servers)

    # Should still add the MCP server (not crash)
    assert db.add.call_count == 1
    added = db.add.call_args[0][0]
    # Partial placeholder is kept as-is in the resolved env
    assert added.env["AUTH"] == "Bearer ${TOKEN}"


@pytest.mark.asyncio
async def test_uninstall_sync_failure_handled_gracefully():
    """If sync_mcp_servers fails during uninstall, it should not crash."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    # Make _read_config raise to simulate corrupt config during sync
    fs.read_text = AsyncMock(return_value="NOT VALID JSON {{{")
    fs.write_text = AsyncMock()

    # sync_mcp_servers should not raise on corrupt config
    await adapter.sync_mcp_servers(fs, [])
    fs.write_text.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_command_allowlist_rejects_shell():
    """MCP command allowlist should reject /bin/sh and similar."""
    from app.services.gene_service import _validate_mcp_command

    # Allowed commands
    _validate_mcp_command("node")
    _validate_mcp_command("python3")
    _validate_mcp_command("/usr/bin/node")
    _validate_mcp_command("npx")
    _validate_mcp_command("uvx")
    _validate_mcp_command("python")

    # Rejected commands
    import pytest as pt
    for cmd in ["/bin/sh", "sh", "bash", "/bin/bash", "curl", "wget", "nc"]:
        with pt.raises(ValueError, match="not in allowlist"):
            _validate_mcp_command(cmd)


@pytest.mark.asyncio
async def test_tool_allow_deny_list_skips_dangerous_tools():
    """tool_allow deny list should skip shell, computer, bash, exec, filesystem_write_file."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    fs.read_text = AsyncMock(return_value=json.dumps({"tools": {"allow": []}}))
    fs.write_text = AsyncMock()

    # Try to allow dangerous tools
    await adapter.allow_tools(fs, ["shell", "computer", "bash", "exec", "filesystem_write_file"])

    config = json.loads(fs.write_text.call_args[0][1])
    # None of the deny-listed tools should appear
    assert config["tools"]["allow"] == []


@pytest.mark.asyncio
async def test_tool_allow_permits_safe_tools():
    """Safe tools should be added to the allowlist."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    fs.read_text = AsyncMock(return_value=json.dumps({"tools": {"allow": []}}))
    fs.write_text = AsyncMock()

    await adapter.allow_tools(fs, ["nodeskclaw_blackboard", "nodeskclaw_proposals"])

    config = json.loads(fs.write_text.call_args[0][1])
    assert "nodeskclaw_blackboard" in config["tools"]["allow"]
    assert "nodeskclaw_proposals" in config["tools"]["allow"]


@pytest.mark.asyncio
async def test_deploy_scripts_rejects_path_traversal():
    """deploy_scripts should reject filenames with '..' or starting with '/'."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()

    import pytest as pt
    with pt.raises(ValueError, match="Path traversal"):
        await adapter.deploy_scripts(fs, {"../../../etc/passwd": "malicious"})

    with pt.raises(ValueError, match="Path traversal"):
        await adapter.deploy_scripts(fs, {"/etc/passwd": "malicious"})


def test_slug_regex_rejects_traversal():
    """Slug regex should reject path traversal attempts like '../../.ssh/keys'."""
    import re
    slug_pattern = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")

    # Valid slugs
    assert slug_pattern.match("social-media-browser")
    assert slug_pattern.match("media-generator")
    assert slug_pattern.match("my_gene_v2")

    # Invalid slugs (traversal / special chars)
    assert slug_pattern.match("../../.ssh/keys") is None
    assert slug_pattern.match("../etc/passwd") is None
    assert slug_pattern.match(".hidden") is None
    assert slug_pattern.match("-starts-dash") is None
    assert slug_pattern.match("UPPERCASE") is None
    assert slug_pattern.match("has spaces") is None
    assert slug_pattern.match("has/slash") is None


def test_error_redaction_catches_api_key_patterns():
    """_API_KEY_RE should match sk-xxx and similar patterns."""
    import re
    api_key_re = re.compile(r"(sk-[a-zA-Z0-9]{8,}|key-[a-zA-Z0-9]{8,}|Bearer\s+\S{8,})")

    # Should match: sk- followed by 8+ alphanumeric chars
    assert api_key_re.search("Error: sk-abcdefghij12345")
    assert api_key_re.search("key-abcdef12345678")
    assert api_key_re.search("Bearer eyJhbGciOiJSUzI1NiIs")

    # Should redact
    redacted = api_key_re.sub("[redacted]", "Auth failed: sk-abcdefghij12345 is invalid")
    assert "sk-abcdefghij" not in redacted
    assert "[redacted]" in redacted

    # Short patterns should NOT match (below 8 alphanumeric chars after prefix)
    assert api_key_re.search("sk-short") is None
    assert api_key_re.search("key-abc") is None
