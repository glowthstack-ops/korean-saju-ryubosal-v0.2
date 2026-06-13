"use client";

// 랜딩 — 사주목록 진입 + 무료(만세력·간지달력) / 로그인 전용(테마사주·AI상담) 구분.

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";

interface Service {
  href: string;
  title: string;
  desc: string;
  paid?: boolean;
}

const FREE: Service[] = [
  {
    href: "/manse",
    title: "만세력",
    desc: "생년월일시·출생지로 원국과 대운/세운/월운을 확인하고 용신을 검증합니다.",
  },
  {
    href: "/calendar",
    title: "간지달력",
    desc: "날짜별 간지(한글·한자 병기)와 절기를 월 단위로 제공합니다.",
  },
];

const PAID: Service[] = [
  {
    href: "/themes",
    title: "테마사주",
    desc: "총운·궁합·직장운·금전운을 페이지 단위 풀이로 제공하고 PDF로 저장합니다.",
    paid: true,
  },
  {
    href: "/chat",
    title: "AI채팅상담",
    desc: "엔진이 계산한 운의 신호를 근거와 함께 대화로 풀이합니다.",
    paid: true,
  },
];

export default function HomePage() {
  const { isLoggedIn } = useAuth();

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold">류보살 v2</h1>
        <p className="mt-2 text-sm text-gray-600">
          LLM이 계산하지 않습니다. 결정론적 만세력 엔진이 원국·세력·용신·대운/세운/월운을 계산하고,
          AI는 그 사실과 점수를 자연어로 풀이만 합니다.
        </p>
        <Link
          href="/sajus"
          className="mt-4 inline-block rounded bg-gray-800 px-4 py-2 text-sm text-white"
        >
          내 사주목록 →
        </Link>
        {!isLoggedIn && (
          <p className="mt-2 text-xs text-gray-400">
            비회원은 만세력·간지달력을 기기당 1개 사주로 바로 이용할 수 있어요. 로그인하면 여러 사주를
            저장하고 테마사주·AI상담을 이용할 수 있습니다.
          </p>
        )}
      </section>

      <Section title="무료" subtitle="로그인 없이 이용 가능">
        {FREE.map((s) => (
          <ServiceCard key={s.href} service={s} locked={false} />
        ))}
      </Section>

      <Section title="로그인 전용" subtitle="여러 사주 저장 · 유료 풀이">
        {PAID.map((s) => (
          <ServiceCard key={s.href} service={s} locked={!isLoggedIn} />
        ))}
      </Section>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
        <span className="text-xs text-gray-400">{subtitle}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function ServiceCard({ service, locked }: { service: Service; locked: boolean }) {
  return (
    <Link
      href={service.href}
      className="relative rounded-lg border bg-white p-6 shadow-sm transition hover:shadow"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{service.title}</h3>
        {locked && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-600">
            로그인 필요
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-500">{service.desc}</p>
    </Link>
  );
}
