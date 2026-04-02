/**
 * URL allowlisting factory to prevent SSRF attacks.
 * Only HTTPS URLs on registered platform domains are permitted.
 *
 * Usage:
 *   const validator = createUrlValidator(platforms);
 *   validator.requireValidUrl("https://x.com/home", "x");
 *
 * Adding a platform: No changes needed here. The new platform module
 * exports its `domains` array, and server.js passes all platforms to
 * this factory at startup.
 */

export function createUrlValidator(platforms) {
  // Build domain -> platform lookup from platform configs
  // Supports both exact domain match and subdomain suffix match (*.substack.com)
  const domainToPlatform = new Map();
  const platformDomains = new Map();

  for (const p of platforms) {
    platformDomains.set(p.platform, p.domains);
    for (const domain of p.domains) {
      domainToPlatform.set(domain, p.platform);
    }
  }

  const allDomains = [...domainToPlatform.keys()];

  function matchesDomain(hostname, domains) {
    for (const d of domains) {
      if (hostname === d || hostname.endsWith(`.${d}`)) {
        return true;
      }
    }
    return false;
  }

  function validateUrl(url, platform = null) {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return { valid: false, error: "invalid_url", message: `Cannot parse URL: ${url}` };
    }

    if (parsed.protocol !== "https:") {
      return { valid: false, error: "invalid_protocol", message: "Only HTTPS URLs are allowed." };
    }

    // Reject userinfo in URL (e.g. https://x.com@evil.com/)
    if (parsed.username || parsed.password) {
      return { valid: false, error: "invalid_url", message: "URLs with credentials are not allowed." };
    }

    const domains = platform ? platformDomains.get(platform) : null;
    if (platform && !domains) {
      return { valid: false, error: "unknown_platform", message: `Unknown platform: ${platform}` };
    }

    const checkDomains = domains || allDomains;
    if (!matchesDomain(parsed.hostname, checkDomains)) {
      return {
        valid: false,
        error: "domain_not_allowed",
        message: `Domain ${parsed.hostname} is not in the allowlist for ${platform || "any platform"}.`,
      };
    }

    return { valid: true, url: parsed.href };
  }

  function requireValidUrl(url, platform = null) {
    const result = validateUrl(url, platform);
    if (!result.valid) {
      const err = new Error(result.message);
      err.code = result.error;
      throw err;
    }
    return result.url;
  }

  return { validateUrl, requireValidUrl };
}
