"""추첨·선발·배치 질문 감지 (2026-07-14 설계 §9, rules-first·shadow-first).

사용자 표현을 selection_allocation 도메인·단계로 매핑한다. 기존 질문 분류
(EventKey·QueryType)를 바꾸지 않는 **병행 감지 계층**이다 — 감지되면 chat이
설명 보조 지시문(선발·배치 풀이 블록)을 덧붙일 뿐, 실행 경로·점수는 불변.

가드: 로또·복권·연금복권은 생활형 횡재 정책(절대원칙 8)이 관할하므로 여기서
감지하지 않는다. "군입대 단일 인텐트로 묶지 말 것" — 단계별 분리가 목적이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from saju_shared_types.selection_allocation import ObjectiveOdds, SelectionStage

# 횡재 정책 관할 — 이 표현이 있으면 selection 레이어 비개입.
_WINDFALL_RE = re.compile(r"로또|복권|연금\s*복권|스피또|토토|경마")

# 도메인 감지(구체 도메인 우선, generic 폴백). 값 = (어댑터 키, 정규식).
_DOMAIN_RES: list[tuple[str, re.Pattern[str]]] = [
    ("military_service", re.compile(
        r"군\s*입대|입영|병무|모집병|특기병|카투사|의무경찰|해군|공군|육군"
        r"|군대.{0,8}(?:지원|추첨|모집|신청|가고|갈)|입대"
    )),
    ("housing_subscription", re.compile(
        r"청약|행복\s*주택|국민\s*임대|장기\s*전세|공공\s*임대|임대\s*주택"
        r"|LH|SH|사전\s*청약"
    )),
    ("dormitory_assignment", re.compile(r"기숙사")),
    ("school_assignment", re.compile(
        r"(?:학교|중학교|고등학교|유치원|어린이집|캠퍼스|반)\s*(?:배정|추첨)"
        r"|배정.{0,6}(?:학교|유치원|어린이집)|교환\s*학생|전공\s*배정"
    )),
    ("workplace_assignment", re.compile(
        r"발령|(?:근무지|부서|지점|팀)\s*(?:배치|배정|이동)|사택"
    )),
    ("public_program", re.compile(
        r"지원\s*사업|보조금.{0,6}(?:선정|신청)|공공\s*근로|바우처|국가\s*장학"
    )),
    ("event_ticketing", re.compile(r"티켓팅|티케팅|(?:콘서트|공연|좌석).{0,6}추첨|응모")),
]
# generic 폴백 — 추첨·선발·배치 일반 표현(도메인 미상). '당첨'은 횡재 가드 뒤에서만.
_GENERIC_RE = re.compile(r"추첨|당첨|선발|공모|모집.{0,6}(?:지원|신청)|대기\s*(?:번호|순번)")

# 단계 감지(구체 단계 우선 — 희망 조건 > 대기 > 자격 > 적응 > 실행 > 배정 > 지원 > 선발).
_STAGE_RES: list[tuple[SelectionStage, re.Pattern[str]]] = [
    (SelectionStage.PREFERENCE_MATCH, re.compile(
        r"원하는\s*(?:날짜|날|달|월|시기|지역|동네|동|호수|특기|부대|학교|반|조건|곳"
        r"|자리)|1\s*지망|지망\s*(?:대로|순위)|희망\s*(?:조건|일자|월|지역|특기)"
    )),
    # 대기·추가 선발은 별도 단계가 아니라 selection의 waitlist 시나리오.
    (SelectionStage.SELECTION, re.compile(r"대기\s*(?:번호|순번|자).{0,8}(?:빠질|될|가능)")),
    (SelectionStage.ELIGIBILITY, re.compile(
        r"자격.{0,8}(?:될|문제|통과|되나|미달)|서류.{0,6}(?:통과|문제)|조건.{0,6}(?:맞|충족)"
    )),
    (SelectionStage.ADAPTATION, re.compile(r"적응|잘\s*지낼|버틸|만족할")),
    (SelectionStage.EXECUTION, re.compile(
        r"실제로.{0,8}(?:들어가|입주|입영|입학|가게)|언제.{0,6}(?:입대|입영|입주|입학)"
        r"|(?:입대|입영|입주|입학).{0,4}(?:언제|하게\s*될)"
    )),
    (SelectionStage.ALLOCATION, re.compile(r"배정|배치")),
    (SelectionStage.APPLICATION, re.compile(
        r"(?:지원|신청|넣어).{0,6}(?:해도|해\s*볼|할까|될까|괜찮)"
    )),
    (SelectionStage.SELECTION, re.compile(r"당첨|붙을|뽑힐|선발될|될까|합격")),
]

# 재지원 신호 — 단계는 selection 유지, 대기·다음 회차 시나리오 강조.
_REAPPLY_RE = re.compile(r"떨어지면|다음\s*(?:회차|모집|차수|기회)|재지원|다시\s*넣")


@dataclass(frozen=True)
class SelectionQuery:
    """선발·배치 질문 감지 결과."""

    domain: str  # SELECTION_DOMAIN_ADAPTERS 키
    stage: SelectionStage
    waitlist_focus: bool = False  # 대기·재지원 시나리오 강조
    explicit_domain: bool = False  # 구체 도메인 매칭(generic 폴백 아님)
    odds: ObjectiveOdds | None = None  # 발화 속 객관 경쟁률(분리 표기 전용)


# 객관 경쟁률 표현(설계 §8) — "경쟁률 5대 1", "1000명 중 200명", "당첨 확률 20%".
_ODDS_RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:대|:)\s*1")
_ODDS_SEATS_RE = re.compile(r"(\d[\d,]*)\s*명?\s*중(?:에서)?\s*(\d[\d,]*)\s*명")
_ODDS_PCT_RE = re.compile(r"(?:경쟁률|확률|당첨률)\s*(?:이|은|는)?\s*(\d+(?:\.\d+)?)\s*%")


def parse_objective_odds(text: str) -> ObjectiveOdds | None:
    """발화에서 객관 경쟁률을 추출한다 — 사주 해석과 혼합 금지(분리 표기 전용).

    지원 형태: 'N대 1'/'N:1'(경쟁률), 'A명 중 B명'(정원/지원), '확률 N%'.
    수치가 없으면 None — 엔진은 객관 확률을 임의로 만들지 않는다.
    """
    m = _ODDS_SEATS_RE.search(text)
    if m:
        applicants = int(m.group(1).replace(",", ""))
        seats = int(m.group(2).replace(",", ""))
        if applicants > 0 and seats <= applicants:
            return ObjectiveOdds(
                applicants=applicants, seats=seats,
                base_probability=round(seats / applicants, 4),
            )
    m = _ODDS_RATIO_RE.search(text)
    if m:
        ratio = float(m.group(1))
        if ratio >= 1:
            return ObjectiveOdds(base_probability=round(1.0 / ratio, 4))
    m = _ODDS_PCT_RE.search(text)
    if m:
        pct = float(m.group(1))
        if 0 < pct <= 100:
            return ObjectiveOdds(base_probability=round(pct / 100.0, 4))
    return None


# 후속 승계용 강한 단계 신호 — 도메인 단어 없는 후속("그래서 원하는 날짜로 갈 수
# 있다는 거야?")에서 직전 답변의 선발 맥락을 이어받는 조건(설계 §9 멀티턴).
_STRONG_STAGE_RE = re.compile(
    r"원하는\s*(?:날짜|날|달|월|시기|지역|동네|동|호수|특기|부대|조건|곳|자리)"
    r"|1\s*지망|지망|배정|배치|대기\s*(?:번호|순번)"
)


def _match_domain(text: str) -> str | None:
    """구체 도메인 매칭(횡재 가드 통과 후 호출)."""
    for key, rx in _DOMAIN_RES:
        if rx.search(text):
            return key
    return None


def detect_selection_query(
    text: str, prior_text: str | None = None
) -> SelectionQuery | None:
    """질문 → 선발·배치 도메인·단계. 해당 없으면 None(기존 경로 불변).

    generic 폴백은 추첨·선발 표현이 명시된 경우만 — '합격'·'될까' 단독은 기존
    시험·경쟁 분류가 관할하므로 여기서 잡지 않는다(오탐 방지). prior_text(직전
    답변)가 주어지면, 도메인 단어 없는 후속이라도 강한 단계 신호가 있으면 직전
    맥락의 도메인을 승계한다 — turn2 "그래서 원하는 날짜로 갈 수 있다는 거야?"가
    선발 전체 재풀이 대신 preference_match만 잇게 하는 설계 §9 요건.
    """
    if _WINDFALL_RE.search(text):
        return None  # 생활형 횡재 정책 관할(원칙 8)
    domain = _match_domain(text)
    explicit = domain is not None
    if domain is None and not _GENERIC_RE.search(text):
        # 후속 승계 — 현재 발화에 강한 단계 신호 + 직전 답변에 선발 맥락.
        if prior_text is None or not _STRONG_STAGE_RE.search(text):
            return None
        if _WINDFALL_RE.search(prior_text):
            return None
        domain = _match_domain(prior_text)
        if domain is None and not _GENERIC_RE.search(prior_text):
            return None
    if domain is None:
        domain = "generic"
    stage = SelectionStage.SELECTION
    for st, rx in _STAGE_RES:
        if rx.search(text):
            stage = st
            break
    waitlist = bool(_REAPPLY_RE.search(text)) or bool(
        re.search(r"대기\s*(?:번호|순번|자)", text)
    )
    return SelectionQuery(
        domain=domain, stage=stage, waitlist_focus=waitlist, explicit_domain=explicit,
        odds=parse_objective_odds(text),
    )
