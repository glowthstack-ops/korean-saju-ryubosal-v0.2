"use client";

// 온보딩 위저드 — [사주입력]→[용신확정]→[물상해석]→[페르소나]. 용신/물상/페르소나는 스킵 가능.
// mode=add(신규)·edit(수정)·oneoff(비로그인 1회성). add/edit는 백엔드 저장, oneoff는 IndexedDB.
// 페르소나는 계정 전역(account_settings)에 저장한다(사주별 아님).

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { StepBirth } from "@/components/onboarding/StepBirth";
import { StepMulsang } from "@/components/onboarding/StepMulsang";
import { StepPersona } from "@/components/onboarding/StepPersona";
import { StepRealityCalibration } from "@/components/onboarding/StepRealityCalibration";
import { StepShell } from "@/components/onboarding/StepShell";
import { StepYongsin } from "@/components/onboarding/StepYongsin";
import {
  profileToBasic, profileToBirthDTO, subjectEotPreference, summaryToProfile,
} from "@/lib/subject-mapping";
import {
  createSubject,
  getPersona,
  getProfile,
  getSubject,
  saveProfile,
  savePersona,
  updateSubject,
} from "@/lib/subjects";
import { loadEotPreference, saveProfile as saveLocalProfile } from "@/lib/storage";
import { DEFAULT_PERSONA, type ExtendedProfile, type PersonaConfig, type Profile } from "@/lib/types";

type Mode = "add" | "edit" | "oneoff";

interface Draft {
  profile: Profile | null;
  nickname: string;
  yongsin: string | null;
  yongsinConfirmed: boolean;
  extended: ExtendedProfile;
  persona: PersonaConfig;
}

const EMPTY: Draft = {
  profile: null,
  nickname: "",
  yongsin: null,
  yongsinConfirmed: false,
  extended: {},
  persona: DEFAULT_PERSONA,
};

