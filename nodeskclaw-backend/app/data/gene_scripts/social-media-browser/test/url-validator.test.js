import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createUrlValidator } from "../lib/url-validator.js";

const platforms = [
  { platform: "x", domains: ["x.com", "twitter.com"] },
  { platform: "reddit", domains: ["reddit.com", "www.reddit.com"] },
  { platform: "substack", domains: ["substack.com"] },
];

const { validateUrl, requireValidUrl } = createUrlValidator(platforms);

describe("URL Validator", () => {
  it("accepts valid X.com URL", () => {
    const result = validateUrl("https://x.com/home", "x");
    assert.equal(result.valid, true);
    assert.equal(result.url, "https://x.com/home");
  });

  it("accepts valid Reddit URL", () => {
    const result = validateUrl("https://www.reddit.com/r/programming", "reddit");
    assert.equal(result.valid, true);
  });

  it("rejects HTTP URLs", () => {
    const result = validateUrl("http://x.com/home", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "invalid_protocol");
  });

  it("rejects non-allowlisted domains", () => {
    const result = validateUrl("https://evil.com/phish", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "domain_not_allowed");
  });

  it("rejects internal IPs (SSRF protection)", () => {
    const result = validateUrl("https://169.254.169.254/metadata");
    assert.equal(result.valid, false);
    assert.equal(result.error, "domain_not_allowed");
  });

  it("rejects cross-platform URLs", () => {
    const result = validateUrl("https://x.com/home", "reddit");
    assert.equal(result.valid, false);
    assert.equal(result.error, "domain_not_allowed");
  });

  it("accepts subdomain URLs (e.g. newsletter.substack.com)", () => {
    const result = validateUrl("https://newsletter.substack.com/archive", "substack");
    assert.equal(result.valid, true);
  });

  it("rejects URLs with userinfo (credential bypass)", () => {
    const result = validateUrl("https://user:pass@x.com/home", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "invalid_url");
  });

  it("requireValidUrl throws Error instance on invalid URL", () => {
    assert.throws(
      () => requireValidUrl("http://x.com", "x"),
      (err) => err instanceof Error && err.code === "invalid_protocol",
    );
  });

  it("rejects unparseable URLs", () => {
    const result = validateUrl("not-a-url", "x");
    assert.equal(result.valid, false);
    assert.equal(result.error, "invalid_url");
  });

  it("rejects unknown platform", () => {
    const result = validateUrl("https://medium.com/article", "medium");
    assert.equal(result.valid, false);
    assert.equal(result.error, "unknown_platform");
  });
});
