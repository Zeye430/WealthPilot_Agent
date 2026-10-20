import type { NextConfig } from "next";

// The browser talks only to Next.js; /api is proxied to FastAPI, so the frontend needs no CORS handling.
// Note: rewrites are evaluated at `next build`; Docker builds pass the BACKEND_URL build argument.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // The /api proxy times out after 30 s by default; a turn may include several tool and model calls, and customers would see a failure past 30 s.
    // 120 s covers normal multi-tool turns; the backend enforces the overall turn budget (graceful timeout, added in P8-4).
    proxyTimeout: 120_000,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/health", destination: `${backendUrl}/health` },
      // Back-end API of the simulated mobile banking app (demo); in production this is the bank's own system
      { source: "/bank-sim/api/:path*", destination: `${backendUrl}/bank-sim/api/:path*` },
    ];
  },
};

export default nextConfig;
