import type { NextConfig } from "next";

// 浏览器只访问 Next.js；/api 由 Next.js 代理到 FastAPI，前端无需处理跨域。
// 注意：rewrites 在 `next build` 时求值，Docker 构建时通过 BACKEND_URL 构建参数传入。
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
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
    ];
  },
};

export default nextConfig;
