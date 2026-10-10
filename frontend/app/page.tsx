"use client";

// 랜딩 — 무료(일주별 오늘의 운세·만세력·간지달력) / 로그인 전용(테마사주·AI상담) 구분.
// 상단 소개 히어로(제목·설명·로그인 버튼)는 공간만 차지해 제거했다(화면수정안 2026-10-10).
// 로그인·사주목록 진입은 GNB 드로어가 담당한다.

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
      <Section
        title="무료"
        subtitle="로그인 없이 이용 가능"
        lead={<DailyHomeCard />} // 무료 영역 최상단 가로 전체 — 일주별 오늘의 운세 (PRD UI/UX 1항)
      >
        {FREE.map((s) => (
          <ServiceCard key={s.href} service={s} locked={false} />
        ))}
      </Section>

      <Section title="로그인 전용" subtitle="여러 사주 저장 · 테마사주 · AI상담">
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
  lead,
  children,
}: {
  title: string;
  subtitle: string;
  // 카드 그리드 위에 가로 전체로 렌더할 리드 블록(예: 일주별 오늘의 운세)
  lead?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
        <span className="text-xs text-gray-400">{subtitle}</span>
      </div>
      {lead && <div className="mb-4">{lead}</div>}
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
