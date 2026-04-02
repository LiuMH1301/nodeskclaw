import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

// Allowlist safe Chromium flags to prevent sandbox bypass via env injection
const SAFE_CHROMIUM_ARGS = new Set([
  "--disable-dev-shm-usage",
  "--disable-gpu",
  "--disable-software-rasterizer",
  "--disable-extensions",
]);
const CHROMIUM_ARGS = (process.env.PLAYWRIGHT_CHROMIUM_ARGS || "")
  .split(" ")
  .filter((arg) => SAFE_CHROMIUM_ARGS.has(arg));

/**
 * Manages one persistent browser context per platform.
 * Cookies are loaded from JSON files at context creation time.
 * Platform-agnostic -- works with any platform identifier.
 */
export function createBrowserPool(cookiesPath) {
  let browser = null;
  // Note: browser pool requires mutable state for connection management.
  // This is an intentional exception to the immutability rule.
  const contexts = new Map();

  async function ensureBrowser() {
    if (!browser || !browser.isConnected()) {
      browser = await chromium.launch({
        headless: true,
        args: [
          "--disable-dev-shm-usage",
          "--disable-gpu",
          "--js-flags=--max-old-space-size=512",
          // Block navigation to cloud metadata / internal IPs at Chromium level
          "--host-resolver-rules=MAP 169.254.169.254 ~NOTFOUND, MAP 0.0.0.0 ~NOTFOUND",
          ...CHROMIUM_ARGS,
        ],
      });
    }
    return browser;
  }

  function cookieFilePath(platform) {
    if (!/^[a-z][a-z0-9_]{0,30}$/.test(platform)) {
      throw new Error(`Invalid platform identifier`);
    }
    const filePath = path.resolve(cookiesPath, `${platform}.json`);
    if (!filePath.startsWith(path.resolve(cookiesPath))) {
      throw new Error("Invalid cookie path");
    }
    return filePath;
  }

  function loadCookies(platform) {
    const filePath = cookieFilePath(platform);
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async function getContext(platform) {
    if (contexts.has(platform)) {
      return contexts.get(platform);
    }

    const b = await ensureBrowser();
    const cookies = loadCookies(platform);
    if (!cookies) {
      throw {
        error: "cookies_not_found",
        platform,
        message: `No cookie file found for platform "${platform}". Please export cookies and place the file.`,
      };
    }

    const context = await b.newContext({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    });
    await context.addCookies(cookies);
    contexts.set(platform, context);
    return context;
  }

  async function invalidateContext(platform) {
    const ctx = contexts.get(platform);
    if (ctx) {
      await ctx.close();
      contexts.delete(platform);
    }
  }

  async function closeAll() {
    for (const [, ctx] of contexts) {
      await ctx.close();
    }
    contexts.clear();
    if (browser) {
      await browser.close();
      browser = null;
    }
  }

  function checkAuthRedirect(page, platform, loginUrlPatterns) {
    const url = page.url();
    for (const pattern of loginUrlPatterns) {
      if (url.includes(pattern)) {
        return {
          error: "auth_expired",
          platform,
          message: `Session cookies expired for ${platform}. Please export fresh cookies.`,
        };
      }
    }
    return null;
  }

  return { getContext, invalidateContext, closeAll, checkAuthRedirect };
}
