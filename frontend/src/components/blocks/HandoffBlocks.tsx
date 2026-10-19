"use client";

import { useState } from "react";

import { Avatar, Icon } from "@/components/ui";
import { defineCopy, useCopy, initial } from "@/lib/i18n";
import type { RmContactBlock } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    subtitle: (title: string) => `${title}，您的专属理财经理`,
    wecom: "企业微信联系",
    call: "拨打电话",
    wecomDemo: (name: string) => `演示环境：真实部署时将打开企业微信，与${name}发起会话。`,
    callDemo: (name: string) => `演示环境：真实部署时将直接拨打${name}的工作电话。`,
  },
  en: {
    subtitle: (title: string) => `${title}, your relationship manager`,
    wecom: "Message on WeCom",
    call: "Call",
    wecomDemo: (name: string) => `Demo: in production this opens a WeCom chat with ${name}.`,
    callDemo: (name: string) => `Demo: in production this calls ${name}'s work phone.`,
  },
});

/**
 * 理财经理名片：客户通过企业微信或电话直接联系，只展示理财经理信息，不展示客户资料。
 * 咨询要点已由系统同步到理财经理看板，名片上用一句话告知客户。
 * 演示数据没有真实联系方式：点击时说明真实环境中会发生什么，而不是拨打一个虚构号码。
 */
export function RmContactCard({ block }: { block: RmContactBlock }) {
  const c = useCopy(COPY);
  const [demoNote, setDemoNote] = useState<string | null>(null);

  return (
    <div className="flex max-w-md flex-col gap-4 rounded-card bg-fill p-5">
      <div className="flex items-center gap-3">
        <Avatar text={initial(block.rm_name)} tone="navy" />
        <div className="min-w-0">
          <p className="text-base font-extrabold">{block.rm_name}</p>
          <p className="text-xs text-ink-2">{c.subtitle(block.rm_title)}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <ContactButton label={c.wecom} icon="chat" href={block.wecom_url} external primary onDemo={() => setDemoNote(c.wecomDemo(block.rm_name))} />
        <ContactButton label={c.call} icon="phone" href={block.phone ? `tel:${block.phone}` : null} onDemo={() => setDemoNote(c.callDemo(block.rm_name))} />
      </div>
      {demoNote && (
        <p role="status" className="text-xs leading-5 text-ink-2">
          {demoNote}
        </p>
      )}

      <p className="border-t border-line pt-3 text-xs leading-5 text-ink-2">{block.notice}</p>
    </div>
  );
}

function ContactButton({
  label,
  icon,
  href,
  external = false,
  primary = false,
  onDemo,
}: {
  label: string;
  icon: "chat" | "phone";
  href: string | null;
  external?: boolean;
  primary?: boolean;
  onDemo: () => void;
}) {
  const className = `flex h-11 items-center justify-center gap-2 rounded-full px-3 text-sm font-bold ${
    primary ? "bg-brand text-on-brand hover:bg-brand-strong" : "border-2 border-ink text-ink hover:bg-canvas"
  }`;
  const content = (
    <>
      <Icon name={icon} size={18} />
      {label}
    </>
  );
  if (href) {
    return (
      <a href={href} className={className} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
        {content}
      </a>
    );
  }
  return (
    <button type="button" onClick={onDemo} className={className}>
      {content}
    </button>
  );
}
