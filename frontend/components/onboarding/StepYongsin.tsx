"use client";

// [용신확정] 만세력을 계산해 용신 후보를 보여주고, 과거 경험 문항(CalibrationPanel)으로 확정한다.
// 스킵 가능 — 스킵 시 유력 후보(yongsin_analysis.final.yongsin)를 미확정 상태로 사용한다.
// 간지·용신 계산은 모두 백엔드 엔진이 수행한다(프론트는 표시·전달만).

import { useEffect, useState } from "react";
import { CalibrationPanel, YongsinPanel } from "@/components/manse/CalibrationPanel";
import { calculateManse, todayISO } from "@/lib/api";
import type { AnswerMap } from "@/lib/calibration";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

interface Props {
  profile: Profile;
  // 확정/유력 용신을 상위(위저드)로 전달. confirmed=true면 검증 확정.
  onYongsin: (element: string | null, confirmed: boolean) => void;
  // 편집 진입 시 이미 등록된(DB 확정) 용신 — 있으면 등록 상태를 보존하고 표시한다.
  initialYongsin?: string | null;
  initialConfirmed?: boolean;
}

export function StepYongsin({
  profile,
  onYongsin,
  initialYongsin = null,
  initialConfirmed = false,
}: Props) {
  const [result, setResult] = useState<ManseResult | null>(null);
  const [calibration, setCalibration] = useState<CalibrationResult | null>(null);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [error, setError] = useState<string | null>(null);
  const [referenceDate] = useState(() => todayISO());

  useEffect(() => {
    calculateManse(profile, referenceDate)
      .then((r) => {
        setResult(r);
        // 이미 등록(확정)된 경우엔 그 상태를 보존한다 — 마운트가 false로 덮어쓰면 저장 시
        // confirmed_yongsin이 지워지는 데이터 손실이 생긴다. 미등록일 때만 유력 후보를 기본값으로.
        if (!initialConfirmed) {
          const lead = (r.yongsin_analysis.final.yongsin ?? null) as string | null;
          onYongsin(lead, false);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "계산 실패"));
    // onYongsin/profile은 마운트 1회 계산 의도라 의존성에서 제외.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referenceDate]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!result) return <p className="text-sm text-gray-500">사주 계산 중…</p>;

  return (
    <div className="space-y-3">
      <YongsinPanel
        result={result}
        calibration={calibration}
        confirmedYongsin={initialConfirmed ? initialYongsin : null}
      />
      <CalibrationPanel
        result={result}
        profile={profile}
        referenceDate={referenceDate}
        initialAnswers={answers}
        submitted={calibration !== null}
        registered={initialConfirmed && calibration === null}
        onResult={(r, a) => {
          setCalibration(r);
          setAnswers(a);
          const lead = (result.yongsin_analysis.final.yongsin ?? null) as string | null;
          onYongsin(r.final_yongsin ?? lead, true);
        }}
      />
      <p className="text-xs text-gray-400">
        과거 경험으로 확정하면 풀이 정확도가 올라갑니다. 건너뛰면 유력 후보를 사용하고, 나중에
        설정에서 다시 확정할 수 있어요.
      </p>
    </div>
  );
}
