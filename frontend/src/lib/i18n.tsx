"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * 界面双语（中文 / English）。文案与组件放在一起：每个组件用 defineCopy 声明 zh、en 两份，
 * 类型保证两种语言的键完全一致，漏写英文会在编译时报错。
 * 语言保存在 localStorage（界面偏好）和 Cookie wp_locale（供后端选择回答语言）。
 */

export type Locale = "zh" | "en";

const STORAGE_KEY = "wp_locale";

type Ctx = { locale: Locale; setLocale: (l: Locale) => void };

const LocaleContext = createContext<Ctx>({ locale: "zh", setLocale: () => {} });

function writeCookie(locale: Locale) {
  document.cookie = `${STORAGE_KEY}=${locale}; path=/; max-age=31536000; samesite=lax`;
}

function readStored(): Locale | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "en" || v === "zh" ? v : null;
  } catch {
    return null;
  }
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    // 首次渲染在服务端（默认中文），挂载后恢复客户的语言偏好
    const stored = readStored();
    if (stored) writeCookie(stored);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    // 先写 Cookie 再更新状态：子组件随语言重新请求数据时，后端已能读到新语言
    writeCookie(l);
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // 隐私模式等无法写入时，仅本次会话生效
    }
  }, []);

  return <LocaleContext.Provider value={{ locale, setLocale }}>{children}</LocaleContext.Provider>;
}

export const useLocale = () => useContext(LocaleContext);

/** 声明一个组件的双语文案；值可以是字符串，也可以是带参数的函数。 */
export function defineCopy<T>(copy: { zh: T; en: T }) {
  return copy;
}

export function useCopy<T>(copy: { zh: T; en: T }): T {
  return copy[useContext(LocaleContext).locale];
}

/** 标点：中文用全角「；」「、」「：」「（）」，英文用半角并带空格 */
export function useSeparators() {
  const en = useContext(LocaleContext).locale === "en";
  return {
    semi: en ? "; " : "；",
    comma: en ? ", " : "、",
    clause: en ? ", " : "，",
    colon: en ? ": " : "：",
    sentence: en ? " " : "",
    paren: (s: string) => (en ? ` (${s})` : `（${s}）`),
  };
}

/** 去掉演示数据名称后的「（虚构）」/ " (fictional)" 标注，界面其他位置已统一说明 */
export function stripFictional(name: string) {
  return name.replace(/\s*[（(](虚构|fictional)[）)]$/, "");
}

/** 头像上的字：中文取姓，英文跳过 Mr. / Ms. / RM 等称谓取姓氏首字母 */
export function initial(name: string) {
  const bare = stripFictional(name).replace(/^(Mr\.|Ms\.|Mrs\.|RM)\s+/, "");
  return bare.slice(0, 1).toUpperCase() || "?";
}

export function intlLocale(locale: Locale) {
  return locale === "en" ? "en-US" : "zh-CN";
}

/** 中 / EN 切换按钮 */
export function LocaleToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale } = useLocale();
  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
      aria-label={locale === "zh" ? "Switch to English" : "切换到中文"}
      className={`h-9 shrink-0 rounded-full bg-fill px-3.5 text-sm font-semibold text-ink hover:bg-line ${className}`}
    >
      {locale === "zh" ? "中 / EN" : "EN / 中"}
    </button>
  );
}
