# Agent Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable AI employees to use custom skills, automate social media via Playwright, and generate images/video via external APIs -- all packaged as genes with MCP servers.

**Architecture:** Each capability is a gene manifest containing a SKILL.md, MCP server definition, tool allow-list, and server scripts. The existing gene install pipeline deploys skills and scripts to the pod's PVC via `kubectl exec`. A new `sync_mcp_servers()` method bridges the gap between `InstanceMcpServer` DB records and the pod's `openclaw.json`.

**Tech Stack:** Python (FastAPI backend), Node.js (@modelcontextprotocol/sdk + Playwright), Python (mcp SDK + httpx)

**Spec:** `docs/superpowers/specs/2026-04-01-agent-customization-design.md`

---

## Plan Structure (Post-Review Split)

This plan was split into 4 independent plans after a multi-perspective review (architect, security, code quality, feasibility). The original monolithic plan had 3 blockers on the happy path that would have caused 100% failure on every gene install attempt.

| Plan | Scope | Status | Dependency |
|------|-------|--------|------------|
| **A: MCP Sync Foundation** (this document) | Tasks 1-7: adapter fixes, MCP sync, install/uninstall wiring | Active | None |
| **B: Social Media Browser** | MCP server + Playwright tools for X/Reddit/Substack ([plan](2026-04-03-social-media-browser.md)) | Follow-up | Plan A shipped & verified |
| **C: Media Generator** | MCP server + DALL-E/Runway providers ([plan](2026-04-03-media-generator.md)) | Follow-up | Plan A shipped & verified |
| **D: Behavioral Playbooks** | 3 skill-only gene manifests ([plan](2026-04-03-behavioral-playbooks.md)) | Follow-up | None (pure markdown) |

**Why split:** Plans B and C build on the foundation that Plan A establishes. Shipping them together means a bug in the foundation silently breaks everything above it, with no way to isolate the cause. Plan D has zero runtime dependencies and can ship independently at any time.

**Review findings addressed:** See `docs/superpowers/reviews/2026-04-03-agent-customization-review.md` for the full review synthesis.

---

## File Structure

### Plan A: MCP Sync Foundation

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py:58` | Add abstract `sync_mcp_servers()` method |
| Modify | `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py:92` | Implement `sync_mcp_servers()` |
| Modify | `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py:72-77` | Fix `deploy_scripts()` for nested subdirectories |
| Modify | `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py` | Add no-op `sync_mcp_servers()` + fix `deploy_scripts()` |
| Modify | `nodeskclaw-backend/app/services/gene_service.py:1272-1280` | Wire `_inject_mcp_servers()` + `sync_mcp_servers()` into install |
| Modify | `nodeskclaw-backend/app/services/gene_service.py:2219-2226` | Wire MCP cleanup + `sync_mcp_servers()` into uninstall |
| Create | `nodeskclaw-backend/tests/test_mcp_sync.py` | Unit + integration tests for MCP sync |

---

## Task 1: Fix `deploy_scripts()` for nested subdirectories

**Blocker found in review:** `deploy_scripts()` at `openclaw_gene_install_adapter.py:72-77` calls `fs.mkdir(self._scripts_dir)` once (creating `.deskclaw/tools/`) then writes files at paths like `social-media-browser/tools/x.js`. The intermediate directories (`social-media-browser/`, `social-media-browser/tools/`) are never created, causing a file-not-found error for every MCP server gene.

**Files:**
- Modify: `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py:72-77`
- Modify: `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py:40-45`
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Write the failing test**

Create `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py::test_deploy_scripts_creates_nested_directories -v`
Expected: FAIL -- `mkdir` is only called once with `.deskclaw/tools`, no nested dirs.

- [ ] **Step 3: Fix `deploy_scripts` in `OpenClawGeneInstallAdapter`**

In `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py`, replace lines 72-77:

```python
    async def deploy_scripts(self, fs: RemoteFS, scripts: dict[str, str]) -> None:
        if not scripts:
            return
        await fs.mkdir(self._scripts_dir)
        # Collect unique parent directories and create them
        parent_dirs: set[str] = set()
        for filename in scripts:
            parts = filename.split("/")
            for i in range(1, len(parts)):
                parent_dirs.add(f"{self._scripts_dir}/{'/'.join(parts[:i])}")
        for d in sorted(parent_dirs):
            await fs.mkdir(d)
        for filename, content in scripts.items():
            await fs.write_text(f"{self._scripts_dir}/{filename}", content)
```

- [ ] **Step 4: Apply same fix to `NoopGeneInstallAdapter`**

In `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py`, replace `deploy_scripts` (lines 40-45) with the same nested-directory logic using `SCRIPTS_DIR_REL`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py::test_deploy_scripts_creates_nested_directories -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py \
        nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "fix(gene): deploy_scripts 支持嵌套子目录创建"
```

