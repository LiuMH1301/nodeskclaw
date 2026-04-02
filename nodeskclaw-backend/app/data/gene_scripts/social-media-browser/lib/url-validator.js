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
  const domainToPlatform = new Map();
  const platformDomains = new Map();

  for (const p of platforms) {
    platformDomains.set(p.platform, p.domains);
    for (const domain of p.domains) {
      domainToPlatform.set(domain, p.platform);
    }
  }

  const allAllowed = new Set(domainToPlatform.keys());

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

    const domains = platform ? platformDomains.get(platform) : null;
    if (platform && !domains) {
      return { valid: false, error: "unknown_platform", message: `Unknown platform: ${platform}` };
    }

    const checkSet = domains ? new Set(domains) : allAllowed;
    if (!checkSet.has(parsed.hostname)) {
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
      throw result;
    }
    return result.url;
  }

  return { validateUrl, requireValidUrl };
}
