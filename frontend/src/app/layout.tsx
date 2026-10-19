import type { Metadata, Viewport } from "next";
import { Noto_Sans_SC, Plus_Jakarta_Sans } from "next/font/google";

import { I18nProvider } from "@/lib/i18n";

import "./globals.css";

// 英文与数字：Plus Jakarta Sans（开源，圆润现代）；中文：Noto Sans SC
const jakarta = Plus_Jakarta_Sans({
  variable: "--font-jakarta",
  weight: ["400", "500", "600", "700", "800"],
  subsets: ["latin"],
});

const notoSans = Noto_Sans_SC({
  variable: "--font-noto-sans",
  weight: ["400", "500", "700"],
  preload: false,
});

export const metadata: Metadata = {
  title: "WealthPilot",
  description: "AI wealth assistant for retail banking (demo) · 银行理财 AI 助手（演示系统）",
  appleWebApp: { capable: true, title: "WealthPilot", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className={`${jakarta.variable} ${notoSans.variable} h-full antialiased`}>
      <body className="h-full">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
