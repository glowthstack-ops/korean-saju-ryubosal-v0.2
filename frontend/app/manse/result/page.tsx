"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalibrationPanel, YongsinPanel } from "@/components/manse/CalibrationPanel";
import type { AnswerMap } from "@/lib/calibration";
import { FloatingToc, type TocItem } from "@/components/manse/FloatingToc";
import {
  BirthSummaryBar,
  DistributionPanel,
  GeokgukPanel,
  LuckPanel,
  SinsalPanel,
  StrengthPanel,
  StructurePanel,
  TrueSolarTimeCard,
} from "@/components/manse/Panels";
import { PillarBoard } from "@/components/manse/PillarBoard";
import { calculateManse, todayISO } from "@/lib/api";
import {
  clearProfile, loadCalibration, loadEotPreference, loadProfile, profileSig,
  saveCalibration, saveEotPreference,
} from "@/lib/storage";
import { subjectEotPreference, summaryToProfile } from "@/lib/subject-mapping";
import {
  getSubject,
  getSubjectYongsin,
  setSelectedSubjectId,
  setSubjectYongsin,
  updateSubject,
} from "@/lib/subjects";
import type {
  CalibrationResult, ManseResult, Profile, SubjectSummary,
} from "@/lib/types";

// ?subject=<id>(로그인 사주) 우선, 없으면 IndexedDB 1회성 프로필을 로드한다.
// 로그인 사주는 SubjectSummary 도 함께 반환한다 — 균시차가 사주별 속성(birth.time_options)이라
// 초기 토글 상태와 토글 변경 영속(updateSubject)에 원본 레코드가 필요하다.
async function resolveProfile(): Promise<
  { profile: Profile; summary: SubjectSummary | null } | null
> {
  const subjectId =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("subject")
      : null;
  if (subjectId) {
    try {
      const summary = await getSubject(subjectId);
      setSelectedSubjectId(subjectId);  // 간지달력 등 subject 비지정 화면의 오버레이 기준으로 기억
      return { profile: summaryToProfile(summary), summary };
    } catch {
      return null;
    }
  }
  const profile = await loadProfile();
  return profile ? { profile, summary: null } : null;
}


// 우측 플로팅 목차 항목(섹션 id ↔ 표시 라벨). 렌더 순서와 일치시킨다.
const TOC_ITEMS: TocItem[] = [
  { id: "sec-truesolar", label: "진태양시" },
  { id: "sec-pillar", label: "사주 원국" },
  { id: "sec-structure", label: "형충회합" },
  { id: "sec-sinsal", label: "신살·길성" },
  { id: "sec-distribution", label: "오행·십성 분포" },
  { id: "sec-geokguk", label: "격국" },
  { id: "sec-strength", label: "신강·신약" },
  { id: "sec-yongsin", label: "용신" },
  { id: "sec-calibration", label: "용신 검증" },
  { id: "sec-luck", label: "대운·세운·월운" },
];

