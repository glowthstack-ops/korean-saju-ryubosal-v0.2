"""답변 시간 지평(Horizon) 정책 — 무시점 미래 질문의 서술 범위 산출.

2026-07-09 데굴님 지시: 답변이 질문의 시간 지평보다 장기로 흐르는 경향 교정.
기존에는 시점 없는 미래 질문이 전부 10년 연 단위 digest(vague_future)로 빠졌으나,
질문 유형별로 지평을 다르게 잡는다:

- 즉시형("지금 돈이 필요한데") → 향후 3개월 월 단위
- 시도·전망형("부업 해볼까, 성공할까") → 향후 6개월 월 단위 + 5년 연 단위
- 구조 결정형(사업·퇴사·이혼 등 인생 구조 변경) → 원국 적합성 + 현재 대운 +
  향후 5년 연 단위 + 당장 3개월 월 흐름
- 그 외 무시점 분야 질문 → 분야별 기본 기간(docs/03 B3·docs/08 C1,
  rewriter.DEFAULT_PERIOD_MONTHS — 기존 dead code를 여기서 소비)
- 명시적 장기 질문(대운·인생 흐름)만 기존 10년 digest 유지(None 반환)

지평 밖 서술은 금지하되 답변 끝 '더 먼 흐름은 이어서 물어보라' 한 줄 안내만 허용
(2026-07-09 확정). 감지는 규칙 기반 — LLM 판정 금지(절대원칙 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from saju_shared_types.events import EventKey
from saju_shared_types.intent import IntentJson, QueryType, TimeScope

from .job_separation import is_job_separation
from .rewriter import DEFAULT_PERIOD_MONTHS

# 유형 감지(우선순위: 장기/개방형시기 제외 > 구조 결정 > 즉시 > 시도·전망 > 분야 기본).
_LONG_TERM_RE = re.compile(r"대운|인생\s*전체|인생\s*흐름|평생|장기적|10년|노후|말년")
# 개방형 '언제' 질문 — 2026-06-18 확정(10년 연 digest + 연도 지정 유도) 보존.
# 12개월로 좁혀 특정 달을 단정하던 결함의 보완책이므로 지평 정책 밖에 둔다.
_OPEN_WHEN_RE = re.compile(r"언제|어느\s*(해|때|시기)|때를|시기를|타이밍")
_STRUCTURAL_RE = re.compile(r"사업|창업|폐업|퇴사|그만두|그만둘|이혼|전업|이민|귀농|독립")
_IMMEDIATE_RE = re.compile(r"지금|당장|급하|급전|급히|빨리|이번\s*(달|주)")
_VENTURE_RE = re.compile(
    r"해\s*볼까|해도\s*될까|시작해\s*볼|성공할|잘\s*될까|될까요|될\s*수\s*있을까|어떨까|도전"
)


@dataclass(frozen=True)
class HorizonPolicy:
    """무시점 미래 질문 1건의 답변 지평.

    months_detail: 월 단위 상세 창(개월). years_span: 연(세운) 단위 서술 범위(년,
    0=연 digest 없음). natal_fit: 원국 적합성 중심 구성(구조 결정형).
    """

    kind: str  # immediate | venture | structural | domain_default | transactional_when
    months_detail: int
    years_span: int
    natal_fit: bool
    label: str  # 디렉티브·로그용 지평 설명
    # 진입 사건(입사·이직) — 답을 '움직이는 달(제안·접수·면접) + 성사 달(입사)' 두 칸으로 낸다
    # (EMPLOYMENT_HISTORY_CALIBRATION.md §4, 2026-10-22). 구조 결정형·택일에는 붙이지 않는다.
    entry_window: bool = False


#: 진입 사건 키 — 두 칸 지시가 붙는 사건.
_ENTRY_EVENT_KEYS: frozenset[EventKey] = frozenset({EventKey.JOB_GAIN, EventKey.CAREER_CHANGE})
#: 진입 사건 두 칸 지시(리드타임 기본 1~2개월 — 사용자가 말한 값이 있으면 그 값).
ENTRY_WINDOW_DIRECTIVE = (
    "[진입 시기 두 칸] 입사·이직처럼 '들어가는' 사건은 성사 달(입사·계약)과 그보다 한두 달 앞의 "
    "움직이는 달(제안·접수·면접)을 나눠 말하라. 사건 후보가 있는 달을 성사 달로 두고 움직이는 달은 "
    "그 한두 달 앞으로 잡되, 사용자가 자기 리드타임(예: 보통 한 달)을 말했으면 그 값을 쓰라. "
    "행동 제안(지원·주변에 알리기)은 움직이는 달에 붙이고 성사 달에는 결과를 단정하지 말 것. "
    "과거 사례의 회사명·고용주는 언급하지 말 것."
)


def resolve_horizon(question: str, intent: IntentJson) -> HorizonPolicy | None:
    """무시점 미래 질문의 지평 정책을 정한다. 명시적 장기 질문은 None(10년 digest 유지).

    호출 측(chat)은 vague_future(시점 미지정·미래·비구조 질문)에서만 호출한다 —
    명시 시점·과거 회고·CHART_ANALYSIS·택일은 기존 경로가 담당.
    진입 사건(job_gain·career_change)이면 구조 결정형·택일을 뺀 모든 지평에 `entry_window`를 켠다.
    """
    policy = _resolve_horizon_kind(question, intent)
    if (
        policy is not None
        and policy.kind not in ("structural", "date_window")
        and intent.event_key in _ENTRY_EVENT_KEYS
    ):
        return replace(policy, entry_window=True)
    return policy


def _resolve_horizon_kind(question: str, intent: IntentJson) -> HorizonPolicy | None:
    """지평 종류 판정(entry_window 제외)."""
    # 택일(날 고르기) 질문은 탐색 창(오늘부터 약 한 달 — 이번 달·다음 달) 지평이다(2026-10-19 데굴님
    # 승인). 실답: 시점 없는 '이력서 넣기 좋은 날'이 분야 기본 12개월 지평을 타 유력 달 종합·기반
    # 최고
    # 달 '누락 금지' 지시와 함께 2027년 달들을 먼저 풀고, 추천일은 여섯째 문단에 묻혔다.
    if intent.query_type is QueryType.DATE_RECOMMENDATION:
        return HorizonPolicy(
            kind="date_window", months_detail=2, years_span=0, natal_fit=False,
            label="택일 탐색 창(오늘부터 약 한 달)",
        )
    if _LONG_TERM_RE.search(question) or intent.time_scope in (
        TimeScope.LONG_TERM,
        TimeScope.LIFE_STAGE,
        TimeScope.DAEWOON_UNIT,
    ):
        return None
    if _OPEN_WHEN_RE.search(question):
        # 개방형 시기 탐색. 사건 키가 잡힌 거래형 생활 사건(매도·계약·이사·취업 등)은 3년 전망 지평
        # (2026-10-14 데굴님 승인 — '부동산은 언제쯤 팔릴까'가 10년 digest 로 2034년까지 서술).
        # 2026-06-18 우려(12개월로 좁히면 특정 달 단정)는 3년 창 + 단정 금지 지시로 받는다.
        # 사건 키가 없는 순수 '언제' 질문은 기존 10년 digest(연도 지정 유도) 유지.
        if intent.event_key is not None:
            return HorizonPolicy(
                kind="transactional_when",
                months_detail=12,
                years_span=3,
                natal_fit=False,
                label="앞 12개월 월 단위 + 이후 2년 연 단위(총 3년)",
            )
        return None
    # 직장 이탈 계열(해고·퇴사 통보·권고사직 — 한 계열, 2026-10-13)도 퇴사와 같은 구조 결정형이다.
    # 단 이미 겪은 보고일 때만 — "해고 당할까?"(미발생 걱정)는 전망형 경로로 둔다(2026-10-14 검수).
    if _STRUCTURAL_RE.search(question) or (
        is_job_separation(question) and intent.dialogue_act == "reported_event"
    ):
        return HorizonPolicy(
            kind="structural",
            months_detail=3,
            years_span=5,
            natal_fit=True,
            label="원국 적합성 + 현재 대운 + 향후 5년(연 단위) + 당장 3개월",
        )
    if _IMMEDIATE_RE.search(question):
        return HorizonPolicy(
            kind="immediate", months_detail=3, years_span=0, natal_fit=False, label="향후 3개월"
        )
    if _VENTURE_RE.search(question):
        return HorizonPolicy(
            kind="venture",
            months_detail=6,
            years_span=5,
            natal_fit=False,
            label="향후 6개월(월 단위) + 5년(연 단위)",
        )
    months = DEFAULT_PERIOD_MONTHS.get(intent.domain, 3)
    return HorizonPolicy(
        kind="domain_default",
        months_detail=months,
        years_span=0,
        natal_fit=False,
        label=f"향후 {months}개월",
    )


def month_add(label: str, months: int) -> str:
    """'YYYY-MM' 라벨에 개월 수를 더한 라벨(창의 끝 계산용)."""
    year, month = int(label[:4]), int(label[5:7])
    idx = (month - 1) + months
    return f"{year + idx // 12}-{idx % 12 + 1:02d}"


def horizon_directive(policy: HorizonPolicy) -> str:
    """지평 강제 디렉티브 — 지평 밖 서술 금지 + 마지막 한 줄 안내만 허용."""
    parts = [
        f"[답변 지평] 이 질문의 답변 지평은 '{policy.label}'이다. "
        "제공된 자료에 더 먼 연·월이 있어도 이 지평 밖 기간은 본문에서 서술하지 말 것."
    ]
    if policy.natal_fit:
        parts.append(
            "이 질문은 인생 구조를 바꾸는 결정이다 — ① 원국 기준 적합성(격국·용신·성향)을 "
            "먼저 판단하고 ② 현재 대운 배경 ③ 향후 5년 연 단위 흐름 ④ 당장 3개월의 "
            "움직임 순으로 구성하라."
        )
    elif policy.kind == "date_window":
        parts.append(
            "사용자는 '날'을 물었다 — 첫 문단에서 [택일 "
            "결과]의 추천일을 먼저 제시하고 날마다 이유를 "
            "한 줄씩 붙여라. 월운은 그 날의 배경으로 한두 "
            "줄만 쓰고, 탐색 창 밖의 달·해(내년 용신운 "
            "등)는 서술하지 말 것. 회피일은 표에 적힌 날짜를 그대로 나열하고, 추천일이 끼는 구간"
            "('○일부터 ○일까지')으로 묶지 말 것."
        )
    elif policy.kind == "transactional_when":
        parts.append(
            "사용자는 '언제'를 물었다 — 앞 12개월은 월 단위로 짚고 그 뒤 2년은 연(세운) 단위 큰 "
            "줄기만 요약하라. 결론은 유력 구간 1~2개로 말하되 특정 달을 단정하지 말고, 사건 후보가 "
            "있는 달만 실행·계약 가능 시기로 들 것."
        )
    elif policy.years_span and policy.months_detail:
        parts.append(
            f"당장의 흐름은 향후 {policy.months_detail}개월을 월 단위로 구체적으로 짚고, "
            f"그 뒤는 {policy.years_span}년 연(세운) 단위 큰 줄기만 요약하라."
        )
    elif policy.months_detail:
        parts.append(
            f"향후 {policy.months_detail}개월의 월 단위 흐름에 집중하라 — "
            "연 단위 장기 나열은 하지 말 것."
        )
    if policy.entry_window:
        parts.append(ENTRY_WINDOW_DIRECTIVE)
    parts.append(
        "더 먼 시기의 흐름은 답변 끝에 '더 긴 흐름이 궁금하면 이어서 물어봐 달라'는 "
        "한 줄 안내만 허용한다(그 한 줄에 구체 연도·간지·길흉을 담지 말 것)."
    )
    return " ".join(parts)
