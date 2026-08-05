import type { NextConfig } from "next";
import { dirname } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
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
  // Allow the Next dev server to serve HMR/assets to a browser reaching it over
  // the tailnet (add your Tailscale IP/host here, or set ALLOWED_DEV_ORIGINS).
  allowedDevOrigins: (process.env.ALLOWED_DEV_ORIGINS ?? "100.91.75.39")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
};

export default nextConfig;
