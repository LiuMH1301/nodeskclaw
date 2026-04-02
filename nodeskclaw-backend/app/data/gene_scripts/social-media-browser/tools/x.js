/**
 * X.com (Twitter) platform module.
 *
 * To add a new platform, copy this file's structure:
 * 1. Export default with: platform, domains, loginPatterns, selectors, rateLimits, tools, handle
 * 2. Place in tools/<platform>.js
 * 3. Add tool names to gene manifest's tool_allow
 * That's it -- server.js auto-discovers this file.
 */

import { withAuthenticatedPage, navigateWithAuthCheck } from "../lib/with-page.js";
import { checkSelectorHealth } from "../lib/selector-health.js";

const PLATFORM = "x";

const SELECTORS = {
  tweet: 'article[data-testid="tweet"]',
  tweetText: '[data-testid="tweetText"]',
  userName: '[data-testid="User-Name"]',
  time: "time",
  statusLink: 'a[href*="/status/"]',
  composeEditor: '[data-testid="tweetTextarea_0"]',
  postButton: '[data-testid="tweetButtonInline"]',
  likeButton: '[data-testid="like"]',
  alreadyLiked: '[data-testid="unlike"]',
};

const LOGIN_PATTERNS = ["/i/flow/login", "/login"];

export default {
  platform: PLATFORM,

  domains: ["x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com"],

  loginPatterns: LOGIN_PATTERNS,

  selectors: SELECTORS,

  rateLimits: {
    x_post_tweet: { tokens: 5, refillPerHour: 5 },
    x_like: { tokens: 20, refillPerHour: 60 },
    x_reply: { tokens: 5, refillPerHour: 5 },
  },

  tools: [
    {
      name: "x_scan_timeline",
      description: "Scan X.com home timeline or search results. Returns posts with text and engagement metrics.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query. Omit for home timeline." },
          count: { type: "number", description: "Number of posts to return (default 20).", default: 20 },
        },
      },
    },
    {
      name: "x_scan_profile",
      description: "Scan a user's recent posts on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          username: { type: "string", description: "X username without @." },
          count: { type: "number", description: "Number of posts to return (default 10).", default: 10 },
        },
        required: ["username"],
      },
    },
    {
      name: "x_post_tweet",
      description: "Post a tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          text: { type: "string", description: "Tweet text (max 280 characters).", maxLength: 280 },
        },
        required: ["text"],
      },
    },
    {
      name: "x_reply",
      description: "Reply to a specific tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          tweet_url: { type: "string", description: "Full URL of the tweet to reply to." },
          text: { type: "string", description: "Reply text.", maxLength: 280 },
        },
        required: ["tweet_url", "text"],
      },
    },
    {
      name: "x_like",
      description: "Like a tweet on X.com.",
      inputSchema: {
        type: "object",
        properties: {
          tweet_url: { type: "string", description: "Full URL of the tweet to like." },
        },
        required: ["tweet_url"],
      },
    },
  ],

  async handle(pool, toolName, args, { urlValidator }) {
    return withAuthenticatedPage(pool, PLATFORM, LOGIN_PATTERNS, async (page) => {
      switch (toolName) {
        case "x_scan_timeline":
          return await scanTimeline(pool, page, args, urlValidator);
        case "x_scan_profile":
          return await scanProfile(pool, page, args, urlValidator);
        case "x_post_tweet":
          return await postTweet(pool, page, args);
        case "x_reply":
          return await replyToTweet(pool, page, args, urlValidator);
        case "x_like":
          return await likeTweet(pool, page, args, urlValidator);
        default:
          return { error: "unknown_tool", tool: toolName };
      }
    });
  },
};

// --- Tool implementations (private to this module) ---

const MAX_SCAN_COUNT = 100;

