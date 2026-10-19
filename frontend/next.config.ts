import type { NextConfig } from "next";

// 浏览器只访问 Next.js；/api 由 Next.js 代理到 FastAPI，前端无需处理跨域。
// 注意：rewrites 在 `next build` 时求值，Docker 构建时通过 BACKEND_URL 构建参数传入。
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // /api 代理默认 30 秒超时；一轮对话可能包含多次工具调用与模型调用，超过 30 秒时客户会看到请求失败。
    // 120 秒覆盖正常的多工具回合；单轮总时长的上限（超时降级）计划在 P8-4 可靠性阶段由后端控制。
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
    ];
  },
};

export default nextConfig;
