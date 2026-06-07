"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalibrationPanel, YongsinPanel } from "@/components/manse/CalibrationPanel";
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
      <TrueSolarTimeCard result={result} />
      <PillarBoard result={result} />
      <StructurePanel result={result} />
      <SinsalPanel result={result} />
      <DistributionPanel result={result} />
      <GeokgukPanel result={result} />
      <StrengthPanel result={result} />

      <YongsinPanel
        result={result}
        calibration={calibration}
        onRedo={() => setCalibration(null)}
      />
      <CalibrationPanel
        result={result}
        profile={profile}
        referenceDate={referenceDate}
        onResult={onCalibrationResult}
        initialAnswers={savedAnswers}
        submitted={calibration !== null}
      />

      <LuckPanel result={result} profile={profile} />
    </div>
  );
}
