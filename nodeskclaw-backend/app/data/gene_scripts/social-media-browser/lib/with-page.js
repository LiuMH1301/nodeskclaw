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
 */
export async function navigateWithAuthCheck(page, url, pool, platform, loginPatterns) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });

  // Verify final URL after redirects is still on an allowed domain
  const finalUrl = page.url();
  try {
    const parsed = new URL(finalUrl);
    const originalParsed = new URL(url);
    if (parsed.hostname !== originalParsed.hostname &&
        !parsed.hostname.endsWith(`.${originalParsed.hostname}`)) {
      return {
        error: "redirect_to_disallowed_domain",
        platform,
        message: `Navigation redirected to disallowed domain.`,
      };
    }
  } catch {
    // URL parsing failure on final URL -- treat as suspicious
    return {
      error: "redirect_to_disallowed_domain",
      platform,
      message: "Navigation resulted in an unparseable URL.",
    };
  }

  const authError = pool.checkAuthRedirect(page, platform, loginPatterns);
  if (authError) {
    await pool.invalidateContext(platform);
    return authError;
  }
  return null;
}