---

## Task 2: Add `sync_mcp_servers()` to the abstract adapter

**Files:**
- Modify: `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py:58`
- Modify: `nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py`

- [ ] **Step 1: Write the failing test**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
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

In `nodeskclaw-backend/app/services/runtime/gene_install_adapter.py`, add after `post_remove_cleanup` (line 58):

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
        logger.debug("NoopGeneInstallAdapter.sync_mcp_servers: skipped (noop runtime)")
```

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-backend/app/services/runtime/gene_install_adapter.py \
        nodeskclaw-backend/app/services/runtime/noop_gene_install_adapter.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "refactor(gene): GeneInstallAdapter 新增 sync_mcp_servers 抽象方法"
```

---

## Task 3: Implement `sync_mcp_servers()` in `OpenClawGeneInstallAdapter`

**Files:**
- Modify: `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py`
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Implement `sync_mcp_servers`**

In `nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py`, add after `apply_config` (after line 92):

```python
    async def sync_mcp_servers(self, fs: RemoteFS, mcp_records: list) -> None:
        """Sync active InstanceMcpServer records into openclaw.json mcpServers section."""
        try:
            config = await self._read_config(fs)
        except ValueError:
            logger.warning("sync_mcp_servers: openclaw.json parse failed, skipping MCP sync")
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
                entry["args"] = list(rec.args)
            if rec.env:
                entry["env"] = dict(rec.env)
            mcp_servers[rec.name] = entry

        config = {**config, "mcpServers": mcp_servers}
        await self._write_config(fs, config)
```

Note: Uses `list(rec.args)` and `dict(rec.env)` to produce new objects (immutability). Uses spread to create a new config dict instead of mutating.

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
    # Existing config preserved
    assert config["skills"] == {}
```

- [ ] **Step 4: Write test for inactive filtering**

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

- [ ] **Step 5: Write test for ValueError error path**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
@pytest.mark.asyncio
async def test_sync_mcp_servers_skips_on_corrupt_config():
    """sync_mcp_servers should skip gracefully when openclaw.json is corrupt."""
    adapter = OpenClawGeneInstallAdapter()
    fs = AsyncMock()
    fs.read_text = AsyncMock(return_value="NOT VALID JSON {{{")
    fs.write_text = AsyncMock()

    mcp_records = [
        MagicMock(name="test", transport="stdio", command="node",
                  url=None, args=None, env=None, is_active=True),
    ]

    # Should not raise
    await adapter.sync_mcp_servers(fs, mcp_records)

    # Should not write anything
    fs.write_text.assert_not_called()
```

- [ ] **Step 6: Run all MCP sync tests**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add nodeskclaw-backend/app/services/runtime/openclaw_gene_install_adapter.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "feat(gene): OpenClawGeneInstallAdapter 实现 sync_mcp_servers"
```

---

## Task 4: Wire `_inject_mcp_servers()` into gene install

**Blocker found in review:** `_inject_mcp_servers()` at `gene_service.py:1211` is defined but **never called**. The plan's Task 3 (old plan) assumed MCP rows already exist in the DB, but nothing creates them. Result: `sync_mcp_servers` always writes `mcpServers: {}`.

**Files:**
- Modify: `nodeskclaw-backend/app/services/gene_service.py:1272-1280` (install path)
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Write the failing test**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
@pytest.mark.asyncio
async def test_inject_mcp_servers_creates_db_records(monkeypatch):
    """_inject_mcp_servers should create InstanceMcpServer rows from manifest."""
    from unittest.mock import patch
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
```

- [ ] **Step 2: Run test to verify it passes (function exists, just unused)**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py::test_inject_mcp_servers_creates_db_records -v`
Expected: PASS (the function is implemented, it's just never called from the install path)

- [ ] **Step 3: Wire `_inject_mcp_servers` and `sync_mcp_servers` into `_direct_install`**

In `nodeskclaw-backend/app/services/gene_service.py`, inside `_direct_install()`, after `_apply_manifest_actions` (around line 1279), add:

```python
                    await _apply_manifest_actions(fs, manifest, adapter)

                    # Wire MCP servers: create DB rows then sync to openclaw.json
                    mcp_defs = manifest.get("mcp_servers")
                    if mcp_defs:
                        await _inject_mcp_servers(db, instance_id, gene_id, mcp_defs)
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

Also add the required import near the top of `_direct_install` or at module level:

```python
from app.models.instance_mcp_server import InstanceMcpServer
```

- [ ] **Step 4: Run full test suite**

Run: `cd nodeskclaw-backend && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add nodeskclaw-backend/app/services/gene_service.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "feat(gene): 基因安装时调用 _inject_mcp_servers 创建 DB 记录并同步到 openclaw.json"
```

