"use client";

// [사주입력] 별명(비식별 라벨) + 생년월일시 + 출생지. BirthForm을 재사용하고 별명 입력을
// 폼 상단에 주입해 같은 제출로 처리한다. 별명은 2~10자(BasicProfile.display_name 규격).
// chooseNext(신규 등록 add 모드): "다음" 단일 버튼 대신 목적지 3버튼을 제공한다 —
// 테마사주/AI채팅은 즉시 저장 후 이동, 캘리브레이션은 용신확정→물상해석→페르소나→현실보정 진행.

import { useState } from "react";
import { BirthForm } from "@/components/manse/BirthForm";
import type { Profile } from "@/lib/types";

/** 신규 등록 사주입력 직후 선택지 — Wizard가 분기 처리한다. */
export type BirthNextAction = "theme" | "chat" | "calibrate";

const CHOICES: { value: BirthNextAction; label: string }[] = [
  { value: "theme", label: "테마사주 보기" },
  { value: "chat", label: "AI 채팅상담하기" },
  { value: "calibrate", label: "사주풀이 캘리브레이션하기" },
];

interface Props {
  initialProfile?: Profile;
  initialNickname?: string;
  /** true면 3버튼(테마/채팅/캘리브레이션) 선택형 — 신규 등록(add) 전용. */
  chooseNext?: boolean;
  onNext: (profile: Profile, nickname: string, action?: BirthNextAction) => void;
}

export function StepBirth({ initialProfile, initialNickname, chooseNext, onNext }: Props) {
  const [nickname, setNickname] = useState(initialNickname ?? "");
  const [error, setError] = useState<string | null>(null);

  return (
    <BirthForm
      initial={initialProfile}
      heading={null}
      submitLabel="다음"
      onSubmit={(profile, action) => {
        const n = nickname.trim();
        if (n.length < 2 || n.length > 10) {
          setError("별명은 2~10자로 입력해 주세요.");
          return;
        }
        onNext(profile, n, action as BirthNextAction | undefined);
      }}
      actions={
        chooseNext
          ? (disabled) => (
              <div className="space-y-2">
                {CHOICES.map((c) => (
                  <button
                    key={c.value}
                    type="submit"
                    name="action"
                    value={c.value}
                    disabled={disabled}
                    className="w-full rounded bg-gray-900 py-2 text-sm text-white disabled:bg-gray-400"
                  >
                    {c.label}
                  </button>
                ))}
                <p className="text-[11px] text-gray-400">
                  어떤 선택이든 사주는 저장됩니다. 캘리브레이션을 선택하면 용신확정·물상해석·페르소나·현실보정을
                  이어서 진행해 풀이 정확도를 높일 수 있어요.
                </p>
              </div>
            )
          : undefined
      }
    >
      <div>
        <span className="mb-1 block text-sm font-medium">별명</span>
        <input
          value={nickname}
          onChange={(e) => {
            setNickname(e.target.value);
            setError(null);
          }}
          placeholder="구분용 별명(예: 본인, 첫째, 신랑) 2~10자"
          className="w-full rounded border px-2 py-1 text-sm"
          maxLength={10}
        />
        {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
        <p className="mt-1 text-[11px] text-gray-400">
          개인 식별 정보가 아닌, 목록에서 구분하기 위한 별명입니다.
        </p>
      </div>
    </BirthForm>
  );
}
