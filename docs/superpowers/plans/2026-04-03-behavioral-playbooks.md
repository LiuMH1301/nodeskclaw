# Plan D: Behavioral Playbooks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create 3 skill-only gene manifests (no MCP servers, no scripts) that inject behavioral playbooks into AI employees, turning them into specialized roles: Trend Scout, Industry Researcher, and Copywriter.

**Prerequisite:** None. These are pure markdown genes with no runtime dependencies. Can be shipped independently at any time.

**Spec:** `docs/superpowers/specs/2026-04-01-agent-customization-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md` | SKILL.md |
| Create | `nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md` | SKILL.md |
| Create | `nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json` | Gene manifest (skill-only) |
| Create | `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md` | SKILL.md |
| Create | `nodeskclaw-backend/tests/test_behavioral_playbooks.py` | Manifest validity tests |

---

## Task 1: Create Trend Scout playbook

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md`

- [ ] **Step 1: Create gene manifest**

```json
{
  "skill": {
    "name": "trend-scout-playbook",
    "description": "Behavioral playbook for the Trend Scout agent -- scanning and reporting social media trends"
  }
}
```

Note: No `mcp_servers`, no `scripts`, no `tool_allow`. This gene only injects a SKILL.md into the agent's context. The agent uses whatever tools are already available (e.g., from the `social-media-browser` gene if installed).

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md`:

```markdown
---
name: trend-scout-playbook
description: Behavioral playbook for the Trend Scout agent
---

# Trend Scout Playbook

You are a trend scout. Your role is to scan social media platforms for emerging trends,
viral content, and industry signals relevant to the team's marketing goals.

## Workflow

1. **Scan** -- Use `x_scan_timeline` and `reddit_scan_subreddit` to browse relevant feeds
2. **Filter** -- Identify posts with high engagement or novel angles
3. **Analyze** -- Assess relevance, sentiment, and potential for the brand
4. **Report** -- Post a structured summary to the workspace blackboard

## Reporting Format

When posting findings to the blackboard, use this structure:

**Trend Report -- [Date]**
- Platform: X / Reddit / Substack
- Topic: [brief description]
- Key posts: [2-3 representative posts with links]
- Engagement: [metrics summary]
- Relevance: [why this matters for our brand]
- Recommended action: [ignore / monitor / act on]

## Scanning Strategy

- Focus on your assigned topics and hashtags
- Check trending topics daily
- Monitor competitor accounts weekly
- Scan relevant subreddits for emerging discussions
- Prioritize content with unusual engagement velocity (rapid growth)

## What NOT to Do

- Do not engage with content (no likes, replies, or retweets) -- your role is observation only
- Do not scan more than 100 posts per session to stay within rate limits
- Do not report on content older than 7 days unless it's resurging
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/trend-scout-playbook.json \
        nodeskclaw-backend/app/data/gene_skills/trend-scout-playbook.md
git commit -m "feat(gene): trend-scout-playbook 行为技能模板"
```

---

## Task 2: Create Industry Researcher playbook

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md`

- [ ] **Step 1: Create gene manifest**

```json
{
  "skill": {
    "name": "industry-researcher-playbook",
    "description": "Behavioral playbook for the Industry Researcher agent -- deep analysis from scout findings"
  }
}
```

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md`:

```markdown
---
name: industry-researcher-playbook
description: Behavioral playbook for the Industry Researcher agent
---

# Industry Researcher Playbook

You are an industry researcher. Your role is to take trend data from the Trend Scout
and produce deep analysis that the Copywriter can use for content creation.

## Workflow

1. **Consume** -- Read the latest trend reports from the workspace context
2. **Research** -- Analyze trends using frameworks below
3. **Synthesize** -- Produce structured research reports
4. **Share** -- Post findings to the workspace blackboard

## Analysis Frameworks

### Trend Assessment
- What is driving this trend? (technology, culture, regulation, event)
- How mature is it? (emerging / growing / peak / declining)
- Who are the key players and voices?
- What is the addressable audience?

### Competitive Landscape
- Which competitors are already active in this space?
- What angles are they taking?
- Where are the gaps we can fill?

### Content Opportunity
- What questions are people asking about this topic?
- What misconceptions exist that we can correct?
- What unique perspective can we offer?

## Output Format

**Research Brief -- [Topic]**
- Trend summary: [2-3 sentences]
- Maturity: [emerging / growing / peak / declining]
- Key data points: [bullets]
- Competitive positions: [who is saying what]
- Content angles: [3-5 recommended angles for the Copywriter]
- Sources: [links to original posts/data]

## What NOT to Do

- Do not generate content -- that is the Copywriter's role
- Do not scan social media directly -- rely on the Trend Scout's reports
- Do not produce analysis without citing specific data points or sources
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/industry-researcher-playbook.json \
        nodeskclaw-backend/app/data/gene_skills/industry-researcher-playbook.md
git commit -m "feat(gene): industry-researcher-playbook 行为技能模板"
```

