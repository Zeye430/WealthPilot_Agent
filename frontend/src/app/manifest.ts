import type { MetadataRoute } from "next";

// Progressive web app: after "Add to Home Screen" on a phone it opens full screen, like a native app
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
