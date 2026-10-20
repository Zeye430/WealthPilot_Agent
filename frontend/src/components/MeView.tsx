"use client";

import { useEffect, useState } from "react";

import { listReminders } from "@/lib/api";
import { useEmbedded } from "@/lib/embed";
import { defineCopy, initial, stripFictional, useCopy, useLocale } from "@/lib/i18n";
import type { SessionUser } from "@/lib/api";
import type { CustomerState, Reminder } from "@/lib/types";

import { AssetCard, NeedsCard, RiskCard, RmRow } from "./Profile";
import { Avatar, ChevronRight, Icon, type IconName } from "./ui";

const COPY = defineCopy({
  zh: {
    greeting: (h: number) => (h < 11 ? "早上好" : h < 18 ? "下午好" : "晚上好"),
    bank: "知岸银行",
    ask: "问助手",
    products: "理财产品",
    reminders: "我的提醒",
    contact: "联系经理",
    mySituation: "我的情况",
    upcoming: (window: string) => `${window}开售，已预约提醒`,
    reset: "清空我的演示数据",
    logout: "退出登录",
    backToBank: "返回手机银行",
    demo: "作品集演示：虚构机构、产品与客户；买入只到确认页，不会真实下单。",
    comma: "，",
  },
  en: {
    greeting: (h: number) => (h < 11 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"),
    bank: "Zhian Bank",
    ask: "Ask",
    products: "Products",
    reminders: "Reminders",
    contact: "Contact RM",
    mySituation: "Overview",
    upcoming: (window: string) => `Opens ${window}, reminder set`,
    reset: "Reset my demo data",
    logout: "Sign out",
    backToBank: "Back to banking app",
    demo: "Portfolio demo: fictional bank, products and customers. Purchases stop at the confirmation step.",
    comma: ", ",
  },
});

/** Me: asset overview card + four shortcuts + list rows (information layout inspired by the PayPal home screen). */
export function MeView({
  user,
  state,
  onAsk,
  onProducts,
  onReminders,
  onContactRm,
  onStartAssessment,
  onStateChange,
  onReset,
  onLogout,
}: {
  user: SessionUser | null;
  state: CustomerState | null;
  onAsk: () => void;
  onProducts: () => void;
  onReminders: () => void;
  onContactRm: () => void;
  onStartAssessment: () => void;
  onStateChange: (s: CustomerState) => void;
  onReset: () => void;
  onLogout: () => void;
}) {
  const c = useCopy(COPY);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [hour] = useState(() => new Date().getHours());

  const { locale } = useLocale();
  const embedded = useEmbedded();
  useEffect(() => {
    listReminders()
      .then(setReminders)
      .catch(() => setReminders([]));
  }, [locale]);

  const name = user ? stripFictional(user.display_name) : "";
  const actions: { label: string; icon: IconName; onClick: () => void; primary?: boolean }[] = [
    { label: c.ask, icon: "chat", onClick: onAsk, primary: true },
    { label: c.products, icon: "grid", onClick: onProducts },
    { label: c.reminders, icon: "bell", onClick: onReminders },
    { label: c.contact, icon: "phone", onClick: onContactRm },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-xl flex-col gap-6 px-5 pt-5 pb-8">
        <header className="flex flex-col gap-0.5">
          <span className="text-[13px] text-ink-3">{c.bank}</span>
          <h1 className="text-[26px] font-extrabold tracking-tight">
            {c.greeting(hour)}
            {name && `${c.comma}${name}`}
          </h1>
        </header>

        <AssetCard state={state} />

        <nav aria-label={c.mySituation} className="grid grid-cols-4 gap-2">
          {actions.map((a) => (
            <button key={a.label} type="button" onClick={a.onClick} className="flex flex-col items-center gap-2 text-xs font-bold">
              <span
                className={`flex h-14 w-14 items-center justify-center rounded-full ${
                  a.primary ? "bg-brand text-on-brand" : "bg-fill text-ink hover:bg-line"
                }`}
              >
                <Icon name={a.icon} size={24} />
              </span>
              {a.label}
            </button>
          ))}
        </nav>

        <section className="flex flex-col gap-3">
          <h2 className="text-[17px] font-extrabold">{c.mySituation}</h2>
          <RiskCard state={state} onStart={onStartAssessment} />
          {reminders.slice(0, 2).map((r) => (
            <button key={r.id} type="button" onClick={onReminders} className="flex items-center gap-3 rounded-2xl py-2 text-left hover:bg-fill">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-fill">
                <Icon name="bell" size={20} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[15px] font-bold">{r.product.name}</span>
                <span className="text-[13px] text-ink-3">{c.upcoming(r.product.sale_window ?? "")}</span>
              </span>
              <ChevronRight />
            </button>
          ))}
          <RmRow state={state} onContact={onContactRm} />
          <NeedsCard state={state} onChange={onStateChange} />
        </section>

        <div className="flex flex-col gap-3 border-t border-line pt-5 text-sm">
          {user && (
            <div className="flex items-center gap-3">
              <Avatar text={initial(name)} tone="navy" />
              <span className="font-bold">{user.display_name}</span>
            </div>
          )}
          <div className="flex flex-wrap gap-x-5 gap-y-2 font-semibold text-ink-2">
            <button type="button" onClick={onLogout} className="hover:text-ink">
              {embedded ? c.backToBank : c.logout}
            </button>
            <button type="button" onClick={onReset} className="hover:text-ink">
              {c.reset}
            </button>
          </div>
          <p className="text-xs leading-5 text-ink-3">{c.demo}</p>
        </div>
      </div>
    </div>
  );
}
