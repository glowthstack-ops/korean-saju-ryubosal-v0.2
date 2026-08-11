"""Broad Query Rewriter (v2.2 Phase 3 T3.2, docs/03 B3 — 판정표 전체).

판정 축: 시점 × 분야 × **대상**(동반자 기능 때문에 대상 모호가 별도 축).
질문을 거절하지 않고 실행 가능한 형태로 바꿔 제안한다. 단답 후속(B2)은 슬롯 상속으로
해결되므로 too_broad 판정 전에 Question Linking을 먼저 거친다(파서의 prev_intent 경로).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectKind

# 분야별 기본 기간 (docs/03 B3 — defaults 사전 초안, 검수 대상).
DEFAULT_PERIOD_MONTHS: dict[Domain, int] = {
    Domain.RELATIONSHIP: 6,
    Domain.CAREER: 12,
    Domain.WEALTH: 12,
    Domain.RELOCATION: 6,
    Domain.HEALTH: 12,
    Domain.EDUCATION: 12,
    Domain.GENERAL: 3,
}


class RewriteSuggestion(BaseModel):
    """too_broad 시 제안 한 줄 (docs/03 B3 응답 형식)."""

    label: str
    query_type: QueryType
    domain: Domain | None = None
    time_scope: str | None = None


class QueryAssessment(BaseModel):
    """판정 결과 — ok / too_broad / need_subject."""

    status: str  # 'ok' | 'too_broad' | 'need_subject' | 'apply_default_period'
    original_query: str | None = None
    default_period_months: int | None = None
    rewrite_suggestions: list[RewriteSuggestion] = Field(default_factory=list)
    clarify_question: str | None = None  # 대상 확인 질문(추측 실행 금지)


_SUGGESTIONS = [
    RewriteSuggestion(
        label="향후 3개월 전체 흐름",
        query_type=QueryType.FORTUNE_OVERVIEW, time_scope="short_term",
    ),
    RewriteSuggestion(
        label="올해 직업운", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
    ),
    RewriteSuggestion(
        label="향후 6개월 연애운",
        query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.RELATIONSHIP,
    ),
]

# 분야 한글 라벨 — 활성 스레드 맥락 기반 제안(아래) 생성용.
_DOMAIN_KO: dict[Domain, str] = {
    Domain.RELATIONSHIP: "연애운", Domain.CAREER: "직업운", Domain.WEALTH: "금전운",
    Domain.RELOCATION: "이사운", Domain.HEALTH: "건강운", Domain.EDUCATION: "학업운",
}


def _context_suggestions(last: IntentJson | None) -> list[RewriteSuggestion]:
    """직전(활성 스레드) intent의 분야를 이어가는 좁히기 제안(2026-06-16).

    too_broad 단답이 활성 스레드 안에서 나오면, 하드코딩 일반 목록 대신 직전 분야를
    잇는 제안을 준다(예: 이사 스레드 → '향후 6개월 이사운'/'특정 달 이사 좋은 날').
    직전 분야를 알 수 없으면(GENERAL/없음) 빈 목록 → 호출 측이 일반 목록으로 폴백.
    """
    if last is None:
        return []
    dom = last.domain if last.domain is not Domain.GENERAL else (
        last.domains[0] if last.domains else Domain.GENERAL
    )
    label = _DOMAIN_KO.get(dom)
    if label is None:
        return []
    months = DEFAULT_PERIOD_MONTHS.get(dom, 3)
    out = [
        RewriteSuggestion(
            label=f"향후 {months}개월 {label}",
            query_type=QueryType.DOMAIN_ANALYSIS, domain=dom, time_scope="mid_term",
        ),
        RewriteSuggestion(
            label=f"올해 {label}",
            query_type=QueryType.DOMAIN_ANALYSIS, domain=dom, time_scope="mid_term",
        ),
    ]
    # 이사 택일 스레드면 '다른 달 택일'도 제안(직전이 날짜 추천이었던 맥락 보존).
    if dom is Domain.RELOCATION:
        out.append(RewriteSuggestion(
            label="특정 달 이사 좋은 날(예: 8월)",
            query_type=QueryType.DATE_RECOMMENDATION, domain=dom,
        ))
    return out


# ── 사건 서술(고민 상담)형 감지 — B3 예외(2026-08-11 데굴님 승인) ────────────────
# "과거 사건 서술 + 우려 + 막연 미래 질의"는 시점·분야 어휘가 없어도 범위를 되묻지
# 않고 실행한다. 실사용 보고: "집안 자랑하다가 그게 발목을 잡아서 연기인생을 망치게
# 될 것 같아. 앞으로 어떻게 될까?"가 표현을 바꿔도 세 번 연속 좁히기 메뉴로 튕겼다
# — 상황을 구체적으로 서술했는데 되물으면 서술이 통째로 무시된다.
# 통과 후 서술 범위는 답변 지평 정책(docs/16, horizon.resolve_horizon)이 잡는다.
# 세 신호를 모두 요구해 "앞으로 내 운세 알려줘" 같은 무맥락 질문은 기존대로 좁힌다.
#
# 과거 서술절 연결어미: -았/었는데·-았/었더니(축약형 했·됐·갔·왔·졌…은 아래
# _has_past_narrative가 받침 ㅆ으로 일반화), -다가('다가오는 3년' 같은 시간어는 제외).
_NARRATIVE_CONNECTIVE = re.compile(r"([가-힣])(?:는데|더니)")
_NARRATIVE_DAGA = re.compile(r"[가-힣]다가(?!오|올|온|와)")
# 우려·부정 결과 어휘 — 사건이 나쁘게 번질 것을 걱정하는 표현만 열거한다.
_CONCERN = re.compile(
    r"망치|망칠|망하|망할|발목|잘못되|잘못될|꼬이|꼬여|틀어지|무너지|끝장|"
    r"잃을|잃게|위기|큰일|문제가?\s*(?:생|되|터)|일이\s*터|사고를?\s*치|손해|피해|걱정|불안"
)
# 막연 미래 질의 — 특정 시점 없이 앞날을 묻는 어법.
_VAGUE_FUTURE_ASK = re.compile(r"앞으로|어떻게\s*될|어찌\s*될|어떻게\s*해야|어떡")

_SSANG_SIOT_JONG = 20  # 한글 음절 종성 인덱스 — ㅆ(과거 시제 선어말어미 축약의 공통 받침)


def _has_past_narrative(text: str) -> bool:
    """과거 서술절(-았/었는데·-았/었더니, -다가) 존재 여부.

    '했는데·됐는데·나빠졌는데'처럼 과거 선어말어미가 어간에 축약된 표면형은 열거가
    불가능하므로, 연결어미 앞 음절의 받침이 ㅆ인지로 일반화해 판정한다.
    '활동 중인데' 같은 현재 서술이나 '걱정되는데' 같은 비과거형은 통과하지 않는다.
    """
    for m in _NARRATIVE_CONNECTIVE.finditer(text):
        if (ord(m.group(1)) - 0xAC00) % 28 == _SSANG_SIOT_JONG:
            return True
    return bool(_NARRATIVE_DAGA.search(text))


def _is_incident_concern(text: str) -> bool:
    """사건 서술(고민 상담)형 — 과거 서술절 + 우려 + 막연 미래 질의 3신호 동시 충족."""
    return bool(
        text
        and _has_past_narrative(text)
        and _CONCERN.search(text)
        and _VAGUE_FUTURE_ASK.search(text)
    )


def assess(
    intent: IntentJson, original_query: str = "", last_intent: IntentJson | None = None,
) -> QueryAssessment:
    """B3 판정표 적용.

    | 시점 | 분야 | 대상 | 처리 |
    | ✗ | ✗ | 확정 | too_broad → 선택지 제안(실행 안 함) — 단 사건 서술형은 실행 |
    | ✓ | ✗ | 확정 | 종합운 실행 |
    | ✗ | ✓ | 확정 | 분야 기본 기간 적용 |
    | ✓ | ✓ | 확정 | 바로 실행 |
    | - | - | 모호 | 대상 확인 질문 우선(추측 실행 금지 — 실측 최다 오류) |
    """
    # 대상 모호: partial_info 또는 미해소 동반자(companion_id 없는 companion 참조 다수).
    ambiguous = any(s.kind is SubjectKind.PARTIAL_INFO for s in intent.subjects) or (
        len([s for s in intent.subjects if s.kind is SubjectKind.COMPANION]) > 1
        and intent.subject_mode.value == "single"
    )
    if ambiguous:
        return QueryAssessment(
            status="need_subject",
            original_query=original_query,
            clarify_question="어느 분 사주로 볼까요? (본인 / 등록 동반자 중 선택)",
        )

    has_time = intent.time_range is not None
    has_domain = intent.domain is not Domain.GENERAL or bool(intent.domains)

    # 비분석 라우트는 판정 불요. CHART_ANALYSIS(Q8 — 일주/명식 구조)는 원국(T0)
    # 질문이라 시점·분야가 본질적으로 불요(v2.2.1 — '나의 일주캐릭터는?' 골든 스타일).
    if intent.query_type in (
        QueryType.TERMINOLOGY_EDUCATION, QueryType.FEEDBACK_CORRECTION,
        QueryType.EMOTIONAL_SUPPORT, QueryType.OUT_OF_SCOPE,
        QueryType.CHART_ANALYSIS,
        # 비교/궁합/경쟁은 '무엇을 비교할지(대상)'가 곧 분석 대상이라 시점·분야 없이도 실행한다.
        # (대상 모호는 위 ambiguous 가드가 이미 need_subject로 처리.)
        QueryType.COMPARISON,
    ):
        return QueryAssessment(status="ok")

    if not has_time and not has_domain:
        # 사건 서술(고민 상담)형은 되묻지 않고 실행한다(B3 예외, 2026-08-11) —
        # 서술 범위는 chat의 vague_future 경로에서 답변 지평 정책(docs/16)이 잡는다.
        if _is_incident_concern(original_query):
            return QueryAssessment(status="ok")
        # 활성 스레드가 있으면 직전 분야를 잇는 제안, 없으면 일반 목록으로 폴백.
        return QueryAssessment(
            status="too_broad",
            original_query=original_query,
            rewrite_suggestions=_context_suggestions(last_intent) or _SUGGESTIONS,
        )
    if not has_time and has_domain:
        return QueryAssessment(
            status="apply_default_period",
            default_period_months=DEFAULT_PERIOD_MONTHS[intent.domain],
        )
    return QueryAssessment(status="ok")
