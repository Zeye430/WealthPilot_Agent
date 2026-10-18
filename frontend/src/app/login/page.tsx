import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "登录",
  description: "WealthPilot 演示：客户或理财经理账号登录",
};

export default function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  return (
    <Suspense fallback={null}>
      <Login searchParams={searchParams} />
    </Suspense>
  );
}

async function Login({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <LoginForm next={next ?? null} />;
}
