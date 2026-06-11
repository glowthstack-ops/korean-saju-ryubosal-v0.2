"use client";

// 대화형 통변 (v2.2 MVP UI) — 저장된 프로필로 /api/v2/chat 호출, thread_id로 멀티턴 유지.
// 엔진이 계산한 점수·간지를 LLM이 서술한 결과를 그대로 표시한다(프론트 가공 없음).

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { postChat } from "@/lib/api";
import { loadProfile } from "@/lib/storage";
import type { ChatApiResponse, Profile } from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  text: string;
  meta?: ChatApiResponse;
}

const SUGGESTIONS = [
  "올해 이직운 어때?",
  "내년 연애운은 어때?",
  "올해 재물운 좀 봐줘",
  "다음 달 이사하기 좋은 날짜 알려줘",
  "내 용신이 뭐야?",
];

function newThreadId(): string {
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function ChatPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileChecked, setProfileChecked] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId] = useState(newThreadId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadProfile()
      .then(setProfile)
      .finally(() => setProfileChecked(true));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(question: string) {
    if (!profile || busy || !question.trim()) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await postChat(profile, question, threadId);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.answer ?? "(응답 없음)", meta: res },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "호출 실패";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `오류: ${msg} — 잠시 후 다시 시도해 주세요.` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (!profileChecked) {
    return <p className="text-sm text-gray-500">프로필 확인 중…</p>;
  }
  if (!profile) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">대화형 통변</h1>
        <p className="mt-2 text-sm text-gray-600">
          먼저 만세력에서 생년월일시·출생지를 입력하면 그 사주로 대화할 수 있어요.
        </p>
        <Link
          href="/manse"
          className="mt-4 inline-block rounded bg-indigo-600 px-4 py-2 text-sm text-white"
        >
          만세력 입력하러 가기
        </Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg bg-white p-4 shadow-sm">
        <h1 className="text-xl font-bold">대화형 통변</h1>
        <p className="mt-1 text-xs text-gray-500">
          {profile.birthDate} {profile.timeUnknown ? "(시간 모름)" : profile.birthTime}{" "}
          · {profile.place.name} 사주 기준 · 같은 창에서는 대화 맥락이 이어집니다.
        </p>
      </section>

      <section className="min-h-[300px] space-y-3 rounded-lg bg-white p-4 shadow-sm">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">이렇게 물어보세요:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  className="rounded-full border px-3 py-1 text-xs text-gray-700 hover:bg-gray-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                m.role === "user"
                  ? "inline-block max-w-[85%] rounded-2xl bg-indigo-600 px-4 py-2 text-left text-sm text-white"
                  : "inline-block max-w-[95%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-4 py-3 text-sm text-gray-800"
              }
            >
              {m.text}
            </div>
            {m.meta && m.meta.status !== "answered" && (
              <p className="mt-1 text-xs text-amber-600">
                {m.meta.status === "too_broad" && "범위를 좁히면 바로 풀이해 드려요."}
                {m.meta.status === "need_subject" && "대상 확인이 필요해요."}
                {m.meta.status === "policy" && "정책 안내 응답입니다."}
              </p>
            )}
            {m.meta?.repeated && (
              <p className="mt-1 text-xs text-gray-400">같은 질문이 반복되어 다른 각도로 살펴볼게요.</p>
            )}
            {m.meta?.product_suggestion && (
              <p className="mt-1 text-xs text-gray-500">
                💡 {m.meta.product_suggestion.reason} ({m.meta.product_suggestion.note})
              </p>
            )}
          </div>
        ))}

        {busy && <p className="text-sm text-gray-400">통변 작성 중…</p>}
        <div ref={bottomRef} />
      </section>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="질문을 입력하세요 (예: 올해 이직운 어때?)"
          className="flex-1 rounded-lg border px-4 py-2 text-sm"
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          보내기
        </button>
      </form>
    </div>
  );
}
