import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createRateLimiter } from "../lib/rate-limiter.js";

describe("Rate Limiter", () => {
  it("allows requests within budget", () => {
    const limiter = createRateLimiter([
      { platform: "x", rateLimits: { x_post_tweet: { tokens: 3, refillPerHour: 3 } } },
    ]);

    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
  });

  it("blocks requests over budget", () => {
    const limiter = createRateLimiter([
      { platform: "x", rateLimits: { x_post_tweet: { tokens: 2, refillPerHour: 2 } } },
    ]);

    limiter.checkRateLimit("x_post_tweet");
    limiter.checkRateLimit("x_post_tweet");
    const result = limiter.checkRateLimit("x_post_tweet");
    assert.equal(result.allowed, false);
    assert.equal(result.error, "rate_limited");
    assert.ok(result.retryAfterMinutes > 0);
  });

  it("allows unknown actions (no limit configured)", () => {
    const limiter = createRateLimiter([]);
    assert.equal(limiter.checkRateLimit("unknown_action").allowed, true);
  });

  it("merges rate limits from multiple platforms", () => {
    const limiter = createRateLimiter([
      { platform: "x", rateLimits: { x_post_tweet: { tokens: 1, refillPerHour: 1 } } },
      { platform: "reddit", rateLimits: { reddit_post: { tokens: 1, refillPerHour: 1 } } },
    ]);

    assert.equal(limiter.checkRateLimit("x_post_tweet").allowed, true);
    assert.equal(limiter.checkRateLimit("reddit_post").allowed, true);
  });
});
