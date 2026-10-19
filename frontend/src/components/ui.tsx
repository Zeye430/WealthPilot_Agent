/**
 * 基础界面组件：胶囊按钮、标签、浅灰卡片、列表行、四段式进度条。
 * 设计令牌见 app/globals.css（白底、浅灰分区、深海军蓝文字、亮蓝主操作）。
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "quiet" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-on-brand hover:bg-brand-strong",
  secondary: "border-2 border-ink text-ink hover:bg-fill",
  quiet: "bg-fill text-ink hover:bg-line",
  danger: "bg-danger text-white",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-9 px-4 text-sm", md: "h-11 px-5 text-[15px]", lg: "h-13 px-6 text-base" };
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-bold transition-colors disabled:opacity-40 ${VARIANTS[variant]} ${sizes[size]} ${className}`}
    />
  );
}

export function Chip({
  children,
  tone = "brand",
  className = "",
}: {
  children: ReactNode;
  tone?: "brand" | "neutral" | "ok" | "notice" | "danger";
  className?: string;
}) {
  const tones = {
    brand: "bg-brand-soft text-brand",
    neutral: "bg-fill text-ink",
    ok: "bg-ok-soft text-ok",
    notice: "bg-notice-soft text-notice",
    danger: "bg-danger-soft text-danger",
  };
  return (
    <span
      className={`inline-flex h-7 shrink-0 items-center rounded-full px-3 text-xs font-bold whitespace-nowrap ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-card bg-fill p-5 ${className}`}>{children}</div>;
}

export function Avatar({ text, tone = "brand" }: { text: string; tone?: "brand" | "navy" | "neutral" }) {
  const tones = { brand: "bg-brand-soft text-brand", navy: "bg-navy text-white", neutral: "bg-fill text-ink" };
  return (
    <span
      aria-hidden
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-extrabold ${tones[tone]}`}
    >
      {text}
    </span>
  );
}

export function ChevronRight() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0 text-ink-3">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}

/** 四段式办理进度：真实的先后顺序（未测评不能推荐），当前步骤之前的段填充为主色。 */
export function StepProgress({ label, done, total = 4 }: { label: string; done: number; total?: number }) {
  return (
    <div aria-label={label} className="flex flex-col gap-2">
      <span className="text-[13px] font-bold">{label}</span>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}>
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={`h-1 rounded-full ${i < done ? "bg-brand" : "bg-line"}`} />
        ))}
      </div>
    </div>
  );
}

/** 线性图标（与设计稿一致的 24px 描边图标） */
export function Icon({ name, size = 22, strokeWidth = 2 }: { name: IconName; size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {ICONS[name]}
    </svg>
  );
}

export type IconName = "chat" | "grid" | "bell" | "user" | "phone" | "plus" | "logout" | "back" | "send" | "mic" | "close";

const ICONS: Record<IconName, ReactNode> = {
  chat: <path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  bell: (
    <>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  phone: (
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
  ),
  plus: (
    <>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </>
  ),
  back: <path d="M15 18l-6-6 6-6" />,
  send: (
    <>
      <path d="M12 19V5" />
      <path d="M5 12l7-7 7 7" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </>
  ),
  close: (
    <>
      <path d="M18 6L6 18" />
      <path d="M6 6l12 12" />
    </>
  ),
};
