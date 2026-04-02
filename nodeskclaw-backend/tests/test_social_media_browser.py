"""Tests for social-media-browser gene: manifest validity, SKILL.md, and Node.js unit tests."""

import json
import subprocess
from pathlib import Path

import pytest

MANIFESTS_DIR = Path(__file__).parent.parent / "app/data/gene_manifests"
SKILLS_DIR = Path(__file__).parent.parent / "app/data/gene_skills"
SCRIPTS_DIR = Path(__file__).parent.parent / "app/data/gene_scripts"


class TestManifest:
    """Gene manifest structure and file reference tests."""

    def test_manifest_exists_and_valid(self):
        manifest_path = MANIFESTS_DIR / "social-media-browser.json"
        assert manifest_path.exists(), "Manifest file not found"
        manifest = json.loads(manifest_path.read_text())

        assert manifest["skill"]["name"] == "social-media-browser"
        assert "description" in manifest["skill"]
        assert len(manifest["tool_allow"]) == 10
        assert len(manifest["mcp_servers"]) == 1
        assert manifest["mcp_servers"][0]["transport"] == "stdio"
        assert manifest["mcp_servers"][0]["command"] == "node"

    def test_all_scripts_exist(self):
        manifest_path = MANIFESTS_DIR / "social-media-browser.json"
        manifest = json.loads(manifest_path.read_text())

        for script in manifest["scripts"]:
            script_path = SCRIPTS_DIR / script
            assert script_path.exists(), f"Script not found: {script}"

    def test_tool_allow_matches_platform_tools(self):
        manifest_path = MANIFESTS_DIR / "social-media-browser.json"
        manifest = json.loads(manifest_path.read_text())
        tool_names = set(manifest["tool_allow"])

        expected_tools = {
            "x_scan_timeline",
            "x_scan_profile",
            "x_post_tweet",
            "x_reply",
            "x_like",
            "reddit_scan_subreddit",
            "reddit_post",
            "reddit_reply",
            "substack_publish",
            "substack_scan_feed",
        }
        assert tool_names == expected_tools


class TestSkillMd:
    """SKILL.md content and structure tests."""

    def test_skill_md_exists_and_has_frontmatter(self):
        skill_path = SKILLS_DIR / "social-media-browser.md"
        assert skill_path.exists(), "SKILL.md not found"
        content = skill_path.read_text()
        assert content.startswith("---"), "Missing YAML frontmatter"
        assert "name: social-media-browser" in content

    def test_skill_md_documents_rate_limits(self):
        skill_path = SKILLS_DIR / "social-media-browser.md"
        content = skill_path.read_text()
        assert "Rate Limit" in content
        assert "x_post_tweet" in content
        assert "reddit_post" in content
        assert "substack_publish" in content

    def test_skill_md_has_workflow_and_what_not_to_do(self):
        skill_path = SKILLS_DIR / "social-media-browser.md"
        content = skill_path.read_text()
        assert "## Workflow" in content
        assert "## What NOT to Do" in content


class TestNodejsUnitTests:
    """Run Node.js unit tests for url-validator and rate-limiter via subprocess."""

    def test_nodejs_unit_tests(self):
        scripts_dir = SCRIPTS_DIR / "social-media-browser"
        result = subprocess.run(
            ["node", "--test", "test/url-validator.test.js", "test/rate-limiter.test.js"],
            cwd=scripts_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Node.js tests failed:\n{result.stdout}\n{result.stderr}"
        )