export default function ManseResultPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [result, setResult] = useState<ManseResult | null>(null);
  const [calibration, setCalibration] = useState<CalibrationResult | null>(null);
  // '검증 다시 진행' 클릭 상태 — registered(등록 완료) 게이트를 건너뛰고 질문 폼을 바로 연다.
  const [redoRequested, setRedoRequested] = useState(false);
  // 로그인 사주 id + DB에 등록된 확정 용신 — 만세력 페이지·사주목록·수정 폼이 같은 값을 공유.
  const [subjectId, setSubjectId] = useState<string | null>(null);
  const [confirmedYongsin, setConfirmedYongsin] = useState<string | null>(null);
  const [savedAnswers, setSavedAnswers] = useState<AnswerMap>({});
  const [error, setError] = useState<string | null>(null);
  // 균시차 사용 토글(풀이 스타일에 따라 선택). 기본 사용. 끄면 진태양시에서 균시차를 제외해 재계산.
  // 로그인 사주 = 사주별 속성(birth.time_options, DB 영속 — 챗·리포트·간지달력 동일 기준),
  // 비로그인 = 기기 로컬 속성(localStorage). 데굴님 확정 2026-07-13.
  const [applyEoT, setApplyEoT] = useState(true);
  // 로그인 사주의 원본 레코드 — 토글 영속(updateSubject) 시 나머지 필드를 보존해 재전송.
  const [subjectSummary, setSubjectSummary] = useState<SubjectSummary | null>(null);
  // 질문 생성/피드백 채점에 동일 기준일을 쓰도록 마운트 시 한 번 고정(자정·연 경계 안전).
  const [referenceDate] = useState(() => todayISO());

  useEffect(() => {
    const sid =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("subject")
        : null;
    setSubjectId(sid);
    // 로그인 사주면 DB에서 확정 용신 + 검증 답변을 불러와 반영(교차 기기 수정 프리필).
    if (sid) {
      getSubjectYongsin(sid)
        .then((yd) => {
          setConfirmedYongsin(yd.confirmed_yongsin);
          const cal = yd.calibration;
          if (cal?.result) setCalibration(cal.result); // 확정 결과(패널 접힘·요약)
          if (cal?.answers) setSavedAnswers(cal.answers as AnswerMap); // 재검증 시 프리필
        })
        .catch(() => {});
    }
    resolveProfile().then((resolved) => {
      if (!resolved) {
        router.replace("/manse");
        return;
      }
      const p = resolved.profile;
      setProfile(p);
      setSubjectSummary(resolved.summary);
      // 초기 균시차: 로그인 사주는 저장된 사주별 속성, 비로그인은 기기 토글.
      const eot = resolved.summary
        ? subjectEotPreference(resolved.summary)
        : loadEotPreference();
      setApplyEoT(eot);
      calculateManse(p, referenceDate, { apply_equation_of_time: eot })
        .then(async (r) => {
          setResult(r);
          // 로컬(IndexedDB) 복원은 폴백이다 — 서버(getSubjectYongsin)가 값을 넣었으면 덮지 않고,
          // 서버에 없거나(pre-blob·비로그인·미저장) 사주 미지정일 때만 채운다(빈 값일 때만 채움).
          const saved = await loadCalibration().catch(() => null);
          if (saved && saved.sig === profileSig(p)) {
            setCalibration((prev) => prev ?? saved.result);
            if (saved.chartId === r.chart_id) {
              setSavedAnswers((prev) => (Object.keys(prev).length ? prev : (saved.answers ?? {})));
            }
          }
        })
        .catch((e) => setError(e instanceof Error ? e.message : "계산 실패"));
    });
  }, [router, referenceDate]);

  const reset = async () => {
    await clearProfile();
    router.replace("/manse");
  };

  // 균시차 토글: 즉시 재계산(진태양시·시주가 바뀔 수 있음). 미지정 옵션은 백엔드 기본값 유지.
  // 로그인 사주는 DB(birth.time_options)에 영속 — 챗·리포트가 같은 시주 기준을 쓴다.
  const toggleEoT = (value: boolean) => {
    setApplyEoT(value);
    if (subjectSummary && subjectId) {
      const birth = {
        ...subjectSummary.birth,
        time_options: {
          ...(subjectSummary.birth.time_options ?? {}),
          apply_equation_of_time: value,
        },
      };
      setSubjectSummary({ ...subjectSummary, birth });
      void updateSubject(subjectId, {
        kind: subjectSummary.kind,
        label: subjectSummary.label,
        birth,
        gender: subjectSummary.gender,
        relation_to_user: subjectSummary.relation_to_user,
        aliases: subjectSummary.aliases,
        is_minor: subjectSummary.is_minor,
        subscribed: subjectSummary.subscribed,
      }).catch(() => {
        /* 영속 실패해도 화면 재계산은 유지 — 다음 토글/저장에서 재시도 */
      });
    } else {
      saveEotPreference(value); // 비로그인: 기기 로컬 속성
    }
    if (!profile) return;
    calculateManse(profile, referenceDate, { apply_equation_of_time: value })
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : "계산 실패"));
  };

  // 검증 제출 시: 화면 반영 + localStorage 저장(reload 후에도 유지).
  const onCalibrationResult = (res: CalibrationResult, answers: AnswerMap) => {
    setRedoRequested(false); // 재검증 완료 — 다음 진입은 다시 요약(등록 완료) 뷰부터
    setCalibration(res);
    setSavedAnswers(answers); // 재검증(다시 진행) 시 방금 제출한 답변이 프리필되도록 유지
    if (profile && result) {
      void saveCalibration({
        sig: profileSig(profile), chartId: result.chart_id, answers, result: res,
      });
    }
    // 검증 확정 용신 + 답변을 DB에도 영속 — 사주목록·수정 폼 공유 + 교차 기기 재검증 프리필.
    if (subjectId && res.final_yongsin) {
      setConfirmedYongsin(res.final_yongsin);
      void setSubjectYongsin(subjectId, res.final_yongsin, { answers, result: res }).catch(
        () => {},
      );
    }
  };

  if (error) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-red-600">{error} (백엔드 API 실행 여부 확인)</p>
        <button onClick={reset} className="rounded border px-3 py-1 text-sm">등록 정보 초기화</button>
      </div>
    );
  }
  if (!result || !profile) return <p className="text-sm text-gray-500">만세력 계산 중…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">만세력 정보</h1>
        <button onClick={reset} className="rounded border px-3 py-1 text-xs hover:bg-gray-100">
          등록 정보 초기화
        </button>
      </div>

      <BirthSummaryBar result={result} />
      <div id="sec-truesolar" className="scroll-mt-4">
        <TrueSolarTimeCard
          result={result}
          applyEquationOfTime={applyEoT}
          onToggleEquationOfTime={toggleEoT}
        />
      </div>
      <div id="sec-pillar" className="scroll-mt-4">
        <PillarBoard result={result} />
      </div>
      <div id="sec-structure" className="scroll-mt-4">
        <StructurePanel result={result} />
      </div>
      <div id="sec-sinsal" className="scroll-mt-4">
        <SinsalPanel result={result} />
      </div>
      <div id="sec-distribution" className="scroll-mt-4">
        <DistributionPanel result={result} />
      </div>
      <div id="sec-geokguk" className="scroll-mt-4">
        <GeokgukPanel result={result} />
      </div>
      <div id="sec-strength" className="scroll-mt-4">
        <StrengthPanel result={result} />
      </div>

      <div id="sec-yongsin" className="scroll-mt-4">
        <YongsinPanel
          result={result}
          calibration={calibration}
          confirmedYongsin={confirmedYongsin}
          onRedo={() => {
            // '검증 다시 진행' 한 번으로 곧장 질문 폼까지 — '용신 등록 완료 → 다시 검증'
            // 중간 게이트를 건너뛴다(이중 단계 제거, 2026-07-03 데굴님 지적). registered
            // 게이트는 다른 기기에서 확정한 사용자의 '초기 진입' 전용으로만 남는다.
            setCalibration(null);
            setRedoRequested(true);
          }}
        />
      </div>
      <div id="sec-calibration" className="scroll-mt-4">
        <CalibrationPanel
          result={result}
          profile={profile}
          referenceDate={referenceDate}
          timeOptions={{ apply_equation_of_time: applyEoT }}
          onResult={onCalibrationResult}
          initialAnswers={savedAnswers}
          submitted={calibration !== null}
          registered={!!confirmedYongsin && calibration === null && !redoRequested}
        />
      </div>

      <div id="sec-luck" className="scroll-mt-4">
        <LuckPanel
          result={result}
          profile={profile}
          timeOptions={{ apply_equation_of_time: applyEoT }}
          calibration={calibration}
        />
      </div>

      <FloatingToc items={TOC_ITEMS} />
    </div>
  );
}
