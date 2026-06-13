"use client";

// [물상해석] 직업(O01~O18)·거주 지역·혼인상태. 전 필드 선택(스킵 가능, 설정에서 편집).
// docs/11 3장 닫힌 분류만 사용. 부재로 기능을 차단하지 않는다.

import { EMPLOYMENT_FORMS, MARITAL_STATUSES, OCCUPATIONS } from "@/lib/onboarding-constants";
import type { ExtendedProfile } from "@/lib/types";

interface Props {
  value: ExtendedProfile;
  onChange: (v: ExtendedProfile) => void;
}

export function StepMulsang({ value, onChange }: Props) {
  const occ = value.occupation ?? null;
  const res = value.residence ?? null;

  return (
    <div className="space-y-5 text-sm">
      <div>
        <span className="mb-1 block font-medium">현재 직업</span>
        <select
          value={occ?.category_id ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              occupation: e.target.value
                ? { category_id: e.target.value, employment_form: occ?.employment_form ?? null }
                : null,
            })
          }
          className="w-full rounded border px-2 py-1.5"
        >
          <option value="">선택 안 함</option>
          {OCCUPATIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        {occ && (
          <select
            value={occ.employment_form ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                occupation: {
                  ...occ,
                  employment_form: (e.target.value || null) as typeof occ.employment_form,
                },
              })
            }
            className="mt-2 w-full rounded border px-2 py-1.5"
          >
            <option value="">고용형태(선택)</option>
            {EMPLOYMENT_FORMS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        )}
      </div>

      <div>
        <span className="mb-1 block font-medium">현재 거주 지역</span>
        <input
          value={res?.region ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              residence: e.target.value ? { region: e.target.value } : null,
            })
          }
          placeholder="예: 서울특별시 강남구 (택일·방위 질문에 사용)"
          className="w-full rounded border px-2 py-1.5"
        />
      </div>

      <div>
        <span className="mb-1 block font-medium">현재 혼인 상태</span>
        <div className="flex flex-wrap gap-2">
          {MARITAL_STATUSES.map((m) => {
            const active = value.marital_status === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() =>
                  onChange({ ...value, marital_status: active ? null : m })
                }
                className={`rounded-full border px-3 py-1 ${
                  active ? "border-gray-800 bg-gray-800 text-white" : "text-gray-600"
                }`}
              >
                {m}
              </button>
            );
          })}
        </div>
      </div>

      <p className="text-xs text-gray-400">
        입력하지 않아도 모든 기능을 이용할 수 있어요. 직업·거주는 발현 형태와 택일 정밀도에만
        반영됩니다.
      </p>
    </div>
  );
}
