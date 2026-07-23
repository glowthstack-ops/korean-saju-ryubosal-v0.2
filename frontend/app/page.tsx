"use client";

// 랜딩 — 사주목록 진입 + 무료(만세력·간지달력) / 로그인 전용(테마사주·AI상담) 구분.

import Link from "next/link";
import { DailyHomeCard } from "@/components/daily/DailyHomeCard";
import { useAuth } from "@/components/providers/AuthProvider";

interface Service {
  href: string;
  title: string;
  desc: string;
  paid?: boolean;
}

const FREE: Service[] = [
  {
    href: "/daily",
    title: "일주별 오늘의 운세",
    desc: "내 일주(태어난 날)의 오늘 흐름을 매일 아침 5초 만에 확인하세요. 금전·연애·좋은소식 TOP5 일주도 함께 보여드려요.",
  },
  {
    href: "/manse",
    title: "만세력",
    desc: "생년월일시만 입력하면 내 사주 명식과 대운·세운·월운 흐름을 한눈에 볼 수 있어요. 간단한 과거 확인으로 나에게 필요한 기운(용신)까지 찾아드려요.",
  },
  {
    href: "/calendar",
    title: "간지달력",
    desc: "오늘과 앞으로의 날짜별 간지·절기를 달력으로 넘겨볼 수 있어요. 날을 잡기 전에 그날의 기운을 미리 확인해 보세요.",
  },
];

const PAID: Service[] = [
  {
    href: "/themes",
    title: "테마사주",
    desc: "인생 총운부터 연애·직장·금전까지, 궁금한 주제를 골라 책처럼 읽는 상세 풀이를 받아보세요. PDF로 저장해 두고두고 볼 수 있어요.",
    paid: true,
  },
  {
    href: "/chat",
    title: "AI채팅상담",
    desc: "'이직은 언제가 좋을까?' 같은 궁금증을 바로 물어보세요. 내 사주와 운의 근거를 짚어 가며 대화로 풀어드려요.",
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
          생년월일시만 입력하면 내 사주 명식부터 지금 흐르는 운, 주제별 깊은 풀이까지 한곳에서 볼 수
          있어요. 사주와 운의 계산은 정해진 명리 규칙대로 정확하게 하고, AI는 그 결과를 알기 쉬운
          말로 풀어드립니다.
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

      {/* 무료 영역 최상단 가로 전체 카드 — 일주별 오늘의 운세 (PRD UI/UX 1항) */}
      <DailyHomeCard />

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
