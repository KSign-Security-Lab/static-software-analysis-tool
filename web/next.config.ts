import type { NextConfig } from "next";
import { networkInterfaces } from "os";
import { dirname } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));

function devOrigins(): string[] {
  const found = new Set(["127.0.0.1", "::1", "[::1]"]);

  for (const addresses of Object.values(networkInterfaces())) {
    for (const address of addresses ?? []) {
      if (address.internal) continue;
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
  distDir: process.env.NEXT_DIST_DIR || ".next",
  images: { unoptimized: true },
  devIndicators: { position: "bottom-right" },
  outputFileTracingRoot: here,
  allowedDevOrigins: devOrigins(),
};

export default nextConfig;
