import type { Metadata } from "next";
import { Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";
import "./globals.css";

const notoSans = Noto_Sans_SC({
  variable: "--font-noto-sans",
  weight: ["400", "500", "700"],
  preload: false,
});

const notoSerif = Noto_Serif_SC({
  variable: "--font-noto-serif",
  weight: ["500", "700"],
  preload: false,
});

export const metadata: Metadata = {
  title: "WealthPilot 理财助手",
  description: "面向银行理财客户的 AI 理财助手（演示系统）",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className={`${notoSans.variable} ${notoSerif.variable} h-full antialiased`}>
      <body className="h-full">{children}</body>
    </html>
  );
}
