import type { MetadataRoute } from "next";

// 渐进式网页应用：手机上「添加到主屏幕」后全屏打开，像原生 App 一样使用
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "WealthPilot",
    short_name: "WealthPilot",
    description: "AI wealth assistant (demo) · 理财助手（演示）",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
