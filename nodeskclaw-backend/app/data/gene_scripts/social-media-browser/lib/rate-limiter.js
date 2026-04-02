/**
 * Server-side token-bucket rate limiter factory for write operations.
 * Enforces hard limits that SKILL.md prose cannot bypass.
 *
 * Usage:
 *   const limiter = createRateLimiter(platforms);
 *   limiter.checkRateLimit("x_post_tweet");
 *
 * Adding a platform: No changes needed here. The new platform module
 * exports its `rateLimits` map, and server.js passes all platforms
 * to this factory at startup.
 */

export function createRateLimiter(platforms) {
  // Merge all platform rate limits into a single limits map
  const limits = {};
  for (const p of platforms) {
    if (p.rateLimits) {
      Object.assign(limits, p.rateLimits);
    }
  }

  // Note: buckets require mutable state for token tracking.
  // This is an intentional exception to the immutability rule.
  const buckets = new Map();

  function getBucket(action) {
    if (!limits[action]) return null;

    if (!buckets.has(action)) {
      const limit = limits[action];
      buckets.set(action, {
        tokens: limit.tokens,
        max: limit.tokens,
        refillPerHour: limit.refillPerHour,
        lastRefill: Date.now(),
      });
    }

    const bucket = buckets.get(action);
    const now = Date.now();
    const elapsed = (now - bucket.lastRefill) / (1000 * 60 * 60);
    const refill = elapsed * bucket.refillPerHour;
    const updated = {
      ...bucket,
      tokens: Math.min(bucket.max, bucket.tokens + refill),
      lastRefill: now,
    };
    buckets.set(action, updated);
    return updated;
  }

  function checkRateLimit(action) {
    const bucket = getBucket(action);
    if (!bucket) return { allowed: true };

    if (bucket.tokens < 1) {
      const waitMinutes = Math.ceil((1 - bucket.tokens) / (bucket.refillPerHour / 60));
      return {
        allowed: false,
        error: "rate_limited",
        action,
        message: `Rate limit exceeded for ${action}. Try again in ~${waitMinutes} minutes.`,
        retryAfterMinutes: waitMinutes,
      };
    }

    buckets.set(action, { ...bucket, tokens: bucket.tokens - 1 });
    return { allowed: true, remainingTokens: Math.floor(bucket.tokens - 1) };
  }

  return { checkRateLimit };
}
