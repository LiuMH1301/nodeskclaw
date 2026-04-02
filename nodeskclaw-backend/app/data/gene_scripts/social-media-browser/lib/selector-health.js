/**
 * DOM selector health check utility.
 * Each platform module defines its own selectors object.
 * This utility verifies that selectors still match the live DOM.
 *
 * When a selector breaks, update it in the PLATFORM MODULE --
 * all tool functions in that module pick up the change automatically.
 */

export async function checkSelectorHealth(page, selectors, minExpected = 1) {
  const primarySelector = Object.values(selectors)[0];
  if (!primarySelector) return null;

  const count = await page.locator(primarySelector).count();
  if (count < minExpected) {
    return {
      warning: "selector_mismatch",
      selector: primarySelector,
      found: count,
      expected: `>=${minExpected}`,
      message: "DOM selectors may be outdated. Platform may have changed its layout.",
    };
  }
  return null;
}