export function Wizard({ mode, subjectId, next }: { mode: Mode; subjectId?: string; next: string }) {
  const router = useRouter();
  const { setSelected } = useSelectedSubject();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loaded, setLoaded] = useState(mode === "add" || mode === "oneoff");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 신규 등록 완료 후 현실 캘리브레이션(스킵 가능) 단계에서 쓸 새 subject id.
  const [createdSubjectId, setCreatedSubjectId] = useState<string | null>(null);
  // 균시차는 사주별 속성(데굴님 확정 2026-07-13) — edit 는 저장값 보존, add 는 기기 토글 시드.
  // null 이면 미로드(add/oneoff) → 저장 시 loadEotPreference() 사용.
  const [storedEot, setStoredEot] = useState<boolean | null>(null);

  // add(로그인): 계정 페르소나를 불러와 편집 기본값으로. edit: 사주·프로필·페르소나 프리필.
  useEffect(() => {
    if (mode === "add") {
      getPersona()
        .then((p) => setDraft((d) => ({ ...d, persona: p })))
        .catch(() => {});
      return;
    }
    if (mode === "edit" && subjectId) {
      Promise.all([getSubject(subjectId), getProfile(subjectId), getPersona()])
        .then(([subj, prof, persona]) => {
          setDraft({
            profile: summaryToProfile(subj),
            nickname: subj.label,
            yongsin: prof.confirmed_yongsin,
            yongsinConfirmed: prof.confirmed_yongsin !== null,
            extended: prof.extended ?? {},
            persona,
          });
          setStoredEot(subjectEotPreference(subj)); // 수정 저장 시 사주별 균시차 보존
          setLoaded(true);
        })
        .catch((e) => {
          setError(e instanceof Error ? e.message : "불러오기 실패");
          setLoaded(true);
        });
    }
  }, [mode, subjectId]);

  // 신규(add)는 마지막에 현실 캘리브레이션 단계(step 4)를 더 둔다. edit/oneoff는 기존 그대로.
  const total = mode === "oneoff" ? 1 : mode === "add" ? 5 : 4;

  async function finish(d: Draft) {
    if (!d.profile) return;
    setSaving(true);
    setError(null);
    try {
      if (mode === "oneoff") {
        await saveLocalProfile(d.profile);
        router.push(next);
        return;
      }
      // 균시차를 birth에 영속화(사주별 속성) — 챗·리포트·간지달력이 같은 시주 기준을 쓴다.
      // edit 는 저장된 사주별 값을 보존(기기 토글로 덮지 않음), add 는 기기 토글을 시드로.
      const birth = profileToBirthDTO(d.profile, {
        apply_equation_of_time: storedEot ?? loadEotPreference(),
      });
      const payload = {
        kind: "self" as const,
        label: d.nickname,
        birth,
        gender: d.profile.gender,
      };
      const subj =
        mode === "edit" && subjectId
          ? await updateSubject(subjectId, payload)
          : await createSubject(payload);
      await saveProfile(subj.subject_id, {
        basic: profileToBasic(d.profile, d.nickname),
        extended: Object.keys(d.extended).length ? d.extended : null,
        confirmed_yongsin: d.yongsinConfirmed ? d.yongsin : null,
      });
      await savePersona(d.persona);
      setSelected({ subjectId: subj.subject_id, label: subj.label });
      // 신규 등록: 마지막에 현실 캘리브레이션(스킵 가능) 단계를 제시. edit는 바로 이동.
      if (mode === "add") {
        setCreatedSubjectId(subj.subject_id);
        setSaving(false);
        setStep(4);
        return;
      }
      router.push(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
      setSaving(false);
    }
  }

  if (!loaded) return <p className="text-sm text-gray-500">불러오는 중…</p>;
  if (saving) return <p className="text-sm text-gray-500">저장 중…</p>;

  // 0 — 사주입력(별명+생년월일시)
  if (step === 0) {
    return (
      <StepShell step={0} total={total} title="사주 입력" desc="별명과 생년월일시·출생지를 입력하세요.">
        <StepBirth
          initialProfile={draft.profile ?? undefined}
          initialNickname={draft.nickname}
          onNext={(profile, nickname) => {
            const d = { ...draft, profile, nickname };
            setDraft(d);
            if (mode === "oneoff") finish(d);
            else setStep(1);
          }}
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
      </StepShell>
    );
  }

  // 1 — 용신확정(스킵 가능)
  if (step === 1 && draft.profile) {
    return (
      <StepShell
        step={1}
        total={total}
        title="용신 확정"
        desc="과거 경험으로 용신을 확정하면 풀이가 정확해져요. 건너뛰면 유력 후보를 사용합니다."
        canSkip
        onSkip={() => setStep(2)}
        onBack={() => setStep(0)}
      >
        <StepYongsin
          profile={draft.profile}
          initialYongsin={draft.yongsin}
          initialConfirmed={draft.yongsinConfirmed}
          onYongsin={(element, confirmed) =>
            setDraft((d) => ({ ...d, yongsin: element, yongsinConfirmed: confirmed }))
          }
        />
        <button
          onClick={() => setStep(2)}
          className="mt-2 w-full rounded bg-gray-900 py-2 text-sm text-white"
        >
          다음
        </button>
      </StepShell>
    );
  }

  // 2 — 물상해석(스킵 가능)
  if (step === 2) {
    return (
      <StepShell
        step={2}
        total={total}
        title="물상 해석"
        desc="직업·거주·혼인 정보(선택). 입력하면 발현 형태·택일 정밀도가 올라갑니다."
        canSkip
        onSkip={() => setStep(3)}
        onBack={() => setStep(1)}
      >
        <StepMulsang value={draft.extended} onChange={(v) => setDraft((d) => ({ ...d, extended: v }))} />
        <button
          onClick={() => setStep(3)}
          className="mt-2 w-full rounded bg-gray-900 py-2 text-sm text-white"
        >
          다음
        </button>
      </StepShell>
    );
  }

  // 4 — 현실 신호 캘리브레이션(신규 등록 완료 후, 스킵 가능) — 저장된 새 subject 기준.
  if (step === 4 && createdSubjectId) {
    return (
      <StepShell
        step={4}
        total={total}
        title="현실 신호 캘리브레이션"
        desc="과거에 실제 있었던 일을 알려주면 이 사주에 맞춰 풀이 정확도가 올라갑니다. 건너뛰어도 됩니다."
        canSkip
        onSkip={() => router.push(next)}
      >
        <StepRealityCalibration subjectId={createdSubjectId} onDone={() => router.push(next)} />
      </StepShell>
    );
  }

  // 3 — 페르소나(스킵 가능, 계정 전역)
  return (
    <StepShell
      step={3}
      total={total}
      title="페르소나 설정"
      desc="상담가 말투·난이도(계정 전체 공통). 건너뛰면 기본값으로 저장됩니다."
      canSkip
      onSkip={() => finish(draft)}
      onBack={() => setStep(2)}
    >
      <StepPersona value={draft.persona} onChange={(v) => setDraft((d) => ({ ...d, persona: v }))} />
      <button
        onClick={() => finish(draft)}
        className="mt-2 w-full rounded bg-gray-900 py-2 text-sm text-white"
      >
        완료
      </button>
      {error && <p className="text-sm text-red-500">{error}</p>}
    </StepShell>
  );
}
