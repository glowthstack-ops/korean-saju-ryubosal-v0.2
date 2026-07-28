"""커리어 사실 추출 — P3 (CAREER_TRANSITION_SYSTEM §7·§12-6).

**rules-first 정규식**이며 LLM을 쓰지 않는다(절대원칙 1·9). 범용 `user_facts`와 섞지 않고
career 전용 결과를 만든다 — 단계 전이 자격 판정이 도메인마다 다르기 때문.

**전이 자격은 관찰 가능한 사실만**(INV-18·§8):

```
허용: 지원했다 · 면접 봤다 · 서면 오퍼 받았다 · 수락했다 · 통보했다 · 퇴사했다
      · 입사했다 · 부서 이동 완료
차단: 될 것 같다 · 회사가 좋아하는 듯 · 합격할 것 같다 · 분위기 좋았다
      · 사주상 오퍼가 예상된다
```

차단된 발화는 **버리지 않고** `SUBJECTIVE_IMPRESSION`/`COUNTERPARTY_SPECULATION`으로
분류해 남긴다 — 별도 현실 맥락으로 보관할 수 있으나 단계 전이에는 쓰지 못한다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_commands import CareerFactType, FactEvidenceClass
from saju_shared_types.career_transition import (
    EntryScope,
    FactOperationType,
    TimePrecision,
)


class CareerParsedFact(BaseModel):
    """추출된 커리어 사실 1건 — 명령 생성 전 중간 표현."""

    model_config = ConfigDict(frozen=True)

    text: str
    fact_type: CareerFactType | None = None
    evidence_class: FactEvidenceClass = FactEvidenceClass.OBSERVABLE_HARD_FACT
    operation_type: FactOperationType = FactOperationType.ASSERT
    episode_target_hint: str | None = None
    occurred_at: str | None = None
    time_precision: TimePrecision = TimePrecision.UNKNOWN
    correction_target: str | None = None
    #: 진입 범위 — **명시된 경우에만** 채운다(CARR-SCOPE). None은 "외부 이직"이 아니라
    #: "판정 자료 없음"이며 하류에서 coverage bypass로 처리된다.
    entry_scope: EntryScope | None = None
    scope_rule_id: str | None = None
    scope_evidence_text: str | None = None

    @property
    def is_transition_eligible(self) -> bool:
        """단계 전이 자격 — 관찰 가능한 hard fact이고 유형이 확정된 경우만."""
        return (
            self.fact_type is not None
            and self.evidence_class is FactEvidenceClass.OBSERVABLE_HARD_FACT
        )


# 추측·전망 표지 — 하나라도 걸리면 hard fact 로 승격하지 않는다.
_SPECULATION_RE = re.compile(
    r"(것?\s*같|듯|예상|전망|아마|싶다|바란|기대|가능성|運|운이|사주|점괘|보인다|볼 것)"
)
_COUNTERPARTY_RE = re.compile(r"(회사|면접관|담당자|팀장|인사|반응).{0,12}(좋|마음에|뽑|선호|관심)")
_PLANNED_RE = re.compile(r"(할까|하려|예정|계획|고민|생각 중|생각중|볼까|낼까)")

# 관찰 가능한 사실 표지(과거·완료형 우선).
_FACT_PATTERNS: tuple[tuple[re.Pattern[str], CareerFactType], ...] = (
    (re.compile(r"(지원서|원서|이력서).{0,6}(냈|제출|넣었)|지원했"),
     CareerFactType.APPLICATION_SUBMITTED),
    (re.compile(r"면접.{0,6}(봤|보았|치렀|끝났|완료)"), CareerFactType.INTERVIEW_COMPLETED),
    (re.compile(r"(서면|정식|공식)?\s*오퍼.{0,6}(받았|왔|나왔)|합격 통보.{0,4}받았"),
     CareerFactType.WRITTEN_OFFER_RECEIVED),
    (re.compile(r"오퍼.{0,6}(수락|승낙|받아들)|입사.{0,4}(확정|결정)했"),
     CareerFactType.OFFER_ACCEPTED),
    (re.compile(r"(퇴사|사직).{0,6}(통보|말씀|알렸|얘기했|이야기했)"), CareerFactType.NOTICE_GIVEN),
    (re.compile(r"(퇴사|사직|그만).{0,4}(했|뒀|둠|함)|퇴사 완료"), CareerFactType.EXIT_COMPLETED),
    (re.compile(r"(입사|출근).{0,6}(했|시작|개시)|첫 출근"), CareerFactType.JOINED),
    (re.compile(r"(부서|팀|보직).{0,4}(이동|발령).{0,6}(났|됐|되었|완료|끝)"),
     CareerFactType.TRANSFER_COMPLETED),
)

# ── 진입 범위 표지 (CARR-SCOPE) ────────────────────────────────────────────
# **명시된 범위만 읽는다.** fact_type·intent·현재 회사 정보에서 추론하지 않는다:
#   "면접을 봤다" → 외부인지 사내인지 알 수 없다 → None
#   "입사했다"     → 외부 입사로 단정하지 않는다 → None
#   "이직하고 싶다" → hard fact 자체가 없다
# 자료가 없는 것을 추론으로 채우면 F1을 푸는 대신 오귀속을 만든다.
#
# 규칙 순서가 곧 우선순위다 — 더 구체적인 표지(지역·부서·승진)를 앞에 둔다.
# 사내 표지가 있으면 외부 표지보다 먼저 판정한다("사내 공고에 지원").
_SCOPE_PATTERNS: tuple[tuple[re.Pattern[str], EntryScope, str], ...] = (
    (re.compile(r"(지점|지사|사업장|근무지|본사|공장).{0,6}(이동|발령|이전|옮)"
                r"|(서울|부산|대구|인천|광주|대전|울산|세종|제주)\s*(지점|지사|사업장|근무지)"),
     EntryScope.INTERNAL_LOCATION, "SCOPE_INTERNAL_LOCATION"),
    (re.compile(r"(다른|타|옆)\s*(부서|팀|본부)|(부서|팀|본부)\s*(이동|전보|발령|옮)"
                r"|사내\s*(전보|이동)"),
     EntryScope.INTERNAL_DEPARTMENT, "SCOPE_INTERNAL_DEPARTMENT"),
    (re.compile(r"(사내|내부|회사 안|같은 회사).{0,8}(승진|승격|공모|공고|지원|면접|심사)"
                r"|승진\s*(심사|면접|대상|후보|지원)|진급\s*(심사|면접)"),
     EntryScope.INTERNAL_ROLE, "SCOPE_INTERNAL_ROLE"),
    (re.compile(r"(다른|타|새|외부|딴)\s*(회사|기업|직장|데)|이직|경력직|헤드헌|스카우"
                r"|(회사|기업)\s*(면접|지원|공고)"),
     EntryScope.EXTERNAL_EMPLOYER, "SCOPE_EXTERNAL_EMPLOYER"),
)

# 발생 시점 힌트(정밀도만 결정 — 실제 날짜 해소는 호출자 몫).
_TIME_HINTS: tuple[tuple[re.Pattern[str], TimePrecision], ...] = (
    (re.compile(r"(어제|오늘|그저께)"), TimePrecision.DAY),
    (re.compile(r"(지난달|저번 달|이번 달|다음 달)"), TimePrecision.MONTH),
    (re.compile(r"(지난주|저번 주|이번 주)"), TimePrecision.DAY),
    (re.compile(r"(작년|재작년|올해)"), TimePrecision.APPROXIMATE),
)


def _classify_evidence(text: str) -> FactEvidenceClass:
    """증거 등급 — 추측·상대 의향은 hard fact 가 아니다."""
    if _COUNTERPARTY_RE.search(text):
        return FactEvidenceClass.COUNTERPARTY_SPECULATION
    if _SPECULATION_RE.search(text):
        return FactEvidenceClass.SUBJECTIVE_IMPRESSION
    return FactEvidenceClass.OBSERVABLE_HARD_FACT


def _parse_entry_scope(text: str) -> tuple[EntryScope | None, str | None, str | None]:
    """명시된 진입 범위만 읽는다 (CARR-SCOPE).

    Args:
        text: 사용자 발화.

    Returns:
        `(범위, 규칙 id, 근거 구절)`. 명시가 없으면 `(None, None, None)` —
        기본값을 정하지 않는다. 근거 구절은 감사 전용이며 사용자에게 노출하지 않는다.
    """
    for pattern, scope, rule_id in _SCOPE_PATTERNS:
        found = pattern.search(text)
        if found:
            return scope, rule_id, found.group(0)
    return None, None, None


def _time_precision(text: str) -> TimePrecision:
    for pattern, precision in _TIME_HINTS:
        if pattern.search(text):
            return precision
    return TimePrecision.UNKNOWN


def parse_career_fact(text: str) -> CareerParsedFact:
    """발화 1건에서 커리어 사실을 추출한다(순수 함수).

    유형을 찾지 못하거나 hard fact 가 아니면 `is_transition_eligible`이 False다 —
    그래도 결과는 남겨 별도 현실 맥락으로 보관할 수 있게 한다.
    """
    evidence = _classify_evidence(text)
    # 계획·고민 표현은 완료 사실로 승격하지 않는다("퇴사할까 고민 중").
    planned = bool(_PLANNED_RE.search(text))
    fact_type: CareerFactType | None = None
    for pattern, ftype in _FACT_PATTERNS:
        if pattern.search(text):
            fact_type = ftype
            break
    if planned and evidence is FactEvidenceClass.OBSERVABLE_HARD_FACT:
        # "다음 주 입사 예정"·"퇴사할까 고민 중" 류 — 계획·고민은 확정 사실이 아니다.
        evidence = FactEvidenceClass.SUBJECTIVE_IMPRESSION
    scope, scope_rule_id, scope_text = _parse_entry_scope(text)
    return CareerParsedFact(
        text=text,
        fact_type=fact_type,
        evidence_class=evidence,
        time_precision=_time_precision(text),
        entry_scope=scope,
        scope_rule_id=scope_rule_id,
        scope_evidence_text=scope_text,
    )


__all__ = ["CareerParsedFact", "parse_career_fact"]
