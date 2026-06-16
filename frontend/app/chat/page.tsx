"use client";

// AI채팅상담 (로그인 전용) — 선택된 사주로 /api/v2/chat 호출, 계정 페르소나(문체) 적용,
// thread_id로 멀티턴 유지. 엔진이 계산한 점수·간지를 LLM이 서술한 결과를 그대로 표시한다.

import Link from "next/link";
import { type ReactNode, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@/components/providers/AuthProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { InlinePartnerForm } from "@/components/subject/InlinePartnerForm";
import { SubjectGateway } from "@/components/subject/SubjectGateway";
import {
  deleteChatThread,
  getChatPartner,
  getChatThread,
  listChatThreads,
  postChat,
} from "@/lib/api";
import { readingFontClasses } from "@/lib/storage";
import { useReadingFontSize } from "@/lib/useReadingFontSize";
import { summaryToProfile } from "@/lib/subject-mapping";
import { getPersona, getSubject, listSubjects } from "@/lib/subjects";
import type {
  ChatApiResponse,
  ChatMessageDTO,
  ChatPartner,
  ChatThreadSummary,
  PersonaConfig,
  Profile,
  SubjectSummary,
} from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  text: string;
  meta?: ChatApiResponse;
  pending?: boolean; // 백그라운드 생성 중(폴링 대기) — 플레이스홀더 표시
  error?: boolean; // 생성 실패(서버 안내문)
}

