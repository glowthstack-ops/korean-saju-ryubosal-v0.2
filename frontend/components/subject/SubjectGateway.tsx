"use client";

// 대상 선택 게이트웨이 — 모든 서비스(만세력·테마·채팅)가 "누구의 사주인가"를 확정하는 1차 관문.
// 로그인 사용자의 사주목록에서 선택하거나 새 사주를 추가하고, 필요 시 동반자(궁합/관계)를 함께
// 고른다. 선택 결과는 전역 컨텍스트에 반영하고 onResolved로 호출자에게 전달한다.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useGnb } from "@/components/providers/GnbProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { InlinePartnerForm } from "@/components/subject/InlinePartnerForm";
import { SubjectCard } from "@/components/subject/SubjectCard";
import { RELATION_OPTIONS, themeRelationFromStored, type CompanionChoice } from "@/lib/themes";
import { hasRelation, relationLabel } from "@/lib/relations";
import { listSubjects } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

// 동반자 선택 정책: none=단독 / optional=상대 추가 선택 가능(내 명식만도 가능) / required=상대 필수.
type CompanionMode = "none" | "optional" | "required";

interface Props {
  /** 동반자(2번째 사주) 선택 정책. 미지정 시 requireCompanion로 호환. */
  companionMode?: CompanionMode;
  /** (레거시) 동반자 선택 강제 — companionMode 미지정 시 사용. */
  requireCompanion?: boolean;
  /** 추가 완료 후 돌아올 경로(온보딩 next). */
  returnTo: string;
  title?: string;
  onResolved: (primary: SubjectSummary, companion?: CompanionChoice) => void;
}

