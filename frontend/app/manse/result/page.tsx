"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalibrationPanel, YongsinPanel } from "@/components/manse/CalibrationPanel";
import {
  BirthSummaryBar,
  DistributionPanel,
  GeokgukPanel,
  LuckPanel,
  QuickSummaryBar,
  SinsalPanel,
  StrengthPanel,
  StructurePanel,
  TrueSolarTimeCard,
} from "@/components/manse/Panels";
import { PillarBoard } from "@/components/manse/PillarBoard";
import { calculateManse } from "@/lib/api";
import { clearProfile, loadProfile } from "@/lib/storage";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

export default function ManseResultPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [result, setResult] = useState<ManseResult | null>(null);
  const [calibration, setCalibration] = useState<CalibrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfile().then((p) => {
      if (!p) {
        router.replace("/manse");
        return;
      }
      setProfile(p);
      calculateManse(p)
        .then(setResult)
        .catch((e) => setError(e instanceof Error ? e.message : "계산 실패"));
    });
  }, [router]);

  const reset = async () => {
    await clearProfile();
    router.replace("/manse");
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
      <QuickSummaryBar result={result} />
      <StructurePanel result={result} />
      <StrengthPanel result={result} />
      <DistributionPanel result={result} />
      <GeokgukPanel result={result} />

      <YongsinPanel result={result} calibration={calibration} />
      <CalibrationPanel result={result} profile={profile} onResult={setCalibration} />

      <LuckPanel result={result} />
      <SinsalPanel result={result} />
    </div>
  );
}
