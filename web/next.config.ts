import type { NextConfig } from "next";
import { networkInterfaces } from "os";
import { dirname } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));

/** Every address this machine can be reached on, plus anything asked for. */
function devOrigins(): string[] {
  const found = new Set(["127.0.0.1", "::1", "[::1]"]);

  for (const addresses of Object.values(networkInterfaces())) {
    for (const address of addresses ?? []) {
      if (address.internal) continue;
      // IPv6 arrives bracketed in a Host/Origin header; accept either form.
      found.add(address.address);
      if (address.family === "IPv6") found.add(`[${address.address}]`);
    }
  }

  for (const extra of (process.env.ALLOWED_DEV_ORIGINS ?? "").split(",")) {
    const trimmed = extra.trim();
    if (trimmed) found.add(trimmed);
  }

  return [...found];
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // One build directory per worker, when asked for.
  //
  // `next dev` and `next build` both own `.next`, so running a build while a
  // dev server is up deletes the chunks that server has already told a browser
  // to fetch. The page then half-loads with no explanation. Set NEXT_DIST_DIR
  // to work alongside someone else's dev server instead of underneath it.
  //
  // Setting it makes Next rewrite `tsconfig.json` and `next-env.d.ts` to point
  // at the new directory; check those two back out when you are done, or the
  // path leaks into the commit.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // This app renders code, graphs and findings -- it has no bitmap assets and
  // imports next/image nowhere. Turning the optimizer off means sharp, and the
  // LGPL libvips binary underneath it, is never loaded. (It cannot be dropped
  // at install time: it is an optional dependency of next, and --omit=optional
  // would take @next/swc-* with it. See web/licenses.config.json.)
  images: { unoptimized: true },
  // Keep the dev-only indicator out of the sidebar's bottom-left corner.
  devIndicators: { position: "bottom-right" },
  // This app is self-contained; pin the tracing root so the repo-root
  // lockfile doesn't trigger a workspace-root warning.
  outputFileTracingRoot: here,
  // Who may load /_next/* from the dev server.
  //
  // Next allows `localhost` and nothing else by default, and refuses the rest
  // with a 403. That failure is unusually cruel: the HTML is server-rendered
  // and looks perfect, while every client chunk is blocked -- so the page
  // never hydrates and not one button does anything. It reads as an app with
  // dead buttons, not as a blocked request.
  //
  // `127.0.0.1` is the common way in and is *not* covered by `localhost`: an
  // SSH or VS Code forwarded port presents the server as a loopback IP. The
  // rest are this machine's own interface addresses, so reaching the box on
  // its LAN or tailnet address works without anyone editing a list. Both are
  // addresses of this host, which is the thing the check is really asking
  // about. `next build`/`next start` ignore this entirely.
  allowedDevOrigins: devOrigins(),
};

export default nextConfig;
