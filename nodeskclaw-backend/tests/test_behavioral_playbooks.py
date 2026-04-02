"""Tests for behavioral playbook gene manifests."""

import json
from pathlib import Path

import pytest

MANIFESTS_DIR = Path(__file__).parent.parent / "app/data/gene_manifests"
SKILLS_DIR = Path(__file__).parent.parent / "app/data/gene_skills"

PLAYBOOKS = [
    "trend-scout-playbook",
    "industry-researcher-playbook",
    "copywriter-playbook",
]


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_manifest_exists_and_valid(name):
    """Each playbook should have a valid JSON manifest."""
    manifest_path = MANIFESTS_DIR / f"{name}.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["skill"]["name"] == name
    assert "description" in manifest["skill"]
    # Skill-only genes should NOT have mcp_servers or scripts
    assert "mcp_servers" not in manifest
    assert "scripts" not in manifest


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_skill_md_exists_and_has_frontmatter(name):
    """Each playbook should have a SKILL.md with correct frontmatter."""
    skill_path = SKILLS_DIR / f"{name}.md"
    assert skill_path.exists(), f"SKILL.md not found: {skill_path}"
    content = skill_path.read_text()
    assert content.startswith("---"), "SKILL.md must start with frontmatter"
    assert f"name: {name}" in content


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_skill_md_has_workflow_section(name):
    """Each playbook should have a Workflow section."""
    skill_path = SKILLS_DIR / f"{name}.md"
    content = skill_path.read_text()
    assert "## Workflow" in content


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_skill_md_has_what_not_to_do(name):
    """Each playbook should have a 'What NOT to Do' section."""
    skill_path = SKILLS_DIR / f"{name}.md"
    content = skill_path.read_text()
    assert "## What NOT to Do" in content
