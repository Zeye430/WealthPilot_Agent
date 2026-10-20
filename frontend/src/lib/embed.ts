"use client";

import { useSyncExternalStore } from "react";

/**
 * Embedded mode: when the customer enters from the banking app, the assistant is a module inside the app.
 * WealthPilot's own sign-in / sign-out are hidden in favor of "Back to banking app"; an expired session returns to the bank app instead of the sign-in page.
 * The flag lives in sessionStorage (valid only for the current WebView, cleared when it closes).
 */

const KEY = "wp_entry";
export const BANK_APP_HOME = "/bank/app";

export function setEmbedded(on: boolean) {
  try {
    if (on) sessionStorage.setItem(KEY, "bank_app");
    else sessionStorage.removeItem(KEY);
  } catch {
    // If storage can't be written, treat it as a standalone page
  }
}

export function isEmbedded(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "bank_app";
  } catch {
    return false;
  }
}

/** Read embedded mode in components; server rendering treats it as not embedded, updated with the real value after mount */
export function useEmbedded(): boolean {
  return useSyncExternalStore(
    () => () => {},
    isEmbedded,
    () => false,
  );
}

/** The embedded page tells the outer demo frame which step it reached (only the desktop demo page /bank listens) */
export function notifyDemoStep(step: number) {
  if (typeof window !== "undefined" && window.parent !== window) {
    window.parent.postMessage({ type: "wp-demo-step", step }, window.location.origin);
  }
}