---

## Task 5: Wire MCP cleanup into gene uninstall

**Issue found in review:** `_direct_uninstall` at `gene_service.py:2219-2226` calls `remove_skill` and `post_remove_cleanup` but never:
1. Soft-deletes `InstanceMcpServer` rows for the uninstalled gene
2. Re-syncs `openclaw.json` (so stale MCP entries persist)
3. Removes deployed script files from the PVC

**Files:**
- Modify: `nodeskclaw-backend/app/services/gene_service.py:2219-2226` (uninstall path)
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Write the failing test**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
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
```

- [ ] **Step 2: Add MCP cleanup to `_direct_uninstall`**

In `nodeskclaw-backend/app/services/gene_service.py`, inside `_direct_uninstall()`, after `post_remove_cleanup` (around line 2226), add:

```python
                        await adapter.remove_skill(fs, skill_name)
                        await adapter.post_remove_cleanup(fs, skill_name)

                        # Soft-delete MCP server records for this gene
                        mcp_rows = await db.execute(
                            select(InstanceMcpServer).where(
                                InstanceMcpServer.instance_id == instance_id,
                                InstanceMcpServer.source_gene_id == gene_id,
                                not_deleted(InstanceMcpServer),
                            )
                        )
                        for mcp_row in mcp_rows.scalars().all():
                            mcp_row.soft_delete()

                        # Re-sync remaining active MCP servers to openclaw.json
                        remaining_mcp = await db.execute(
                            select(InstanceMcpServer).where(
                                InstanceMcpServer.instance_id == instance_id,
                                InstanceMcpServer.is_active.is_(True),
                                not_deleted(InstanceMcpServer),
                            )
                        )
                        await adapter.sync_mcp_servers(fs, list(remaining_mcp.scalars().all()))
```

- [ ] **Step 3: Run full test suite**

Run: `cd nodeskclaw-backend && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add nodeskclaw-backend/app/services/gene_service.py \
        nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "feat(gene): 基因卸载时软删除 MCP Server 记录并重新同步 openclaw.json"
```

---

## Task 6: Integration test -- full install-to-config round-trip

**Issue found in review:** All previous tests use bare `AsyncMock()` for `fs`, which never validates the read-modify-write cycle against realistic data. Need at least one test that verifies the full flow: existing config is preserved, MCP servers are injected correctly, and the resulting `openclaw.json` is structurally valid.

**Files:**
- Test: `nodeskclaw-backend/tests/test_mcp_sync.py`

- [ ] **Step 1: Write round-trip integration test**

Add to `nodeskclaw-backend/tests/test_mcp_sync.py`:

```python
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
```

- [ ] **Step 2: Run all tests**

Run: `cd nodeskclaw-backend && uv run pytest tests/test_mcp_sync.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/tests/test_mcp_sync.py
git commit -m "test(gene): MCP sync 集成测试 -- 完整安装/卸载往返验证"
```

---

## Task 7: Run full suite, ruff check, and verify

- [ ] **Step 1: Run full backend test suite**

Run: `cd nodeskclaw-backend && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run ruff on modified files**

Run: `cd nodeskclaw-backend && uv run ruff check app/services/runtime/openclaw_gene_install_adapter.py app/services/runtime/gene_install_adapter.py app/services/runtime/noop_gene_install_adapter.py app/services/gene_service.py`
Expected: No errors

- [ ] **Step 3: Verify no import cycles**

Run: `cd nodeskclaw-backend && uv run python -c "from app.services.gene_service import _inject_mcp_servers; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "chore(gene): Plan A 最终验证和修复"
```

---

## Follow-up Plans

### Plan B: Social Media Browser MCP Server

**Prerequisite:** Plan A shipped and verified end-to-end (install a test gene with `mcp_servers` in manifest, confirm `openclaw.json` is updated).

**Key changes from original plan (based on review):**

1. **No self-bootstrap** -- Bake Playwright + Chromium into the pod image via a Docker layer or init container. Remove all `execSync("npm install")` / `npx playwright install` code. Ship a `package-lock.json` with pinned hashes and use `npm ci` if any install step remains.

2. **URL allowlisting (SSRF protection)** -- Create a `ALLOWED_DOMAINS` config per platform. Validate all user-supplied URLs (`tweet_url`, `post_url`) against scheme (`https:` only) and hostname allowlist before passing to `page.goto()`.

3. **Cookie encryption at rest** -- Encrypt cookie JSON files on PVC using a per-instance key stored in a K8s Secret. Validate cookie file integrity with HMAC before loading. Add cookie expiry checking beyond the login-redirect heuristic.

