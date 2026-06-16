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
import { StepShell } from "@/components/onboarding/StepShell";
import { StepYongsin } from "@/components/onboarding/StepYongsin";
import { profileToBasic, profileToBirthDTO, summaryToProfile } from "@/lib/subject-mapping";
import {
  createSubject,
  getPersona,
  getProfile,
  getSubject,
  saveProfile,
  savePersona,
  updateSubject,
} from "@/lib/subjects";
import { saveProfile as saveLocalProfile } from "@/lib/storage";
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
          setLoaded(true);
        })
        .catch((e) => {
          setError(e instanceof Error ? e.message : "불러오기 실패");
          setLoaded(true);
        });
    }
  }, [mode, subjectId]);

  const total = mode === "oneoff" ? 1 : 4;

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
      const birth = profileToBirthDTO(d.profile);
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
