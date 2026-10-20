"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * Bilingual UI (Chinese / English). Copy lives next to components: each component declares zh and en with defineCopy,
 * and types ensure both languages have exactly the same keys, so a missing English string fails to compile.
 * The language is saved in localStorage (UI preference) and the wp_locale cookie (so the backend picks the reply language).
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
    // The first render is on the server (Chinese by default); the customer's language preference is restored after mount
    const stored = readStored();
    if (stored) writeCookie(stored);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    // Write the cookie before updating state: when children refetch for the new language, the backend already sees it
    writeCookie(l);
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // If storage can't be written (e.g. private mode), the choice lasts only for this session
    }
  }, []);

  return <LocaleContext.Provider value={{ locale, setLocale }}>{children}</LocaleContext.Provider>;
}

export const useLocale = () => useContext(LocaleContext);

/** Declare a component's bilingual copy; values can be strings or functions with parameters. */
export function defineCopy<T>(copy: { zh: T; en: T }) {
  return copy;
}

export function useCopy<T>(copy: { zh: T; en: T }): T {
  return copy[useContext(LocaleContext).locale];
}

/** Punctuation: full-width separators in Chinese, half-width with spaces in English */
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

/** Strip the "(fictional)" label after demo names; the UI already says so elsewhere */
export function stripFictional(name: string) {
  return name.replace(/\s*[（(](虚构|fictional)[）)]$/, "");
}

/** Avatar text: the surname in Chinese; in English, skip titles such as Mr. / Ms. / RM and take the surname's initial */
export function initial(name: string) {
  const bare = stripFictional(name).replace(/^(Mr\.|Ms\.|Mrs\.|RM)\s+/, "");
  return bare.slice(0, 1).toUpperCase() || "?";
}

export function intlLocale(locale: Locale) {
  return locale === "en" ? "en-US" : "zh-CN";
}

/** 中 / EN toggle button */
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