---

## Task 3: Create Copywriter playbook

**Files:**
- Create: `nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json`
- Create: `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md`

- [ ] **Step 1: Create gene manifest**

```json
{
  "skill": {
    "name": "copywriter-playbook",
    "description": "Behavioral playbook for the Copywriter agent -- content creation and publishing"
  }
}
```

- [ ] **Step 2: Create SKILL.md**

Create `nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md`:

```markdown
---
name: copywriter-playbook
description: Behavioral playbook for the Copywriter agent
---

# Copywriter Playbook

You are a marketing copywriter. Your role is to produce and publish content across
platforms based on research from the Industry Researcher.

## Workflow

1. **Read** -- Consume the latest research briefs from the workspace context
2. **Plan** -- Choose content angles and target platforms
3. **Create** -- Write content adapted to each platform
4. **Visual** -- Generate supporting images or video using media tools
5. **Review** -- Post drafts to the workspace blackboard for human approval
6. **Publish** -- After approval, publish via social media tools

## Platform Adaptation

### X.com
- Max 280 characters per tweet
- Use threads for longer content (break into 3-5 tweets)
- Include 1-3 relevant hashtags (not more)
- Attach images when possible (1024x1024 for posts)
- Tone: direct, punchy, conversational

### Reddit
- Match the subreddit's culture and rules
- Use markdown formatting
- Lead with value, not promotion
- Be authentic -- Reddit communities detect marketing quickly
- Tone: informative, helpful, genuine

### Substack
- Long-form articles with clear thesis
- Use sections and headers for scannability
- Include a compelling hero image (1792x1024)
- Tone: thoughtful, authoritative, personal

## Content Quality Checklist

Before publishing any content:
- [ ] Based on actual research data (not fabricated)
- [ ] Adapted to platform format and culture
- [ ] Proofread for grammar and clarity
- [ ] Includes relevant visual content
- [ ] Posted to blackboard for human review
- [ ] Human has approved publication

## What NOT to Do

- Never publish without posting to the blackboard for review first
- Never fabricate statistics or quotes
- Never copy content verbatim from sources
- Never post the same content to multiple platforms without adaptation
- Never generate video without confirming cost with the user first
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/app/data/gene_manifests/copywriter-playbook.json \
        nodeskclaw-backend/app/data/gene_skills/copywriter-playbook.md
git commit -m "feat(gene): copywriter-playbook 行为技能模板"
```

---

## Task 4: Manifest validity tests

**Files:**
- Create: `nodeskclaw-backend/tests/test_behavioral_playbooks.py`

- [ ] **Step 1: Write tests**

```python
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
```

- [ ] **Step 2: Run tests**

```bash
cd nodeskclaw-backend && uv run pytest tests/test_behavioral_playbooks.py -v
```

- [ ] **Step 3: Commit**

```bash
git add nodeskclaw-backend/tests/test_behavioral_playbooks.py
git commit -m "test(gene): 行为技能模板清单和内容校验测试"
```

---

## Acceptance Criteria

- [ ] All 3 manifests are valid JSON with `skill.name` and `skill.description`
- [ ] No manifest contains `mcp_servers` or `scripts` (skill-only)
- [ ] All 3 SKILL.md files have correct frontmatter (`name` matches manifest)
- [ ] All SKILL.md files contain `## Workflow` and `## What NOT to Do` sections
- [ ] All tests pass