function newThreadId(): string {
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// '+' 메뉴 액션 → 레이어 팝업 모달. 모바일은 바텀시트, 데스크톱은 가운데 정렬.
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        aria-label="닫기"
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
      />
      <div className="relative z-10 max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-800">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="rounded p-1 text-gray-400 hover:bg-gray-100"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeWidth="2" strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// 서버 저장 메시지 → 말풍선. pending(생성 중)/error(실패)는 플래그로 표시한다.
function toMessage(m: ChatMessageDTO): Message {
  return {
    role: m.role,
    text: m.text || (m.status === "pending" ? "답변 생성 중…" : ""),
    pending: m.status === "pending",
    error: m.status === "error",
  };
}

// 궁합 상대 첨부 상태를 스레드별로 영속화(localStorage) — 새로고침·대화 이어가기에 유지.
const PARTNER_KEY = (threadId: string) => `ryubosal:chatPartner:${threadId}`;
function loadPartnerFor(threadId: string): ChatPartner | null {
  try {
    const raw = localStorage.getItem(PARTNER_KEY(threadId));
    return raw ? (JSON.parse(raw) as ChatPartner) : null;
  } catch {
    return null;
  }
}
function savePartnerFor(threadId: string, partner: ChatPartner | null): void {
  try {
    if (partner) localStorage.setItem(PARTNER_KEY(threadId), JSON.stringify(partner));
    else localStorage.removeItem(PARTNER_KEY(threadId));
  } catch {
    /* 저장 실패는 무시(첨부는 세션 상태로도 동작) */
  }
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
  const [showMenu, setShowMenu] = useState(false); // 하단 '+' 레이어 팝업
  const [showSwitch, setShowSwitch] = useState(false);
  const MAX_INPUT = 120; // 입력 글자수 제한(목업 0/70 → 사용자 확정 120)
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [partner, setPartner] = useState<ChatPartner | null>(null);
  const [showPartner, setShowPartner] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  // 백그라운드 답변 폴링 세션 토큰 — 스레드 전환/언마운트 시 증가시켜 진행 중 폴링을 무효화.
  const pollTokenRef = useRef(0);

  // 백그라운드 생성 답변을 완료까지 폴링한다(2초 간격, 최대 ~4분). 서버가 진리원본이므로
  // 완료 시 스레드 전체 메시지로 교체한다. 클라이언트 이탈 후 재진입에도 동일 경로로 복구된다.
  async function pollThread(id: string): Promise<void> {
    const token = ++pollTokenRef.current;
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      if (pollTokenRef.current !== token) return; // 다른 스레드로 이동 — 중단
      let msgs: ChatMessageDTO[];
      try {
        msgs = await getChatThread(id);
      } catch {
        continue; // 일시 오류는 계속 재시도
      }
      if (pollTokenRef.current !== token) return;
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant" && last.status !== "pending") {
        setMessages(msgs.map(toMessage));
        loadThreads();
        return;
      }
    }
    // 타임아웃 — 플레이스홀더를 안내문으로 교체(답변은 목록에서 이어 확인 가능).
    setMessages((prev) =>
      prev.map((m) =>
        m.pending
          ? {
              ...m,
              text: "답변 생성이 지연되고 있어요. 잠시 후 목록에서 다시 확인해 주세요.",
              pending: false,
            }
          : m,
      ),
    );
  }

  // 읽기 글자 크기(설정 페이지) — 채팅·테마 뷰어 공통. 말풍선 본문·마크다운에 함께 적용.
  const { text: bubbleFontCls, prose: proseFontCls } = readingFontClasses(useReadingFontSize());
  // 미열람 완료 답변이 있는 대화 수 — '+' 버튼·대화목록 항목 뱃지.
  const unseenCount = threads.filter((t) => t.has_unseen).length;
  // 동반자로 고를 수 있는 등록 사주(현재 상담 대상 제외) — 없으면 등록 안내.
  const partnerCandidates = subjects.filter((s) => s.subject_id !== selected?.subjectId);

  function loadSubjectsOnce() {
    if (subjects.length === 0) {
      listSubjects().then(setSubjects).catch(() => setSubjects([]));
    }
  }
  // 사주 변경(본인↔동반자) — 상담 대상을 전환한다. 선택 시 컨텍스트 반영 → effect가 프로필 재로드.
  function openSwitch() {
    setShowSwitch((v) => !v);
    loadSubjectsOnce();
  }
  function switchSubject(s: SubjectSummary) {
    setShowSwitch(false);
    if (s.subject_id === selected?.subjectId) return;
    setSelected({ subjectId: s.subject_id, label: s.label });
  }
  // 궁합 상대 첨부 — 등록 동반자 또는 즉석 입력. 첨부 시 질문이 두 명식 궁합으로 풀린다.
  function openPartner() {
    setShowPartner((v) => !v);
    loadSubjectsOnce();
  }
  // '+' 팝업에서 레이어 모달 열기 — 다른 모달은 닫고 대상만 연다(오버레이라 스크롤 불필요).
  function closeMenuAndOpen(panel: "switch" | "partner" | "history") {
    setShowMenu(false);
    setShowSwitch(panel === "switch");
    setShowPartner(panel === "partner");
    setShowHistory(panel === "history");
    if (panel !== "history") loadSubjectsOnce();
    else loadThreads();
  }

  // 첨부 상태를 스레드별로 영속화(새로고침·대화 이어가기에도 유지). setPartner 대신 사용.
  function attachPartner(p: ChatPartner | null) {
    setPartner(p);
    savePartnerFor(threadId, p);
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
        pollTokenRef.current++; // 대상 전환 — 진행 중 폴링 무효화
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

  // 스레드가 바뀌면(이어가기·새 대화) 그 스레드의 궁합 상대 첨부를 복원한다.
  // 로컬(같은 기기) 우선, 없으면 저장된 스레드에 한해 서버에서 복원(크로스 디바이스).
  useEffect(() => {
    const local = loadPartnerFor(threadId);
    if (local) {
      setPartner(local);
      return;
    }
    setPartner(null);
    if (!threads.some((t) => t.thread_id === threadId)) return; // 신규 대화는 스킵
    let cancelled = false;
    getChatPartner(threadId).then((p) => {
      if (cancelled || !p) return;
      setPartner(p);
      savePartnerFor(threadId, p);
    });
    return () => {
      cancelled = true;
    };
  }, [threadId, threads]);

  function newConversation() {
    pollTokenRef.current++; // 진행 중 폴링 무효화(빈 대화에 결과가 끼어들지 않도록)
    setMessages([]);
    setThreadId(newThreadId());
    setShowHistory(false);
  }

  async function resumeThread(id: string) {
    setShowHistory(false);
    setBusy(true);
    try {
      const msgs = await getChatThread(id);
      setMessages(msgs.map(toMessage));
      setThreadId(id);
      // 이어보기 중인 스레드의 답변이 아직 생성 중이면(다른 기기/이탈 중 전송) 폴링 재개.
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant" && last.status === "pending") {
        void pollThread(id);
      }
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
        partner ?? undefined,
      );
      if (res.status === "pending") {
        // 백그라운드 생성 — 플레이스홀더 표시 후 완료까지 폴링(이탈해도 서버가 끝까지 생성).
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: "답변 생성 중…", pending: true },
        ]);
        if (fresh) loadThreads();
        void pollThread(res.thread_id ?? threadId);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: res.answer ?? "(응답 없음)", meta: res },
        ]);
        if (fresh) loadThreads();
      }
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
    // pb-24: 하단 고정 입력바에 가려지지 않도록 본문 끝에 여백 확보.
    <div className="pb-28">
      {showSwitch && (
        <Modal title="사주 변경" onClose={() => setShowSwitch(false)}>
          <div className="space-y-1.5">
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
        </Modal>
      )}

      {showPartner && (
        <Modal title="동반자 추가" onClose={() => setShowPartner(false)}>
          <div className="space-y-2">
            <p className="text-xs text-gray-500">
              함께 볼 동반자(해제 전까지)를 고르거나 즉석 입력(1회용)하세요. 질문에 따라
              관계·궁합 등으로 함께 풀이됩니다.
            </p>
            {partnerCandidates.length === 0 ? (
              <div className="rounded-lg border bg-gray-50 p-4 text-center">
                <p className="mb-2 text-xs text-gray-500">등록된 동반자가 없어요.</p>
                <Link
                  href="/sajus"
                  onClick={() => setShowPartner(false)}
                  className="inline-block rounded bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700"
                >
                  동반자 등록하러 가기
                </Link>
              </div>
            ) : (
              <div className="grid gap-1.5 sm:grid-cols-2">
                {partnerCandidates.map((s) => (
                  <button
                    key={s.subject_id}
                    onClick={() => {
                      attachPartner({ mode: "registered", subjectId: s.subject_id, label: s.label });
                      setShowPartner(false);
                    }}
                    className="rounded border px-2.5 py-1.5 text-left text-sm hover:bg-gray-50"
                  >
                    <span className="block truncate">
                      {s.label}
                      <span className="ml-1 text-[11px] text-gray-400">
                        {s.relation_to_user ?? (s.kind === "self" ? "본인" : "동반자")}
                      </span>
                    </span>
                    <span className="block text-[11px] text-gray-400">{s.birth.birth_date}</span>
                  </button>
                ))}
              </div>
            )}
            <details className="rounded-lg border bg-gray-50 p-3">
              <summary className="cursor-pointer text-sm font-medium text-gray-700">
                상대 정보 즉석 입력 (등록 없이)
              </summary>
              <div className="mt-3">
                <InlinePartnerForm
                  onSubmit={(label, birth) => {
                    attachPartner({ mode: "inline", label, birth });
                    setShowPartner(false);
                  }}
                />
              </div>
            </details>
          </div>
        </Modal>
      )}

      {showHistory && (
        <Modal title="대화 목록" onClose={() => setShowHistory(false)}>
          <div className="max-h-[60vh] space-y-1.5 overflow-y-auto">
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
                    <span className="flex items-center gap-1.5 truncate text-sm">
                      {t.has_unseen && (
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-full bg-indigo-500"
                          title="새 답변 도착"
                        />
                      )}
                      {t.pending && !t.has_unseen && (
                        <span
                          className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-amber-400"
                          title="답변 생성 중"
                        />
                      )}
                      <span className="truncate">{t.title ?? "(제목 없음)"}</span>
                    </span>
                    <span className="block text-[11px] text-gray-400">
                      {t.subject_label ? `${t.subject_label} · ` : ""}
                      {(t.updated_at ?? "").slice(0, 16).replace("T", " ")}
                      {t.has_unseen ? " · 새 답변" : t.pending ? " · 생성 중" : ""}
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
        </Modal>
      )}

      <section className="min-h-[70vh] space-y-3 pt-3">
        {messages.length === 0 && (
          <p className="pt-20 text-center text-sm text-gray-400">무엇이든 물어보세요.</p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                m.role === "user"
                  ? `inline-block max-w-[85%] whitespace-pre-wrap rounded-2xl bg-indigo-600 px-4 py-2 text-left ${bubbleFontCls} text-white`
                  : m.error
                    ? `inline-block max-w-[95%] rounded-2xl bg-red-50 px-4 py-3 ${bubbleFontCls} text-red-700`
                    : `inline-block max-w-[95%] rounded-2xl bg-gray-100 px-4 py-3 ${bubbleFontCls} text-gray-800`
              }
            >
              {m.role === "user" ? (
                m.text
              ) : m.pending ? (
                <span className={`flex items-center gap-2 ${bubbleFontCls} text-gray-500`}>
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-indigo-400" />
                  답변 생성 중…
                </span>
              ) : (
                <div className={`prose ${proseFontCls} max-w-none prose-p:my-1.5 prose-headings:mt-2 prose-headings:mb-1 prose-li:my-0.5`}>
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

      {/* 질문 입력란 — 브라우저 하단 고정(본문은 위 pb-24로 가림 방지). '+' 레이어 팝업으로
          새 대화·사주변경·동반자추가·대화목록을 연다. iOS 안전영역(노치) 보정. */}
      {/* 메신저 스타일 입력 — 하단 고정. '+'로 레이어 팝업(새 대화·사주변경·동반자추가·대화목록). */}
      <form
        className="fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-white via-white/95 px-3 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <div className="relative mx-auto max-w-4xl">
          {/* 동반자 첨부 칩 */}
          {partner && (
            <div className="mb-2 flex w-fit items-center gap-2 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700">
              <span>
                동반자 <span className="font-medium">{partner.label}</span> — 질문에 따라 함께 풀이
              </span>
              <button
                type="button"
                onClick={() => attachPartner(null)}
                className="rounded-full px-1 text-rose-500 hover:bg-rose-100"
                aria-label="동반자 해제"
              >
                ✕
              </button>
            </div>
          )}

          {/* '+' 레이어 팝업 */}
          {showMenu && (
            <>
              <button
                type="button"
                aria-label="메뉴 닫기"
                className="fixed inset-0 z-10 cursor-default"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute bottom-16 left-1 z-20 w-44 overflow-hidden rounded-lg border bg-white text-sm shadow-lg">
                <button
                  type="button"
                  onClick={() => { setShowMenu(false); newConversation(); }}
                  className="block w-full px-3 py-2 text-left hover:bg-gray-50"
                >
                  새 대화
                </button>
                <button
                  type="button"
                  onClick={() => closeMenuAndOpen("switch")}
                  className="block w-full border-t px-3 py-2 text-left hover:bg-gray-50"
                >
                  사주 변경
                </button>
                <button
                  type="button"
                  onClick={() => closeMenuAndOpen("partner")}
                  className="block w-full border-t px-3 py-2 text-left hover:bg-gray-50"
                >
                  동반자 추가
                </button>
                <button
                  type="button"
                  onClick={() => closeMenuAndOpen("history")}
                  className="flex w-full items-center justify-between border-t px-3 py-2 text-left hover:bg-gray-50"
                >
                  <span>대화 목록</span>
                  <span className="ml-2 flex items-center gap-1">
                    {threads.length > 0 && (
                      <span className="inline-flex h-4 min-w-[1.25rem] items-center justify-center rounded bg-gray-200 px-1 text-[10px] font-semibold text-gray-600">
                        {threads.length}
                      </span>
                    )}
                    {unseenCount > 0 && (
                      <span className="inline-flex h-4 min-w-[1.25rem] items-center justify-center rounded bg-indigo-500 px-1 text-[10px] font-bold text-white">
                        {unseenCount > 99 ? "99+" : unseenCount}
                      </span>
                    )}
                  </span>
                </button>
              </div>
            </>
          )}

          {/* 메신저 입력 박스 — 메시지란 위, 액션행(+·글자수·보내기) 아래 */}
          <div className="rounded-2xl border border-gray-300 bg-white shadow-sm focus-within:border-gray-400">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              maxLength={MAX_INPUT}
              rows={1}
              placeholder="메시지…"
              disabled={busy}
              className="block max-h-32 w-full resize-none bg-transparent px-4 pt-3 text-sm outline-none"
            />
            <div className="flex items-center gap-1 px-2 pb-2">
              <button
                type="button"
                aria-label="메뉴"
                onClick={() => {
                  if (!showMenu) loadThreads(); // 열 때 목록·개수 최신화
                  setShowMenu((v) => !v);
                }}
                className="relative flex h-8 w-8 items-center justify-center rounded-full text-xl leading-none text-gray-500 hover:bg-gray-100"
              >
                +
                {unseenCount > 0 && !showMenu && (
                  <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-indigo-500" />
                )}
              </button>
              <span className="ml-auto text-[10px] text-gray-400">
                {input.length} / {MAX_INPUT}
              </span>
              <button
                type="submit"
                aria-label="보내기"
                disabled={busy || !input.trim()}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-white disabled:bg-gray-200 disabled:text-gray-400"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
