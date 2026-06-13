"use client";

// AI채팅상담 (로그인 전용) — 선택된 사주로 /api/v2/chat 호출, 계정 페르소나(문체) 적용,
// thread_id로 멀티턴 유지. 엔진이 계산한 점수·간지를 LLM이 서술한 결과를 그대로 표시한다.

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@/components/providers/AuthProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { SubjectGateway } from "@/components/subject/SubjectGateway";
import { deleteChatThread, getChatThread, listChatThreads, postChat } from "@/lib/api";
import { summaryToProfile } from "@/lib/subject-mapping";
import { getPersona, getSubject, listSubjects } from "@/lib/subjects";
import type {
  ChatApiResponse,
  ChatThreadSummary,
  PersonaConfig,
  Profile,
  SubjectSummary,
} from "@/lib/types";

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
  const { ready, isLoggedIn } = useAuth();
  const { selected, setSelected } = useSelectedSubject();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [persona, setPersona] = useState<PersonaConfig | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState(newThreadId);
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showSwitch, setShowSwitch] = useState(false);
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 사주 변경(본인↔동반자) — 상담 대상을 전환한다. 선택 시 컨텍스트 반영 → effect가 프로필 재로드.
  function openSwitch() {
    setShowSwitch((v) => !v);
    if (subjects.length === 0) {
      listSubjects().then(setSubjects).catch(() => setSubjects([]));
    }
  }
  function switchSubject(s: SubjectSummary) {
    setShowSwitch(false);
    if (s.subject_id === selected?.subjectId) return;
    setSelected({ subjectId: s.subject_id, label: s.label });
  }

  // 선택된 사주가 바뀌면 프로필·페르소나를 로드하고 새 대화를 시작한다.
  useEffect(() => {
    if (!isLoggedIn || !selected) {
      setProfile(null);
      return;
    }
    setLoading(true);
    Promise.all([getSubject(selected.subjectId), getPersona().catch(() => undefined)])
      .then(([subj, p]) => {
        setProfile(summaryToProfile(subj));
        setPersona(p);
        setMessages([]);
        setThreadId(newThreadId());
      })
      .finally(() => setLoading(false));
  }, [isLoggedIn, selected]);

  // 저장된 대화 목록 로드(로그인 시).
  const loadThreads = () => {
    listChatThreads().then(setThreads).catch(() => setThreads([]));
  };
  useEffect(() => {
    if (isLoggedIn) loadThreads();
  }, [isLoggedIn]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function newConversation() {
    setMessages([]);
    setThreadId(newThreadId());
    setShowHistory(false);
  }

  async function resumeThread(id: string) {
    setShowHistory(false);
    setBusy(true);
    try {
      const msgs = await getChatThread(id);
      setMessages(msgs.map((m) => ({ role: m.role, text: m.text })));
      setThreadId(id);
    } catch {
      /* 무시 */
    } finally {
      setBusy(false);
    }
  }

  async function removeThread(id: string) {
    await deleteChatThread(id).catch(() => {});
    setThreads((prev) => prev.filter((t) => t.thread_id !== id));
    if (id === threadId) newConversation();
  }

  async function send(question: string) {
    if (!profile || busy || !question.trim()) return;
    const fresh = messages.length === 0; // 첫 메시지면 새 스레드가 목록에 생긴다.
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await postChat(
        profile, question, threadId, persona, selected?.label, selected?.subjectId,
      );
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.answer ?? "(응답 없음)", meta: res },
      ]);
      if (fresh) loadThreads();
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

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;

  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">AI채팅상담</h1>
        <p className="mt-2 text-sm text-gray-600">
          로그인 후 이용할 수 있어요. 좌측 메뉴(☰)에서 아이디·PIN으로 로그인해 주세요.
        </p>
      </section>
    );
  }

  if (!selected || !profile) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-bold">AI채팅상담</h1>
        {loading ? (
          <p className="text-sm text-gray-500">사주 불러오는 중…</p>
        ) : (
          <SubjectGateway
            title="상담할 사주 선택"
            returnTo="/chat"
            onResolved={() => {
              /* 선택은 컨텍스트로 반영되어 effect가 프로필을 로드한다. */
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-2">
          <h1 className="text-xl font-bold">AI채팅상담</h1>
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={openSwitch}
              className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
            >
              사주 변경
            </button>
            <button
              onClick={() => {
                if (!showHistory) loadThreads();
                setShowHistory((v) => !v);
              }}
              className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
            >
              대화 목록{threads.length ? ` (${threads.length})` : ""}
            </button>
            <button
              onClick={newConversation}
              className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
            >
              새 대화
            </button>
          </div>
        </div>

        {showSwitch && (
          <div className="mt-3 space-y-1.5 border-t pt-3">
            <p className="text-xs text-gray-500">상담할 사주를 고르세요 (본인·동반자)</p>
            {subjects.length === 0 ? (
              <p className="text-xs text-gray-400">사주목록 불러오는 중…</p>
            ) : (
              <div className="grid gap-1.5 sm:grid-cols-2">
                {subjects.map((s) => (
                  <button
                    key={s.subject_id}
                    onClick={() => switchSubject(s)}
                    className={`rounded border px-2.5 py-1.5 text-left text-sm ${
                      s.subject_id === selected.subjectId
                        ? "border-indigo-300 bg-indigo-50 font-medium"
                        : "hover:bg-gray-50"
                    }`}
                  >
                    <span className="block truncate">
                      {s.label}
                      <span className="ml-1 text-[11px] text-gray-400">
                        {s.kind === "self" ? "본인" : "동반자"}
                      </span>
                    </span>
                    <span className="block text-[11px] text-gray-400">
                      {s.birth.birth_date}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <p className="mt-1 text-xs text-gray-500">
          {selected.label} · {profile.birthDate}{" "}
          {profile.timeUnknown ? "(시간 모름)" : profile.birthTime} 기준 · 같은 창에서는 대화 맥락이
          이어집니다. 로그인 대화는 자동 저장돼요.
        </p>

        {showHistory && (
          <div className="mt-3 max-h-64 space-y-1.5 overflow-y-auto border-t pt-3">
            {threads.length === 0 ? (
              <p className="text-xs text-gray-400">저장된 대화가 없어요.</p>
            ) : (
              threads.map((t) => (
                <div
                  key={t.thread_id}
                  className={`flex items-center justify-between gap-2 rounded border px-2 py-1.5 ${
                    t.thread_id === threadId ? "border-indigo-300 bg-indigo-50" : ""
                  }`}
                >
                  <button
                    onClick={() => resumeThread(t.thread_id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="block truncate text-sm">{t.title ?? "(제목 없음)"}</span>
                    <span className="block text-[11px] text-gray-400">
                      {t.subject_label ? `${t.subject_label} · ` : ""}
                      {(t.updated_at ?? "").slice(0, 16).replace("T", " ")}
                    </span>
                  </button>
                  <button
                    onClick={() => removeThread(t.thread_id)}
                    className="shrink-0 rounded border border-red-200 px-1.5 py-0.5 text-[11px] text-red-500"
                  >
                    삭제
                  </button>
                </div>
              ))
            )}
          </div>
        )}
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
                  ? "inline-block max-w-[85%] whitespace-pre-wrap rounded-2xl bg-indigo-600 px-4 py-2 text-left text-sm text-white"
                  : "inline-block max-w-[95%] rounded-2xl bg-gray-100 px-4 py-3 text-sm text-gray-800"
              }
            >
              {m.role === "user" ? (
                m.text
              ) : (
                <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-headings:mt-2 prose-headings:mb-1 prose-li:my-0.5">
                  <ReactMarkdown>{m.text}</ReactMarkdown>
                </div>
              )}
            </div>
            {m.meta && m.meta.status !== "answered" && (
              <p className="mt-1 text-xs text-amber-600">
                {m.meta.status === "too_broad" && "범위를 좁히면 바로 풀이해 드려요."}
                {m.meta.status === "need_subject" && "동반자 등 대상 확인이 필요해요. 사주목록에서 상대를 등록해 주세요."}
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
