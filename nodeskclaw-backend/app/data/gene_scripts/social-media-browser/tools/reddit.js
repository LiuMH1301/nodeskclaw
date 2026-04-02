/**
 * Reddit platform module.
 * Uses old.reddit.com for simpler, more stable DOM selectors.
 *
 * Tools: reddit_scan_subreddit, reddit_post, reddit_reply
 */

import { withAuthenticatedPage, navigateWithAuthCheck } from "../lib/with-page.js";
import { checkSelectorHealth } from "../lib/selector-health.js";

const PLATFORM = "reddit";

const SELECTORS = {
  post: "#siteTable .thing.link",
  postTitle: "a.title",
  postScore: ".score.unvoted",
  postComments: ".comments",
  postTime: "time",
  titleInput: 'textarea[name="title"]',
  textTab: 'li.tabmenu-li a:text("text")',
  bodyInput: 'textarea[name="text"]',
  submitButton: 'button[name="submit"]',
  commentBox: ".usertext-edit textarea",
  commentSubmit: '.usertext-edit button[type="submit"]',
};

const LOGIN_PATTERNS = ["/login", "/account/login"];

const SUBREDDIT_PATTERN = /^[a-zA-Z0-9_]{1,21}$/;

export default {
  platform: PLATFORM,

  domains: [
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "new.reddit.com", "np.reddit.com",
  ],

  loginPatterns: LOGIN_PATTERNS,

  selectors: SELECTORS,

  rateLimits: {
    reddit_post: { tokens: 3, refillPerHour: 3 },
    reddit_reply: { tokens: 10, refillPerHour: 10 },
  },

  tools: [
    {
      name: "reddit_scan_subreddit",
      description: "Scan posts from a subreddit on Reddit.",
      inputSchema: {
        type: "object",
        properties: {
          subreddit: { type: "string", description: "Subreddit name without r/." },
          sort: { type: "string", enum: ["hot", "new", "top"], default: "hot" },
          count: { type: "number", description: "Number of posts (default 20).", default: 20 },
        },
        required: ["subreddit"],
      },
    },
    {
      name: "reddit_post",
      description: "Submit a text post to a subreddit.",
      inputSchema: {
        type: "object",
        properties: {
          subreddit: { type: "string", description: "Subreddit name without r/." },
          title: { type: "string", description: "Post title." },
          body: { type: "string", description: "Post body (markdown)." },
        },
        required: ["subreddit", "title", "body"],
      },
    },
    {
      name: "reddit_reply",
      description: "Reply to a Reddit post or comment.",
      inputSchema: {
        type: "object",
        properties: {
          post_url: { type: "string", description: "Full URL of the post to reply to." },
          text: { type: "string", description: "Reply text (markdown)." },
        },
        required: ["post_url", "text"],
      },
    },
  ],

  async handle(pool, toolName, args, { urlValidator }) {
    return withAuthenticatedPage(pool, PLATFORM, LOGIN_PATTERNS, async (page) => {
      switch (toolName) {
        case "reddit_scan_subreddit":
          return await scanSubreddit(pool, page, args);
        case "reddit_post":
          return await submitPost(pool, page, args);
        case "reddit_reply":
          return await replyToPost(pool, page, args, urlValidator);
        default:
          return { error: "unknown_tool", tool: toolName };
      }
    });
  },
};

// --- Tool implementations (private to this module) ---

async function scanSubreddit(pool, page, { subreddit, sort = "hot", count = 20 }) {
  if (!SUBREDDIT_PATTERN.test(subreddit)) {
    return {
      error: "invalid_subreddit",
      message: "Subreddit name must be 1-21 alphanumeric characters or underscores.",
    };
  }

  const sortPath = sort === "hot" ? "" : `/${sort}`;
  const url = `https://old.reddit.com/r/${subreddit}${sortPath}`;
  const authErr = await navigateWithAuthCheck(page, url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const things = document.querySelectorAll(sel.post);
      return Array.from(things).slice(0, maxCount).map((thing) => {
        const titleEl = thing.querySelector(sel.postTitle);
        const scoreEl = thing.querySelector(sel.postScore);
        const commentsEl = thing.querySelector(sel.postComments);
        const timeEl = thing.querySelector(sel.postTime);

        return {
          title: titleEl?.innerText || "",
          url: titleEl?.href || "",
          score: scoreEl?.innerText || "0",
          comments: commentsEl?.innerText?.match(/\d+/)?.[0] || "0",
          time: timeEl?.getAttribute("datetime") || "",
          author: thing.getAttribute("data-author") || "",
        };
      });
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { subreddit, sort, posts, count: posts.length };
}

async function submitPost(pool, page, { subreddit, title, body }) {
  if (!SUBREDDIT_PATTERN.test(subreddit)) {
    return {
      error: "invalid_subreddit",
      message: "Subreddit name must be 1-21 alphanumeric characters or underscores.",
    };
  }

  if (!title || title.length > 300) {
    return { error: "invalid_input", message: "Post title must be 1-300 characters." };
  }

  if (!body) {
    return { error: "invalid_input", message: "Post body is required." };
  }

  const url = `https://old.reddit.com/r/${subreddit}/submit`;
  const authErr = await navigateWithAuthCheck(page, url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  // Click the "text" tab to ensure we are on the self-post form
  const textTab = page.locator('a').filter({ hasText: 'text' }).first();
  const textTabCount = await textTab.count();
  if (textTabCount > 0) {
    await textTab.click();
    await page.waitForTimeout(500);
  }

  // Fill in the title
  const titleInput = page.locator(SELECTORS.titleInput);
  await titleInput.waitFor({ state: "visible", timeout: 10_000 });
  await titleInput.fill(title);

  // Fill in the body
  const bodyInput = page.locator(SELECTORS.bodyInput);
  await bodyInput.waitFor({ state: "visible", timeout: 10_000 });
  await bodyInput.fill(body);

  // Submit
  const submitBtn = page.locator(SELECTORS.submitButton);
  await submitBtn.click();

  // Wait for navigation to the new post (URL changes from /submit to /comments/)
  await page.waitForURL(/\/comments\//, { timeout: 15_000 }).catch(() => {});

  const finalUrl = page.url();
  const submitted = finalUrl.includes("/comments/");

  return submitted
    ? { success: true, subreddit, title, url: finalUrl }
    : { error: "submit_uncertain", message: "Post may not have been submitted. Please verify manually.", subreddit, title };
}

async function replyToPost(pool, page, { post_url, text }, urlValidator) {
  urlValidator.requireValidUrl(post_url, "reddit");

  if (!text) {
    return { error: "invalid_input", message: "Reply text is required." };
  }

  // Convert to old.reddit.com for stable DOM
  const oldRedditUrl = post_url
    .replace("www.reddit.com", "old.reddit.com")
    .replace("new.reddit.com", "old.reddit.com")
    .replace(/^(https:\/\/)reddit\.com/, "$1old.reddit.com");

  const authErr = await navigateWithAuthCheck(page, oldRedditUrl, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  // Find the comment box at the top of the thread
  const commentBox = page.locator(SELECTORS.commentBox).first();
  await commentBox.waitFor({ state: "visible", timeout: 10_000 });
  await commentBox.fill(text);

  // Submit the comment
  const submitBtn = page.locator(SELECTORS.commentSubmit).first();
  await submitBtn.click();

  // Wait for the new comment to appear in the DOM
  await page.waitForSelector('.comment .usertext-body', { timeout: 10_000 }).catch(() => {});

  return { success: true, post_url, text };
}
