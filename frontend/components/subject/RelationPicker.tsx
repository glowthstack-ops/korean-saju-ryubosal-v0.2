"use client";

// 명식 카드의 '나와의 관계' 설정 시트 — 관계 17종 선택 + 호칭 별칭('신랑', '우리 딸') 입력.
// '본인'은 계정에 1명: 다른 사주가 이미 본인이면 경고하고, 저장 시 서버가 그 사주를 '관계 미설정'으로 내린다.

import { useState } from "react";
import { RELATION_OPTIONS, relationLabel } from "@/lib/relations";
import type { SubjectSummary } from "@/lib/types";

interface Props {
  subject: SubjectSummary;
  others: SubjectSummary[]; // 같은 계정의 다른 사주(본인 충돌 안내용)
  saving?: boolean;
  onSave: (relation: string | null, aliases: string[]) => void;
  onClose: () => void;
}

export function RelationPicker({ subject, others, saving, onSave, onClose }: Props) {
  const [relation, setRelation] = useState<string | null>(subject.relation_to_user);
  const [aliasText, setAliasText] = useState(subject.aliases.join(", "));
  const currentSelf = others.find((o) => o.relation_to_user === "self");
  const selfConflict = relation === "self" && currentSelf !== undefined;
  const aliases = aliasText
    .split(/[,，\s]+/)
    .map((a) => a.trim())
    .filter((a) => a.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <button type="button" aria-label="닫기" className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-800">
            {subject.label} · 나와의 관계
            <span className="ml-2 text-xs font-normal text-gray-400">현재 {relationLabel(subject)}</span>
          </h2>
          <button type="button" onClick={onClose} aria-label="닫기" className="rounded p-1 text-gray-400 hover:bg-gray-100">
            ✕
          </button>
        </div>
        <p className="mb-2 text-xs text-gray-500">
          이 사주가 나에게 어떤 관계인지 고르세요. 채팅에서 &ldquo;남편은&rdquo;처럼 부르면 이 설정으로 찾아요.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {RELATION_OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => setRelation(o.key)}
              className={`rounded-full border px-2.5 py-1 text-xs ${
                relation === o.key
                  ? "border-indigo-400 bg-indigo-50 font-medium text-indigo-700"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {o.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setRelation(null)}
            className={`rounded-full border px-2.5 py-1 text-xs ${
              relation === null ? "border-gray-400 bg-gray-100 font-medium text-gray-700" : "text-gray-400 hover:bg-gray-50"
            }`}
          >
            미설정
          </button>
        </div>
        {selfConflict && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            본인은 한 명만 둘 수 있어요. 저장하면 &lsquo;{currentSelf.label}&rsquo;은(는) 관계 미설정으로 바뀌어요.
          </p>
        )}
        <label className="mt-3 block text-xs text-gray-600">
          호칭 별칭 (쉼표로 구분, 선택)
          <input
            value={aliasText}
            onChange={(e) => setAliasText(e.target.value)}
            placeholder="예: 신랑, 우리 딸, 1호"
            className="mt-1 w-full rounded border px-2 py-1.5 text-sm"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border px-3 py-1.5 text-sm text-gray-600">
            취소
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => onSave(relation, aliases)}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:bg-gray-300"
          >
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
