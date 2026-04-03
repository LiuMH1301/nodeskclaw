/**
 * Substack platform module.
 * substack_publish saves as DRAFT only (safety measure).
 *
 * Tools: substack_scan_feed, substack_publish
 */

import { withAuthenticatedPage, navigateWithAuthCheck } from "../lib/with-page.js";
import { checkSelectorHealth } from "../lib/selector-health.js";

const PLATFORM = "substack";

const SELECTORS = {
  inboxItem: '[class*="post-preview"], [class*="inbox-item"]',
  inboxTitle: "a",
  inboxAuthor: '[class*="author"], [class*="pub-name"]',
  inboxTime: "time",
  newPostLink: 'a[href*="/publish/post"]',
  titleInput: '[placeholder*="Title"], .post-title',
  subtitleInput: '[placeholder*="subtitle"], .post-subtitle',
  editor: '.ProseMirror, [contenteditable="true"]',
};

const LOGIN_PATTERNS = ["/sign-in", "/account/login"];

export default {
  platform: PLATFORM,

  domains: ["substack.com"],

  loginPatterns: LOGIN_PATTERNS,

  selectors: SELECTORS,

  rateLimits: {
    substack_publish: { tokens: 2, refillPerHour: 2 },
  },

  tools: [
    {
      name: "substack_scan_feed",
      description: "Scan recent posts from a Substack publication's feed.",
      inputSchema: {
        type: "object",
        properties: {
          publication_url: { type: "string", description: "Full URL of the Substack publication." },
          count: { type: "number", description: "Number of posts (default 10).", default: 10 },
        },
        required: ["publication_url"],
      },
    },
    {
      name: "substack_publish",
      description: "Create a draft post on Substack (saves as draft, does NOT publish). Requires human approval to publish.",
      inputSchema: {
        type: "object",
        properties: {
          title: { type: "string", description: "Post title." },
          subtitle: { type: "string", description: "Post subtitle (optional)." },
          body: { type: "string", description: "Post body (plain text or markdown)." },
        },
        required: ["title", "body"],
      },
    },
  ],

  async handle(pool, toolName, args, { urlValidator }) {
    return withAuthenticatedPage(pool, PLATFORM, LOGIN_PATTERNS, async (page) => {
      switch (toolName) {
        case "substack_scan_feed":
          return await scanFeed(pool, page, args, urlValidator);
        case "substack_publish":
          return await publishDraft(pool, page, args, urlValidator);
        default:
          return { error: "unknown_tool", tool: toolName };
      }
    });
  },
};

// --- Tool implementations (private to this module) ---

async function scanFeed(pool, page, { publication_url, count = 10 }, urlValidator) {
  urlValidator.requireValidUrl(publication_url, "substack");

  const authErr = await navigateWithAuthCheck(page, publication_url, pool, PLATFORM, LOGIN_PATTERNS, { urlValidator });
  if (authErr) return authErr;

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const items = document.querySelectorAll(sel.inboxItem);
      return Array.from(items).slice(0, maxCount).map((item) => {
        const titleEl = item.querySelector(sel.inboxTitle);
        const authorEl = item.querySelector(sel.inboxAuthor);
        const timeEl = item.querySelector(sel.inboxTime);

        return {
          title: titleEl?.innerText || "",
          url: titleEl?.href || "",
          author: authorEl?.innerText || "",
          time: timeEl?.getAttribute("datetime") || timeEl?.innerText || "",
        };
      });
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { publication_url, posts, count: posts.length };
}

async function publishDraft(pool, page, { title, subtitle, body }, urlValidator) {
  if (!title) {
    return { error: "invalid_input", message: "Post title is required." };
  }

  if (!body || body.length > 100_000) {
    return { error: "invalid_input", message: "Post body must be 1-100000 characters." };
  }

  // Navigate to the new post page via the Substack dashboard
  const dashboardUrl = "https://substack.com/publish/post";
  const authErr = await navigateWithAuthCheck(page, dashboardUrl, pool, PLATFORM, LOGIN_PATTERNS, { urlValidator });
  if (authErr) return authErr;

  // Fill in the title
  const titleInput = page.locator(SELECTORS.titleInput).first();
  await titleInput.waitFor({ state: "visible", timeout: 10_000 });
  await titleInput.click();
  await titleInput.fill(title);

  // Fill in the subtitle if provided
  if (subtitle) {
    const subtitleInput = page.locator(SELECTORS.subtitleInput).first();
    const subtitleCount = await subtitleInput.count();
    if (subtitleCount > 0) {
      await subtitleInput.click();
      await subtitleInput.fill(subtitle);
    }
  }

  // Fill in the body using the ProseMirror editor
  const editor = page.locator(SELECTORS.editor).first();
  await editor.waitFor({ state: "visible", timeout: 10_000 });
  await editor.click();

  // Type body content line by line to preserve paragraph structure
  const lines = body.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) {
      await page.keyboard.press("Enter");
    }
    if (lines[i]) {
      await page.keyboard.type(lines[i], { delay: 10 });
    }
  }

  // Substack auto-saves drafts. Wait for the "Saved" or "Draft" indicator.
  // Look for indicators that the draft has been saved.
  await page.waitForTimeout(3000);

  // Verify draft was saved by checking for draft-related UI elements
  const savedIndicator = await page.evaluate(() => {
    const body = document.body.innerText;
    return body.includes("Draft") || body.includes("Saved") || body.includes("draft");
  });

  if (savedIndicator) {
    return {
      success: true,
      draft: true,
      title,
      subtitle: subtitle || null,
      message: "Post saved as draft. Please review and publish manually from the Substack dashboard.",
    };
  }

  return {
    success: true,
    draft: true,
    title,
    subtitle: subtitle || null,
    message: "Draft content entered. Substack auto-saves drafts -- please verify in the dashboard.",
  };
}
