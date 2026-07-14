import type { NextConfig } from "next";
import { dirname } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // This app is self-contained; pin the tracing root so sibling lockfiles
  // (the repo root / old web/) don't trigger a workspace-root warning.
  outputFileTracingRoot: here,
  // Allow the Next dev server to serve HMR/assets to a browser reaching it over
  // the tailnet (add your Tailscale IP/host here, or set ALLOWED_DEV_ORIGINS).
  allowedDevOrigins: (process.env.ALLOWED_DEV_ORIGINS ?? "100.91.75.39")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
};

export default nextConfig;