export function SubjectGateway({
  companionMode, requireCompanion, returnTo, title, onResolved,
}: Props) {
  const mode: CompanionMode = companionMode ?? (requireCompanion ? "required" : "none");
  const { ready, isLoggedIn } = useAuth();
  const { openGnb } = useGnb(); // 비로그인 안내의 [로그인] → 사이드바(계정 패널) 열기
  const { setSelected, setCompanion } = useSelectedSubject();
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [primary, setPrimary] = useState<SubjectSummary | null>(null);
  // 상대 카드 선택 뒤 '관계 확인' 단계(2026-10-15 데굴님 승인) — 등록 관계를 셀렉트에 미리 채우고
  // 사용자가 확인·변경한 뒤 시작한다. 종전엔 셀렉트가 카드 위에 있고 기본값이 '선택 안 함(일반
  // 궁합)'이라 등록 관계가 묵시적으로 쓰이는 것을 사용자가 알 수 없었다.
  const [pendingCompanion, setPendingCompanion] = useState<SubjectSummary | null>(null);
  // 상대와의 관계(사용자 명시 선택 또는 등록 관계 번역값) — 궁합(RP) 풀이 방향에 반영. null=일반 궁합.
  const [relationType, setRelationType] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn) {
      setSubjects([]);
      return;
    }
    listSubjects()
      .then(setSubjects)
      .catch((e) => setError(e instanceof Error ? e.message : "목록을 불러오지 못했습니다."));
  }, [isLoggedIn]);

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;

  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">{title ?? "사주 선택"}</h2>
        <p className="mt-2 text-sm text-gray-600">
          이 서비스는 로그인 후 이용할 수 있어요. 아이디·PIN으로 로그인하거나 새 계정을 만들어
          주세요. 같은 아이디·PIN이면 어느 기기에서나 사주목록이 이어집니다.
        </p>
        <button
          type="button"
          onClick={openGnb}
          className="mt-3 rounded bg-gray-800 px-3 py-1.5 text-sm text-white"
        >
          로그인
        </button>
      </section>
    );
  }

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (subjects === null) return <p className="text-sm text-gray-500">사주목록 불러오는 중…</p>;

  const addHref = `/onboarding?mode=add&next=${encodeURIComponent(returnTo)}`;

  // 관계 확인 단계 — 등록 상대를 고른 뒤, 어떤 관계로 풀이할지 보여 주고 확인받는다.
  if (mode !== "none" && primary && pendingCompanion) {
    const comp = pendingCompanion;
    const stored = hasRelation(comp) ? relationLabel(comp) : null;
    const storedMapped = themeRelationFromStored(comp.relation_to_user);
    const relationKo = RELATION_OPTIONS.find((r) => r.value === relationType)?.label ?? null;
    return (
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">관계 확인</h2>
        <div className="rounded-lg border bg-white p-4 text-sm shadow-sm">
          <p>
            <span className="text-gray-500">기준 사주</span>{" "}
            <span className="font-medium">{primary.label}</span>
          </p>
          <p className="mt-1">
            <span className="text-gray-500">상대</span>{" "}
            <span className="font-medium">{comp.label}</span>
            {stored && <span className="ml-1 text-xs text-purple-600">등록 관계: {stored}</span>}
          </p>
          <label className="mt-3 block">
            <span className="font-medium">{primary.label}님에게 {comp.label}님은 어떤 관계인가요?</span>
            <select
              value={relationType ?? ""}
              onChange={(e) => setRelationType(e.target.value || null)}
              className="mt-1.5 w-full rounded border px-2 py-1.5 text-sm"
            >
              <option value="">선택 안 함 (일반 궁합으로 풀이)</option>
              {RELATION_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-1.5 text-xs text-gray-500">
            {relationType && storedMapped && relationType === storedMapped
              ? `등록된 관계(${stored})에 맞춰 '${relationKo}' 방향으로 풀이해요. 다른 관계면 바꿔 주세요.`
              : relationType
                ? `'${relationKo}' 관계로 풀이해요. 연애 관계가 아니면 연애·결혼 풀이는 넣지 않아요.`
                : stored
                  ? `등록 관계(${stored})를 풀이에 쓸 수 없어 일반 궁합으로 풀이해요. 관계를 고르면 그에 맞게 풀이해요.`
                  : "관계를 고르면 그에 맞게 풀이해요. 비워 두면 일반 궁합이에요."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCompanion({ subjectId: comp.subject_id, label: comp.label });
            onResolved(primary, { mode: "registered", subject: comp, relationType });
          }}
          className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-700"
        >
          이 관계로 풀이 시작 →
        </button>
        <button
          type="button"
          onClick={() => setPendingCompanion(null)}
          className="text-xs text-gray-500 hover:underline"
        >
          ← 다른 상대 선택
        </button>
      </section>
    );
  }

  // 동반자 선택 단계(optional·required).
  if (mode !== "none" && primary) {
    const others = subjects.filter((s) => s.subject_id !== primary.subject_id);
    const optional = mode === "optional";
    return (
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">
          {optional ? "상대 선택 (선택)" : "동반자 선택"}
        </h2>
        <p className="text-sm text-gray-600">
          <span className="font-medium">{primary.label}</span>님과 함께 볼 상대를 골라 주세요.
          {optional && " 상대를 더하면 두 사람의 궁합·극복 전략까지 풀이합니다."}
        </p>
        {optional && (
          <button
            onClick={() => {
              setCompanion(null);
              onResolved(primary);
            }}
            className="w-full rounded-lg border border-indigo-300 bg-indigo-50 px-4 py-3 text-left text-sm font-medium text-indigo-700 hover:bg-indigo-100"
          >
            상대 없이 내 명식만으로 보기 →
          </button>
        )}
        {others.length === 0 ? (
          <p className="text-sm text-gray-500">
            등록된 다른 사주가 없어요. 아래에서 즉석으로 입력하거나{" "}
            <Link href={addHref} className="text-blue-600 hover:underline">
              동반자 사주 추가
            </Link>
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {others.map((s) => (
              <SubjectCard
                key={s.subject_id}
                subject={s}
                onSelect={(comp) => {
                  // 바로 시작하지 않고 관계 확인 단계로 — 등록 관계를 테마 어휘로 미리 채운다.
                  setPendingCompanion(comp);
                  setRelationType(themeRelationFromStored(comp.relation_to_user));
                }}
              />
            ))}
          </div>
        )}

        {/* 즉석 상대 입력(미등록) — 1회 궁합 분석용. */}
        <details className="rounded-lg border bg-gray-50 p-3">
          <summary className="cursor-pointer text-sm font-medium text-gray-700">
            상대 정보 즉석 입력 (등록 없이)
          </summary>
          <div className="mt-3">
            <InlinePartnerForm
              onSubmit={(label, birth, inlineRelation) => {
                setCompanion(null);
                onResolved(primary, { mode: "inline", label, birth, relationType: inlineRelation });
              }}
            />
          </div>
        </details>

        <button
          onClick={() => setPrimary(null)}
          className="text-xs text-gray-500 hover:underline"
        >
          ← 본인 사주 다시 선택
        </button>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title ?? "사주 선택"}</h2>
        <Link href={addHref} className="text-sm text-blue-600 hover:underline">
          + 새 사주
        </Link>
      </div>
      {subjects.length === 0 ? (
        <p className="rounded-lg bg-white p-6 text-sm text-gray-500 shadow-sm">
          등록된 사주가 없어요.{" "}
          <Link href={addHref} className="text-blue-600 hover:underline">
            새 사주 추가하기
          </Link>
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {subjects.map((s) => (
            <SubjectCard
              key={s.subject_id}
              subject={s}
              onSelect={(picked) => {
                setSelected({ subjectId: picked.subject_id, label: picked.label });
                if (mode !== "none") setPrimary(picked);
                else onResolved(picked);
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
