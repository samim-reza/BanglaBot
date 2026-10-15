/** Static copy for the public website — re-exported from lib/site/ so existing imports keep working.
 *
 * Plan and add-on numbers mirror backend/app/core/plans.py and addons.py — change both together.
 * The product name always comes from BRAND (lib/brand.ts).
 */

export * from "./site/types";
export * from "./site/nav";
export * from "./site/agents";
export * from "./site/platform";
export * from "./site/pricing";
export * from "./site/addons";
export * from "./site/comparison";
export * from "./site/faqs";
export * from "./site/contact";
