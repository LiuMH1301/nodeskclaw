import dns from "node:dns";

const PRIVATE_IP_PREFIXES = ["10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.", "127.", "0."];

function isPrivateIp(ip) {
  return PRIVATE_IP_PREFIXES.some((prefix) => ip.startsWith(prefix));
}

async function dnsPreResolve(hostname) {
  try {
    const addresses = await dns.promises.resolve4(hostname);
    for (const addr of addresses) {
      if (isPrivateIp(addr)) {
        throw new Error(`DNS resolved to private IP (${addr}) -- potential SSRF.`);
      }
    }
  } catch (err) {
    if (err.code === "ENOTFOUND" || err.code === "ENODATA") {
      return;
    }
    throw err;
  }
}

/**
 * Shared page lifecycle: open page, check auth, execute action, close page.
 * Eliminates the copy-pasted auth-check-then-invalidate pattern.
 * Platform-agnostic -- works with any platform module.
 */

export async function withAuthenticatedPage(pool, platform, loginPatterns, fn) {
  const context = await pool.getContext(platform);
  const page = await context.newPage();

  try {
    const result = await fn(page);

    const authError = pool.checkAuthRedirect(page, platform, loginPatterns);
    if (authError) {
      await pool.invalidateContext(platform);
      return authError;
    }

    return result;
  } catch (err) {
    return {
      error: "tool_error",
      platform,
      message: err.message
        ? err.message.replace(/\/[^\s]+/g, "[path]").slice(0, 200)
        : "Unknown error",
    };
  } finally {
    await page.close();
  }
}

/**
 * Navigate to a URL with auth check immediately after load.
 * Returns null if auth is valid, or an auth_expired error object.
 * @param {object} options - Optional settings
 * @param {object} options.urlValidator - URL validator instance for redirect checking
 */
export async function navigateWithAuthCheck(page, url, pool, platform, loginPatterns, { urlValidator } = {}) {
  // DNS pre-resolve: reject hostnames that resolve to private IPs
  try {
    const parsed = new URL(url);
    await dnsPreResolve(parsed.hostname);
  } catch (err) {
    return {
      error: "ssrf_blocked",
      platform,
      message: err.message.replace(/\/[^\s]+/g, "[path]").slice(0, 200),
    };
  }

  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });

  // Verify final URL after redirects is still on an allowed domain
  const finalUrl = page.url();
  if (urlValidator) {
    try {
      urlValidator.requireValidUrl(finalUrl, platform);
    } catch {
      return {
        error: "redirect_to_disallowed_domain",
        platform,
        message: "Navigation redirected to disallowed domain.",
      };
    }
  } else {
    try {
      const parsedFinal = new URL(finalUrl);
      const originalParsed = new URL(url);
      if (parsedFinal.hostname !== originalParsed.hostname &&
          !parsedFinal.hostname.endsWith(`.${originalParsed.hostname}`)) {
        return {
          error: "redirect_to_disallowed_domain",
          platform,
          message: "Navigation redirected to disallowed domain.",
        };
      }
    } catch {
      return {
        error: "redirect_to_disallowed_domain",
        platform,
        message: "Navigation resulted in an unparseable URL.",
      };
    }
  }

  const authError = pool.checkAuthRedirect(page, platform, loginPatterns);
  if (authError) {
    await pool.invalidateContext(platform);
    return authError;
  }
  return null;
}