4. **Extract selectors into config + health-check tool** -- Move all hardcoded CSS selectors (`data-testid="tweet"`, `#siteTable .thing.link`, etc.) into a `SELECTORS` config object per platform. Add a `social_media_health_check` tool that verifies expected DOM structure exists. When zero elements are found on a successfully-loaded page, return `{"warning": "selector_mismatch"}` instead of empty results.

5. **Deduplicate auth pattern** -- Extract `withAuthenticatedPage(pool, platform, loginPatterns, fn)` helper to eliminate the 11x copy-pasted auth-check-then-invalidate block.

6. **Server-side rate limiting** -- Implement token-bucket rate limiter in the MCP server for write operations (post, reply, like). SKILL.md prose is not enforcement.

7. **Chromium resource limits** -- Launch with `--disable-dev-shm-usage`, `--js-flags="--max-old-space-size=512"`. Replace `waitForTimeout()` with `waitForSelector()` / `waitForResponse()`.

8. **Error sanitization** -- Don't return raw `err.message` to the agent. Wrap in structured error objects that omit internal paths and stack traces.

9. **Test coverage** -- Unit tests for `browser-pool.js` (cookie loading, context caching, auth redirect detection), handler dispatch, and each platform tool with mocked Playwright pages.

### Plan C: Media Generator MCP Server

**Prerequisite:** Plan A shipped and verified.

**Key changes from original plan (based on review):**

1. **API key injection mechanism** -- Design how `${OPENAI_API_KEY}` in gene manifest env is resolved to actual values. Options: (a) resolve at sync time from instance-level secret storage, (b) use K8s Secrets mounted as files, (c) read from a `.env` file on the PVC. Do NOT store cleartext keys in the DB or `openclaw.json`.

2. **Read keys at call time, not import time** -- Move `os.environ.get("OPENAI_API_KEY")` into method calls for rotation support.

3. **Fix `_save_path` collision** -- Add random bytes: `hashlib.sha256((ts + os.urandom(8).hex()).encode())`.

4. **Lockfile with hashes** -- Pin all deps in `requirements.txt` with `--require-hashes`.

5. **Use `--target` or venv** for pip install to avoid system Python conflicts.

6. **SSRF protection on `image_url`** -- Validate URL scheme and domain before `httpx.get()`.

7. **Test coverage** -- Provider tests with httpx mocks for `openai_images.py` and `runway_video.py`.

### Plan D: Behavioral Playbooks

**Prerequisite:** None (pure markdown, no runtime dependencies).

**No changes from original plan.** Create 3 gene manifests (skill-only, no `mcp_servers` or `scripts`) and 3 SKILL.md files:
- `trend-scout-playbook`
- `industry-researcher-playbook`
- `copywriter-playbook`

Can be implemented and shipped independently at any time.

---

## Changelog (Review-Driven Revisions)

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-03 | Split into 4 independent plans (A/B/C/D) | Scope too large; blockers in foundation would silently break everything above |
| 2026-04-03 | Added Task 1: Fix `deploy_scripts` for nested dirs | **BLOCKER**: No MCP server gene could deploy (missing intermediate directories) |
| 2026-04-03 | Added Task 4: Wire `_inject_mcp_servers()` into install | **BLOCKER**: Function was dead code; MCP DB rows never created |
| 2026-04-03 | Added Task 5: Wire MCP cleanup into uninstall | **HIGH**: Uninstall left orphaned MCP server rows and stale openclaw.json entries |
| 2026-04-03 | Added Task 6: Integration test round-trip | **HIGH**: Original tests used raw AsyncMock, never validated read-modify-write cycle |
| 2026-04-03 | Added ValueError error path test (Task 3 Step 5) | **HIGH**: Original tests never tested the corrupt-config error branch |
| 2026-04-03 | Used immutable patterns in `sync_mcp_servers` | **HIGH**: Original used mutation; project rules require immutability |
| 2026-04-03 | Plan B: Replaced self-bootstrap with pre-built layer | **BLOCKER**: `stdio: "inherit"` corrupts MCP JSON-RPC protocol |
| 2026-04-03 | Plan B: Added URL allowlisting | **CRITICAL**: SSRF via unvalidated user URLs |
| 2026-04-03 | Plan B: Added cookie encryption at rest | **CRITICAL**: Plaintext session cookies on PVC = full account takeover risk |
| 2026-04-03 | Plan B: Extracted selectors into config | **CRITICAL**: Hardcoded selectors fail silently when platforms change DOM |
| 2026-04-03 | Plan B: Added server-side rate limiting | **HIGH**: Prose-only rate limits have no enforcement |
| 2026-04-03 | Plan C: Designed API key injection mechanism | **HIGH**: `${VAR}` syntax never resolved; literal strings written to config |
