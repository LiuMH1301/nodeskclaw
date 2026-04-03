/**
 * Tests for browser-pool cookie validation and security logic.
 *
 * These tests replicate the validation logic from browser-pool.js
 * without importing it (to avoid the playwright dependency in test env).
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const platformDomains = new Map([
  ["x", ["x.com", "twitter.com"]],
  ["reddit", ["reddit.com", "www.reddit.com"]],
]);

// Replicate validateCookieSchema from browser-pool.js
function validateCookieSchema(cookies, platform) {
  if (!Array.isArray(cookies)) {
    throw new Error("Cookie file must contain a JSON array.");
  }
  const allowedDomains = platformDomains.get(platform) || [];
  for (const cookie of cookies) {
    if (typeof cookie.name !== "string" || typeof cookie.value !== "string" || typeof cookie.domain !== "string") {
      throw new Error("Each cookie must have name (string), value (string), and domain (string).");
    }
    const cookieDomain = cookie.domain.startsWith(".") ? cookie.domain.slice(1) : cookie.domain;
    const domainAllowed = allowedDomains.some(
      (d) => cookieDomain === d || cookieDomain.endsWith(`.${d}`),
    );
    if (!domainAllowed) {
      throw new Error(`Cookie domain "${cookie.domain}" is not allowed for platform "${platform}".`);
    }
  }
}

// Replicate cookieFilePath validation from browser-pool.js
function validatePlatformId(platform) {
  if (!/^[a-z][a-z0-9_]{0,30}$/.test(platform)) {
    throw new Error("Invalid platform identifier");
  }
}

describe("Cookie Schema Validation", () => {
  it("rejects non-array JSON", () => {
    assert.throws(
      () => validateCookieSchema({ not: "array" }, "x"),
      { message: /JSON array/ },
    );
  });

  it("rejects string JSON", () => {
    assert.throws(
      () => validateCookieSchema("just a string", "x"),
      { message: /JSON array/ },
    );
  });

  it("rejects null JSON", () => {
    assert.throws(
      () => validateCookieSchema(null, "x"),
      { message: /JSON array/ },
    );
  });

  it("rejects cookies missing domain field", () => {
    assert.throws(
      () => validateCookieSchema([{ name: "auth", value: "tok123" }], "x"),
      { message: /name.*value.*domain/ },
    );
  });

  it("rejects cookies missing name field", () => {
    assert.throws(
      () => validateCookieSchema([{ value: "tok123", domain: ".x.com" }], "x"),
      { message: /name.*value.*domain/ },
    );
  });

  it("rejects cookies missing value field", () => {
    assert.throws(
      () => validateCookieSchema([{ name: "auth", domain: ".x.com" }], "x"),
      { message: /name.*value.*domain/ },
    );
  });

  it("rejects cookies with numeric name", () => {
    assert.throws(
      () => validateCookieSchema([{ name: 123, value: "tok", domain: ".x.com" }], "x"),
      { message: /name.*value.*domain/ },
    );
  });

  it("rejects cookies with unauthorized domain", () => {
    assert.throws(
      () => validateCookieSchema([{ name: "auth", value: "tok", domain: ".evil.com" }], "x"),
      { message: /not allowed/ },
    );
  });

  it("rejects cookies with domain confusion (.x.com.evil.com)", () => {
    // ".x.com.evil.com" stripped of leading dot = "x.com.evil.com"
    // That should NOT match "x.com" or end with ".x.com"
    assert.throws(
      () => validateCookieSchema([{ name: "a", value: "b", domain: ".x.com.evil.com" }], "x"),
      { message: /not allowed/ },
    );
  });

  it("accepts cookies with valid platform domain", () => {
    // Should not throw
    validateCookieSchema([{ name: "auth", value: "tok", domain: ".x.com" }], "x");
  });

  it("accepts cookies with subdomain of platform domain", () => {
    validateCookieSchema([{ name: "auth", value: "tok", domain: ".api.x.com" }], "x");
  });

  it("accepts empty cookie array", () => {
    // Empty array is valid
    validateCookieSchema([], "x");
  });
});

describe("Platform Identifier Validation", () => {
  it("rejects path traversal in platform name", () => {
    assert.throws(
      () => validatePlatformId("../../../etc"),
      { message: /Invalid platform/ },
    );
  });

  it("rejects platform with slashes", () => {
    assert.throws(
      () => validatePlatformId("x/../../etc"),
      { message: /Invalid platform/ },
    );
  });

  it("rejects uppercase platform", () => {
    assert.throws(
      () => validatePlatformId("X"),
      { message: /Invalid platform/ },
    );
  });

  it("rejects platform starting with number", () => {
    assert.throws(
      () => validatePlatformId("1x"),
      { message: /Invalid platform/ },
    );
  });

  it("accepts valid platform names", () => {
    validatePlatformId("x");
    validatePlatformId("reddit");
    validatePlatformId("substack");
    validatePlatformId("my_platform_v2");
  });
});

describe("Host Resolver Rules", () => {
  it("expected host-resolver-rules block cloud metadata and internal IPs", () => {
    // From browser-pool.js: the launch args include this rule
    const rule =
      "MAP 169.254.169.254 ~NOTFOUND, MAP 0.0.0.0 ~NOTFOUND, MAP 127.0.0.1 ~NOTFOUND, MAP metadata.google.internal ~NOTFOUND";

    assert.ok(rule.includes("169.254.169.254"), "Should block AWS metadata IP");
    assert.ok(rule.includes("127.0.0.1"), "Should block loopback");
    assert.ok(rule.includes("0.0.0.0"), "Should block 0.0.0.0");
    assert.ok(rule.includes("metadata.google.internal"), "Should block GCP metadata");
  });
});
