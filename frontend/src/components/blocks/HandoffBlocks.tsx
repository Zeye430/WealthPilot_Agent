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
 * Relationship manager card: customers contact the RM directly via WeCom or phone; only the RM's details are shown, no customer data.
 * The summary has already been shared to the RM dashboard; the card tells the customer in one sentence.
 * Demo data has no real contact details: tapping explains what would happen in production instead of dialing a fictional number.
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
