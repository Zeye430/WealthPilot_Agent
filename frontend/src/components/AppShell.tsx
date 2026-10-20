"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AssessmentDialog } from "@/components/AssessmentDialog";
import { Chat, type ChatHandle } from "@/components/Chat";
import { MeView } from "@/components/MeView";
import { AssetCard, NeedsCard, ratingName, RiskCard, riskRange, RmRow } from "@/components/Profile";
import { ProductActionsProvider } from "@/components/products/ProductActions";
import { ProductBrowser } from "@/components/products/ProductBrowser";
import { RemindersView } from "@/components/products/RemindersView";
import { Avatar, Button, Chip, Icon, type IconName, StepProgress } from "@/components/ui";
import { getMe, getSessionUser, listConversations, logout, resetDemo, type SessionUser } from "@/lib/api";
import { BANK_APP_HOME, isEmbedded, useEmbedded } from "@/lib/embed";
import { defineCopy, LocaleToggle, useCopy, useLocale, initial } from "@/lib/i18n";
import type { ConversationSummary, CustomerState } from "@/lib/types";

type View = "chat" | "products" | "reminders" | "me";

const COPY = defineCopy({
  zh: {
    tagline: "知岸银行（虚构）智能理财助手",
    nav: { chat: "对话", products: "理财产品", reminders: "我的提醒", me: "我的" } as Record<View, string>,
    titles: { chat: "理财助手", products: "理财产品", reminders: "我的提醒", me: "我的" } as Record<View, string>,
    contactRm: "联系理财经理",
    contactRmMessage: "我想联系理财经理",
    newChat: "新对话",
    recent: "最近对话",
    untitled: "未命名对话",
    logout: "退出登录",
    backToBank: "返回手机银行",
    notAssessed: "未测评",
    steps: ["了解需求", "风险测评", "匹配产品", "预约或买入"],
    stepLabel: (n: number, name: string) => `第 ${n} 步，共 4 步：${name}`,
    allDone: "四个步骤均已完成，可以随时继续提问",
    assessed: (rating: string, name: string, range: string) => `风险测评已完成：${rating} ${name}，可购买 ${range} 产品。`,
  },
  en: {
    tagline: "AI wealth assistant for Zhian Bank (fictional)",
    nav: { chat: "Chat", products: "Products", reminders: "Reminders", me: "Me" } as Record<View, string>,
    titles: { chat: "Assistant", products: "Products", reminders: "Reminders", me: "Me" } as Record<View, string>,
    contactRm: "Contact my RM",
    contactRmMessage: "I'd like to talk to my relationship manager.",
    newChat: "New chat",
    recent: "Recent chats",
    untitled: "Untitled chat",
    logout: "Sign out",
    backToBank: "Back to banking app",
    notAssessed: "Not profiled",
    steps: ["Needs", "Risk profile", "Matching", "Reserve or buy"],
    stepLabel: (n: number, name: string) => `Step ${n} of 4: ${name}`,
    allDone: "All four steps done. Ask anything, anytime.",
    assessed: (rating: string, name: string, range: string) => `Risk profile complete: ${rating} ${name}, eligible for ${range}.`,
  },
});

const NAV_ICONS: Record<View, IconName> = { chat: "chat", products: "grid", reminders: "bell", me: "user" };
const VIEWS: View[] = ["chat", "products", "reminders", "me"];

/** Dispatched by the components when a purchase is confirmed or a reminder is set, to update step 4 of the progress bar. */
export const ACTED_EVENT = "wp:acted";

