"use client";

import { useSyncExternalStore } from "react";

/**
 * 嵌入模式：客户从手机银行 App 进入时，理财助手是 App 里的一个模块。
 * 此时不显示 WealthPilot 自己的登录 / 退出，改为「返回手机银行」；会话失效时回到手机银行而不是登录页。
 * 标记保存在 sessionStorage（只对当前 WebView 有效，关掉即清除）。
 */

const KEY = "wp_entry";
export const BANK_APP_HOME = "/bank/app";

export function setEmbedded(on: boolean) {
  try {
    if (on) sessionStorage.setItem(KEY, "bank_app");
    else sessionStorage.removeItem(KEY);
  } catch {
    // 无法写入时按独立网页处理
  }
}

export function isEmbedded(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "bank_app";
  } catch {
    return false;
  }
}

/** 组件中读取嵌入模式；服务端渲染时视为非嵌入，挂载后按实际值更新 */
export function useEmbedded(): boolean {
  return useSyncExternalStore(
    () => () => {},
    isEmbedded,
    () => false,
  );
}

/** 嵌入页通知外层演示框架当前进行到哪一步（只在电脑端演示页 /bank 中有接收方） */
export function notifyDemoStep(step: number) {
  if (typeof window !== "undefined" && window.parent !== window) {
    window.parent.postMessage({ type: "wp-demo-step", step }, window.location.origin);
  }
}
