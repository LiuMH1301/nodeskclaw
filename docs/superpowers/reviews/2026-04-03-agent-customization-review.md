# Agent Customization Plan -- Multi-Perspective Review

**Date:** 2026-04-03
**Plan reviewed:** `docs/superpowers/plans/2026-04-01-agent-customization.md` (original, pre-split)
**Verdict:** REVISE (plan restructured into 4 independent plans)

---

## Reviewers

| Reviewer | Role | Focus |
|----------|------|-------|
| Architect | Senior Software Architect | Architecture gaps, integration risks, race conditions, scalability |
| Security | Security Specialist | Credential management, SSRF, supply chain, input validation |
| Code Quality | Code Review Expert | Test coverage, mocks, duplication, error handling, immutability |
| Feasibility | Skeptical Senior Engineer | Scope, Playwright-in-K8s realities, DOM fragility, ops gaps |

---

## Blockers (100% failure on happy path)

### 1. `_inject_mcp_servers` is dead code
- **Found by:** Feasibility, confirmed by Architect
- `gene_service.py:1211` defines `_inject_mcp_servers()` but it is never called. `sync_mcp_servers` queries `InstanceMcpServer` rows that don't exist. Result: always writes `mcpServers: {}`.

### 2. `deploy_scripts` does not create subdirectories
- **Found by:** Architect, Feasibility
- `openclaw_gene_install_adapter.py:72-77` creates `.deskclaw/tools/` but not nested dirs like `social-media-browser/tools/`. Every MCP server gene fails to deploy.

### 3. Self-bootstrap `stdio: "inherit"` corrupts MCP protocol
- **Found by:** Feasibility
- `server.js:476` uses `execSync("npm install ...", { stdio: "inherit" })` which dumps npm output into the MCP stdio channel, corrupting JSON-RPC.

---

## Critical Issues

### 4. Unrestricted SSRF via URL parameters
- **Found by:** Security (CRITICAL, A10 SSRF)
- User-supplied URLs passed directly to `page.goto()` and `httpx.get()` with zero validation.

### 5. Session cookies stored as plaintext on PVC
- **Found by:** Security (CRITICAL, A02), Architect (MEDIUM)
- Cookie JSON files readable by any process with PVC access. Full account takeover risk.

### 6. Zero test coverage for 75% of new code
- **Found by:** Code Quality (CRITICAL)
- TDD applied to Tasks 1-3 only. Tasks 4-12 (~800 lines of Playwright and API code) have no tests.

---

## High Issues

| # | Finding | Found by |
|---|---------|----------|
| 7 | Supply chain attack -- no lockfiles, unpinned deps, `npm install` without integrity hashes | Security |
| 8 | No MCP server crash recovery -- Chromium crash = dead tool until pod restart | Architect, Feasibility |
| 9 | Uninstall leaves orphans -- MCP rows, tool_allow, deployed scripts never cleaned up | Architect, Feasibility |
| 10 | API key `${VAR}` syntax never resolved -- no interpolation mechanism exists | Architect, Feasibility |
| 11 | No server-side rate limiting -- posting rate limits are prose-only in SKILL.md | Security, Feasibility |
| 12 | Hardcoded CSS selectors fail silently -- returns empty results, indistinguishable from empty feed | Code Quality, Feasibility |
| 13 | Chromium memory -- real X.com pages hit 800MB-1.2GB; autoScroll has no memory check | Feasibility |
| 14 | Massive code duplication -- auth-check pattern copy-pasted 11 times across 3 files | Code Quality |
| 15 | Mutable state in browser-pool.js and provider registry -- violates project immutability rules | Code Quality |
| 16 | Test mocks bypass real interface -- raw AsyncMock instead of monkeypatch, no error path tests | Code Quality |

---

## Medium Issues

- `waitForTimeout` used as synchronization instead of DOM conditions
- API keys read at module load time (no rotation support)
- Error messages leak internal paths and stack traces
- `_save_path` collision risk (same-second calls overwrite)
- `pip install` into system Python may conflict with OpenClaw deps
- No cookie provisioning workflow or expiry detection
- `_deploy_gene_scripts` reads all files as text (binary files would corrupt)

---

## Resolution

The plan was restructured into 4 independent plans:

| Plan | Scope | Addresses |
|------|-------|-----------|
| **A: MCP Sync Foundation** | Adapter fixes, MCP sync, install/uninstall wiring | Blockers 1-2, High 9, 16 |
| **B: Social Media Browser** | Playwright MCP server with security hardening | Blocker 3, Critical 4-5, High 7-8, 11-15 |
| **C: Media Generator** | DALL-E/Runway MCP server | Critical 6 (partial), High 10 |
| **D: Behavioral Playbooks** | Pure markdown skill templates | None (no runtime code) |

Plans B and C depend on Plan A being shipped and verified first. Plan D is independent.
