"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalibrationPanel, YongsinPanel } from "@/components/manse/CalibrationPanel";
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
  clearProfile, loadCalibration, loadProfile, profileSig, saveCalibration,
} from "@/lib/storage";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

type AnswerMap = Record<string, { rating: string; events: string[] }>;

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
  const [savedAnswers, setSavedAnswers] = useState<AnswerMap>({});
  const [error, setError] = useState<string | null>(null);
  // 질문 생성/피드백 채점에 동일 기준일을 쓰도록 마운트 시 한 번 고정(자정·연 경계 안전).
  const [referenceDate] = useState(() => todayISO());

  useEffect(() => {
    loadProfile().then((p) => {
      if (!p) {
        router.replace("/manse");
        return;
      }
      setProfile(p);
      calculateManse(p, referenceDate)
        .then(async (r) => {
          setResult(r);
          // 저장된 검증 상태 복원: 명식(sig) 같으면 확정 결과 유지, 질문셋(chartId) 같으면 답변도 복원.
          const saved = await loadCalibration().catch(() => null);
          if (saved && saved.sig === profileSig(p)) {
            setCalibration(saved.result);
            if (saved.chartId === r.chart_id) setSavedAnswers(saved.answers ?? {});
          }
        })
        .catch((e) => setError(e instanceof Error ? e.message : "계산 실패"));
    });
  }, [router, referenceDate]);

  const reset = async () => {
    await clearProfile();
    router.replace("/manse");
  };

  // 검증 제출 시: 화면 반영 + localStorage 저장(reload 후에도 유지).
  const onCalibrationResult = (res: CalibrationResult, answers: AnswerMap) => {
    setCalibration(res);
    if (profile && result) {
      void saveCalibration({
        sig: profileSig(profile), chartId: result.chart_id, answers, result: res,
      });
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
        <TrueSolarTimeCard result={result} />
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
          onRedo={() => setCalibration(null)}
        />
      </div>
      <div id="sec-calibration" className="scroll-mt-4">
        <CalibrationPanel
          result={result}
          profile={profile}
          referenceDate={referenceDate}
          onResult={onCalibrationResult}
          initialAnswers={savedAnswers}
          submitted={calibration !== null}
        />
      </div>

      <div id="sec-luck" className="scroll-mt-4">
        <LuckPanel result={result} profile={profile} />
      </div>

      <FloatingToc items={TOC_ITEMS} />
    </div>
  );
}