export function AppShell() {
  const router = useRouter();
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const embedded = useEmbedded();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [state, setState] = useState<CustomerState | null>(null);
  const [view, setView] = useState<View>("chat");
  const [chatKey, setChatKey] = useState(0);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [openConversation, setOpenConversation] = useState<string | null>(null);
  const [assessing, setAssessing] = useState(false);
  const [matched, setMatched] = useState(false);
  const [acted, setActed] = useState(false);
  const chatRef = useRef<ChatHandle>(null);

  const refreshState = useCallback(() => {
    getMe()
      .then(setState)
      .catch(() => setState(null));
  }, []);

  const refreshHistory = useCallback(() => {
    listConversations()
      .then(setHistory)
      .catch(() => setHistory([]));
  }, []);

  useEffect(() => {
    // When not signed in the API returns 401: go to the sign-in page; RM accounts go to the dashboard
    getSessionUser()
      .then((u) => {
        if (u.role !== "customer") {
          router.replace(u.role === "rm" ? "/rm" : "/ops");
          return;
        }
        setUser(u);
        refreshState();
        refreshHistory();
      })
      // Entered from the banking app, there's no WealthPilot sign-in page: if the session expires, go back to the bank app to re-enter
      .catch(() => (isEmbedded() ? window.location.assign(BANK_APP_HOME) : router.replace("/login")));
  }, [router, refreshState, refreshHistory]);

  // After switching language, reload the profile and conversation titles: tier and rating names come from the backend per language
  useEffect(() => {
    if (!user) return;
    refreshState();
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  useEffect(() => {
    const onActed = () => setActed(true);
    window.addEventListener(ACTED_EVENT, onActed);
    return () => window.removeEventListener(ACTED_EVENT, onActed);
  }, []);

  function newChat() {
    setOpenConversation(null);
    setMatched(false);
    setChatKey((k) => k + 1); // changing the key remounts Chat, starting a new conversation
    setView("chat");
  }

  function openHistory(id: string) {
    setOpenConversation(id);
    setChatKey((k) => k + 1);
    setView("chat");
  }

  function contactRm() {
    setView("chat");
    chatRef.current?.send(c.contactRmMessage);
  }

  async function reset() {
    await resetDemo();
    refreshState();
    refreshHistory();
    newChat();
  }

  async function signOut() {
    await logout().catch(() => undefined);
    if (embedded) {
      // Leave the assistant: end the WealthPilot session and return to the banking app (the bank session is unaffected)
      window.location.assign(BANK_APP_HOME);
      return;
    }
    router.replace("/login");
  }

  const startAssessment = () => setAssessing(true);

  // Progress: needs → risk assessment → matching → reserve or buy (no recommendations before an assessment, so this is the real order)
  const done = [
    !!state?.profile.needs.some((n) => n.value),
    !!state?.assessment,
    matched,
    acted,
  ];
  const next = done.findIndex((d) => !d);
  const progressLabel = next === -1 ? c.allDone : c.stepLabel(next + 1, c.steps[next]);
  const doneCount = next === -1 ? 4 : next;

  const ratingChip = state?.assessment ? (
    <Chip tone="neutral" className="h-8 text-[13px]">
      {state.assessment.rating} {ratingName(state, locale)}
    </Chip>
  ) : (
    <button type="button" onClick={startAssessment}>
      <Chip tone="notice" className="h-8 text-[13px]">
        {c.notAssessed}
      </Chip>
    </button>
  );

  return (
    <ProductActionsProvider onStartAssessment={startAssessment}>
      <div className="flex h-full bg-canvas">
        {/* Desktop left column */}
        <aside className="hidden w-64 shrink-0 flex-col gap-6 overflow-y-auto bg-fill px-5 py-7 lg:flex" aria-label="WealthPilot">
          <div className="flex flex-col gap-0.5">
            <span className="text-[22px] font-extrabold tracking-tight">WealthPilot</span>
            <span className="text-xs text-ink-3">{c.tagline}</span>
          </div>
          <Button onClick={newChat} className="w-full">
            {c.newChat}
          </Button>
          <nav className="flex flex-col gap-1 text-[15px]">
            {VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-current={view === v ? "page" : undefined}
                className={`flex items-center gap-3 rounded-full px-4 py-2.5 text-left ${
                  view === v ? "bg-canvas font-extrabold text-ink" : "font-semibold text-ink-2 hover:bg-canvas/60"
                }`}
              >
                <Icon name={NAV_ICONS[v]} size={20} strokeWidth={view === v ? 2.4 : 2} />
                {c.nav[v]}
              </button>
            ))}
            <button
              type="button"
              onClick={contactRm}
              className="flex items-center gap-3 rounded-full px-4 py-2.5 text-left font-semibold text-ink-2 hover:bg-canvas/60"
            >
              <Icon name="phone" size={20} />
              {c.contactRm}
            </button>
          </nav>

          {history.length > 0 && (
            <section className="flex min-h-0 flex-col gap-0.5 text-sm" aria-label={c.recent}>
              <span className="px-4 pb-1.5 text-xs font-bold text-ink-3">{c.recent}</span>
              {history.slice(0, 8).map((h) => (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => openHistory(h.id)}
                  title={h.title ?? ""}
                  className={`truncate rounded-full px-4 py-2 text-left ${
                    openConversation === h.id ? "bg-canvas font-semibold" : "text-ink-2 hover:bg-canvas/60"
                  }`}
                >
                  {h.title || c.untitled}
                </button>
              ))}
            </section>
          )}

          <div className="mt-auto flex items-center gap-2.5">
            <Avatar text={user ? initial(user.display_name) : "?"} tone="navy" />
            <span className="flex min-w-0 flex-1 flex-col text-[13px]">
              <span className="truncate font-bold">{user?.display_name}</span>
              <button type="button" onClick={signOut} className="self-start text-ink-3 hover:text-ink">
                {embedded ? c.backToBank : c.logout}
              </button>
            </span>
            <LocaleToggle className="bg-canvas" />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Mobile top bar */}
          <header className="flex shrink-0 items-center justify-between gap-3 px-5 pt-4 pb-2 lg:hidden">
            {/* The Me page has its own greeting title, so the top bar doesn't repeat it */}
            <div className="flex min-w-0 items-center gap-1.5">
              {/* Embedded in the banking app: back to the app at the top left (like the native navigation bar's back button) */}
              {embedded && (
                <button type="button" onClick={signOut} aria-label={c.backToBank} className="-ml-2 flex h-9 w-9 items-center justify-center rounded-full hover:bg-fill">
                  <Icon name="back" size={22} />
                </button>
              )}
              <h1 className={`text-[22px] font-extrabold tracking-tight ${view === "me" ? "invisible" : ""}`}>{c.titles[view]}</h1>
            </div>
            <div className="flex items-center gap-2">
              {view === "chat" && ratingChip}
              <LocaleToggle />
            </div>
          </header>

          <main className="flex min-h-0 flex-1 flex-col">
            {view === "chat" && (
              <div className="mx-auto w-full max-w-3xl px-5 pt-1 pb-2 lg:px-12 lg:pt-7">
                <StepProgress label={progressLabel} done={doneCount} />
              </div>
            )}
            {view === "products" && <ProductBrowser state={state} onStartAssessment={startAssessment} />}
            {view === "reminders" && <RemindersView onBrowse={() => setView("products")} />}
            {view === "me" && (
              <MeView
                user={user}
                state={state}
                onAsk={() => setView("chat")}
                onProducts={() => setView("products")}
                onReminders={() => setView("reminders")}
                onContactRm={contactRm}
                onStartAssessment={startAssessment}
                onStateChange={setState}
                onReset={reset}
                onLogout={signOut}
              />
            )}
            {/* Chat stays mounted and is only hidden when switching pages, so the conversation isn't lost */}
            <div className={`min-h-0 flex-1 ${view === "chat" ? "" : "hidden"}`}>
              <Chat
                key={chatKey}
                ref={chatRef}
                initialConversationId={openConversation}
                onActivity={refreshHistory}
                onStartAssessment={startAssessment}
                onStateChange={setState}
                onMatched={() => setMatched(true)}
              />
            </div>
          </main>

          {/* Mobile bottom navigation */}
          <nav className="grid h-[68px] shrink-0 grid-cols-4 border-t border-line bg-canvas pb-[env(safe-area-inset-bottom)] lg:hidden">
            {VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-current={view === v ? "page" : undefined}
                className={`flex flex-col items-center justify-center gap-1 text-[11px] ${
                  view === v ? "font-extrabold text-ink" : "font-semibold text-ink-3"
                }`}
              >
                <Icon name={NAV_ICONS[v]} strokeWidth={view === v ? 2.4 : 2} />
                {c.nav[v]}
              </button>
            ))}
          </nav>
        </div>

        {/* Desktop right column: only on the chat page; products, reminders, etc. use the full width */}
        <aside
          className={`hidden w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-line px-6 py-7 ${view === "chat" ? "xl:flex" : ""}`}
          aria-label={c.nav.me}
        >
          <AssetCard state={state} compact />
          <RiskCard state={state} onStart={startAssessment} />
          <NeedsCard state={state} onChange={setState} />
          <RmRow state={state} onContact={contactRm} />
        </aside>
      </div>

      <AssessmentDialog
        open={assessing}
        onClose={() => setAssessing(false)}
        onConfirmed={(nextState, result) => {
          setState(nextState);
          chatRef.current?.addNotice(
            c.assessed(result.rating, ratingName(nextState, locale) ?? result.rating_name, riskRange(result.max_product_risk)),
          );
        }}
      />
    </ProductActionsProvider>
  );
}
