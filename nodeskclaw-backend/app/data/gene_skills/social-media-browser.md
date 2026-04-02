---
name: social-media-browser
description: Browser-based social media tools for X.com, Reddit, and Substack
---

# Social Media Browser

You have access to browser-based tools for interacting with social media platforms.
These tools use Playwright to automate a real Chromium browser with your session cookies.

## Available Platforms

- **X.com** (Twitter): scan timelines, scan profiles, post tweets, reply, like
- **Reddit**: scan subreddits, post, reply
- **Substack**: scan feeds, create draft posts

## Authentication

Tools use pre-exported session cookies. If you see an `auth_expired` error:
1. Report to the user that cookies need refreshing
2. Do NOT retry the same action -- it will fail again
3. Wait for the user to export fresh cookies

## Rate Limits (server-enforced)

Write operations have hard rate limits enforced server-side. These cannot be bypassed.

| Action | Limit | Refill |
|--------|-------|--------|
| x_post_tweet | 5/hour | 5/hour |
| x_reply | 5/hour | 5/hour |
| x_like | 20/hour | 60/hour |
| reddit_post | 3/hour | 3/hour |
| reddit_reply | 10/hour | 10/hour |
| substack_publish | 2/hour | 2/hour |

If you receive a `rate_limited` error, wait the indicated time before retrying.

## DOM Selector Warnings

If you receive a `selector_mismatch` warning, it means the platform may have changed
its page layout. Report this to the user -- the selectors in the platform module
may need updating. The data returned may be empty or incomplete.

## Workflow

1. **Scan** -- Use scan tools to browse feeds and profiles (read-only, no rate limit)
2. **Analyze** -- Process the returned data for your task
3. **Act** -- Use write tools (post, reply, like) when needed
4. **Report** -- Summarize what you did to the workspace blackboard

## What NOT to Do

- Do not retry failed auth -- report to the user instead
- Do not exceed 100 posts per scan session (use the `count` parameter)
- Do not post identical content across platforms without adaptation
- Do not ignore rate limit errors -- respect the retry time
- Do not use these tools for content older than 7 days unless specifically asked
