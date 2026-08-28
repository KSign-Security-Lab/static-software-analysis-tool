/**
 * What the DOM suite needs before any test runs.
 *
 * Two unrelated things, both about the environment rather than about any one
 * test.
 */

// The matchers. `@testing-library/jest-dom` has been a devDependency since the
// suite was set up and was never registered, so `toBeInTheDocument` threw
// `Invalid Chai property` -- which reads as a broken test rather than as a
// missing import, and is why assertions here had to be written the long way.
import "@testing-library/jest-dom/vitest";

/**
 * What jsdom does not implement and Radix assumes.
 *
 * `ResizeObserver` is the one that bites: `ScrollArea` measures itself in a
 * layout effect, so any test that renders a popover containing one throws
 * `ResizeObserver is not defined` from inside React's commit phase -- which
 * surfaces as an unrelated-looking failure in whichever test happened to click
 * something.
 *
 * A stub rather than a polyfill on purpose. Nothing under test asserts on
 * observed sizes; they assert on what is on screen. A real implementation would
 * be a fixture about jsdom.
 */
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
