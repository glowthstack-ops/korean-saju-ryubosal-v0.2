"use client";

// 설정 — 페르소나(계정 전역)와 물상해석(사주별)을 나중에 편집·삭제한다.

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { StepMulsang } from "@/components/onboarding/StepMulsang";
import { StepPersona } from "@/components/onboarding/StepPersona";
import { profileToBasic, summaryToProfile } from "@/lib/subject-mapping";
import {
  deleteExtendedField,
  getPersona,
  getProfile,
  getSubject,
  listSubjects,
  savePersona,
  saveProfile,
} from "@/lib/subjects";
import {
  DEFAULT_PERSONA,
  type ExtendedProfile,
  type PersonaConfig,
  type SubjectSummary,
} from "@/lib/types";

export default function SettingsPage() {
  const { ready, isLoggedIn } = useAuth();
  const [persona, setPersona] = useState<PersonaConfig>(DEFAULT_PERSONA);
  const [personaSaved, setPersonaSaved] = useState(false);
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [extended, setExtended] = useState<ExtendedProfile>({});
  const [mulsangSaved, setMulsangSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn) return;
    getPersona().then(setPersona).catch(() => {});
    listSubjects().then(setSubjects).catch(() => {});
  }, [isLoggedIn]);

  useEffect(() => {
    if (!activeId) return;
    getProfile(activeId)
      .then((p) => setExtended(p.extended ?? {}))
      .catch(() => setExtended({}));
  }, [activeId]);

  async function savePersonaNow() {
    setError(null);
    try {
      await savePersona(persona);
      setPersonaSaved(true);
      setTimeout(() => setPersonaSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    }
  }

  async function saveMulsang() {
    if (!activeId) return;
    setError(null);
    try {
      const [subj, prof] = await Promise.all([getSubject(activeId), getProfile(activeId)]);
      const profile = summaryToProfile(subj);
      await saveProfile(activeId, {
        basic: profileToBasic(profile, subj.label.slice(0, 10)),
        extended: Object.keys(extended).length ? extended : null,
        confirmed_yongsin: prof.confirmed_yongsin,
      });
      setMulsangSaved(true);
      setTimeout(() => setMulsangSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    }
  }

  async function clearField(field: string) {
    if (!activeId) return;
    await deleteExtendedField(activeId, field).catch(() => {});
    const p = await getProfile(activeId);
    setExtended(p.extended ?? {});
  }

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;
  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">설정</h1>
        <p className="mt-2 text-sm text-gray-600">
          설정은 로그인 후 이용할 수 있어요. 좌측 메뉴(☰)에서 로그인해 주세요.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-red-500">{error}</p>}

      <section className="space-y-3 rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-lg font-bold">페르소나 (계정 전체 공통)</h1>
        <StepPersona value={persona} onChange={setPersona} />
        <button onClick={savePersonaNow} className="rounded bg-gray-900 px-4 py-2 text-sm text-white">
          {personaSaved ? "저장됨 ✓" : "페르소나 저장"}
        </button>
      </section>

      <section className="space-y-3 rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-lg font-bold">물상 해석 (사주별)</h1>
        {subjects.length === 0 ? (
          <p className="text-sm text-gray-500">등록된 사주가 없어요.</p>
        ) : (
          <>
            <select
              value={activeId ?? ""}
              onChange={(e) => setActiveId(e.target.value || null)}
              className="w-full rounded border px-2 py-1.5 text-sm"
            >
              <option value="">사주 선택</option>
              {subjects.map((s) => (
                <option key={s.subject_id} value={s.subject_id}>
                  {s.label} ({s.birth.birth_date})
                </option>
              ))}
            </select>

            {activeId && (
              <>
                <StepMulsang value={extended} onChange={setExtended} />
                <div className="flex flex-wrap gap-2 text-xs">
                  {(["occupation", "residence", "marital_status", "children"] as const).map((f) =>
                    extended[f] ? (
                      <button
                        key={f}
                        onClick={() => clearField(f)}
                        className="rounded border border-red-200 px-2 py-1 text-red-500"
                      >
                        {f} 삭제
                      </button>
                    ) : null,
                  )}
                </div>
                <button
                  onClick={saveMulsang}
                  className="rounded bg-gray-900 px-4 py-2 text-sm text-white"
                >
                  {mulsangSaved ? "저장됨 ✓" : "물상 저장"}
                </button>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
