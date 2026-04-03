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


@pytest.mark.asyncio
async def test_inject_mcp_servers_no_env_dict():
    """Servers without env dict should still be created with empty env."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mcp_servers = [
        {
            "name": "no-env-server",
            "transport": "stdio",
            "command": "python",
        },
    ]

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers, {"FOO": "bar"})

    added_obj = db.add.call_args[0][0]
    assert added_obj.env == {}


@pytest.mark.asyncio
async def test_inject_mcp_servers_none_instance_env():
    """When instance_env is None, placeholders should resolve to empty strings."""
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
            "env": {"API_KEY": "${API_KEY}"},
        },
    ]

    await _inject_mcp_servers(db, "inst-123", "gene-456", mcp_servers, None)

    added_obj = db.add.call_args[0][0]
    assert added_obj.env["API_KEY"] == ""


@pytest.mark.asyncio
async def test_inject_mcp_servers_does_not_mutate_input():
    """Original mcp_servers dicts must not be mutated."""
    from app.services.gene_service import _inject_mcp_servers

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    original_env = {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "STATIC": "hello",
    }
    mcp_servers = [
        {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "env": original_env,
        },
    ]

    await _inject_mcp_servers(
        db, "inst-123", "gene-456", mcp_servers,
        {"OPENAI_API_KEY": "sk-resolved"},
    )

    # Original dict must be untouched
    assert original_env["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert original_env["STATIC"] == "hello"
