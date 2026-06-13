"use client";

// [사주입력] 별명(비식별 라벨) + 생년월일시 + 출생지. BirthForm을 재사용하고 별명 입력을
// 폼 상단에 주입해 같은 제출로 처리한다. 별명은 2~10자(BasicProfile.display_name 규격).

import { useState } from "react";
import { BirthForm } from "@/components/manse/BirthForm";
import type { Profile } from "@/lib/types";

interface Props {
  initialProfile?: Profile;
  initialNickname?: string;
  onNext: (profile: Profile, nickname: string) => void;
}

export function StepBirth({ initialProfile, initialNickname, onNext }: Props) {
  const [nickname, setNickname] = useState(initialNickname ?? "");
  const [error, setError] = useState<string | null>(null);

  return (
    <BirthForm
      initial={initialProfile}
      heading={null}
      submitLabel="다음"
      onSubmit={(profile) => {
        const n = nickname.trim();
        if (n.length < 2 || n.length > 10) {
          setError("별명은 2~10자로 입력해 주세요.");
          return;
        }
        onNext(profile, n);
      }}
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