async function scanTimeline(pool, page, { query, count = 20 }, urlValidator) {
  count = Math.min(Math.max(1, count), MAX_SCAN_COUNT);
  const url = query
    ? `https://x.com/search?q=${encodeURIComponent(query)}&f=live`
    : "https://x.com/home";
  const authErr = await navigateWithAuthCheck(page, url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  await autoScroll(page, count);

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const articles = document.querySelectorAll(sel.tweet);
      return Array.from(articles).slice(0, maxCount).map((article) => ({
        text: article.querySelector(sel.tweetText)?.innerText || "",
        author: article.querySelector(sel.userName)?.innerText?.split("\n")?.[0] || "",
        handle: article.querySelector(sel.userName)?.innerText?.split("\n")?.[1] || "",
        time: article.querySelector(sel.time)?.getAttribute("datetime") || "",
        url: (() => {
          const link = article.querySelector(sel.statusLink);
          return link ? `https://x.com${link.getAttribute("href")}` : "";
        })(),
      }));
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { posts, count: posts.length };
}

async function scanProfile(pool, page, { username, count = 10 }, urlValidator) {
  count = Math.min(Math.max(1, count), MAX_SCAN_COUNT);
  if (!/^[a-zA-Z0-9_]{1,15}$/.test(username)) {
    return { error: "invalid_username", message: "Username must be 1-15 alphanumeric characters." };
  }

  const authErr = await navigateWithAuthCheck(
    page, `https://x.com/${username}`, pool, PLATFORM, LOGIN_PATTERNS,
  );
  if (authErr) return authErr;

  await autoScroll(page, count);

  const health = await checkSelectorHealth(page, SELECTORS);
  if (health) return { ...health, posts: [], count: 0 };

  const posts = await page.evaluate(
    ({ sel, maxCount }) => {
      const articles = document.querySelectorAll(sel.tweet);
      return Array.from(articles).slice(0, maxCount).map((article) => ({
        text: article.querySelector(sel.tweetText)?.innerText || "",
        time: article.querySelector(sel.time)?.getAttribute("datetime") || "",
        url: (() => {
          const link = article.querySelector(sel.statusLink);
          return link ? `https://x.com${link.getAttribute("href")}` : "";
        })(),
      }));
    },
    { sel: SELECTORS, maxCount: count },
  );

  return { posts, count: posts.length };
}

async function postTweet(pool, page, { text }) {
  if (!text || text.length > 280) {
    return { error: "invalid_input", message: "Tweet text must be 1-280 characters." };
  }

  const authErr = await navigateWithAuthCheck(
    page, "https://x.com/compose/post", pool, PLATFORM, LOGIN_PATTERNS,
  );
  if (authErr) return authErr;

  const editor = page.locator(SELECTORS.composeEditor);
  await editor.waitFor({ state: "visible", timeout: 10_000 });
  await editor.click();
  await editor.fill(text);
  await page.locator(SELECTORS.postButton).click();
  await editor.waitFor({ state: "detached", timeout: 10_000 }).catch(() => {});

  return { success: true, text };
}

async function replyToTweet(pool, page, { tweet_url, text }, urlValidator) {
  urlValidator.requireValidUrl(tweet_url, "x");
  if (!text || text.length > 280) {
    return { error: "invalid_input", message: "Reply text must be 1-280 characters." };
  }

  const authErr = await navigateWithAuthCheck(page, tweet_url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  const replyBox = page.locator(SELECTORS.composeEditor);
  await replyBox.waitFor({ state: "visible", timeout: 10_000 });
  await replyBox.click();
  await replyBox.fill(text);
  await page.locator(SELECTORS.postButton).click();
  await replyBox.waitFor({ state: "detached", timeout: 10_000 }).catch(() => {});

  return { success: true, tweet_url, text };
}

async function likeTweet(pool, page, { tweet_url }, urlValidator) {
  urlValidator.requireValidUrl(tweet_url, "x");

  const authErr = await navigateWithAuthCheck(page, tweet_url, pool, PLATFORM, LOGIN_PATTERNS);
  if (authErr) return authErr;

  const likeButton = page.locator(SELECTORS.likeButton);
  if ((await likeButton.count()) > 0) {
    await likeButton.click();
    return { success: true, tweet_url, action: "liked" };
  }

  return { success: true, tweet_url, action: "already_liked" };
}

async function autoScroll(page, targetCount) {
  let previousHeight = 0;
  for (let attempt = 0; attempt < 10; attempt++) {
    const articles = await page.locator(SELECTORS.tweet).count();
    if (articles >= targetCount) break;
    await page.evaluate(() => window.scrollBy(0, window.innerHeight));
    await page.waitForFunction(
      (prevH) => document.body.scrollHeight > prevH,
      previousHeight,
      { timeout: 5_000 },
    ).catch(() => {});
    const currentHeight = await page.evaluate(() => document.body.scrollHeight);
    if (currentHeight === previousHeight) break;
    previousHeight = currentHeight;
  }
}
