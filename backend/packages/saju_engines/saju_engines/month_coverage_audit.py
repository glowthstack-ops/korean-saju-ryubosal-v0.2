"""월 커버리지 출력 감사 — 기반 최고 달 누락·비후보 달 결정 권고를 LLM 재호출 없이 교정.

배경(2026-09-18 데굴님 지시, 전문가 반박 사례): 12개월 이직운 답변이 엔진이 "[기반 최고 달]
2026-10(강한 용신운) — 반드시 한 번 짚을 것"으로 명시한 달을 통째로 건너뛰고, 이직 후보에
없는 2027-01(용신운 부분, luck_score 0.24)을 "적극 수락·실행" 달로 격상했다. 두 가지 모두
프롬프트 지시는 있었으나 LLM이 따르지 않은 준수 결함이며, 사후 검사가 없어 그대로 전달됐다.

원칙(period_v2_config 모듈 docstring — 재생성 철회 확정):
- **LLM 재호출 없음.** 검사는 결정론이고 교정은 엔진 확정값으로 만든 템플릿 문장 삽입이다.
- 답변 본문은 지우지 않는다(관계 의미 패치와 달리 '역전'이 아니라 '누락/과장'이라, 원문을
  살린 채 엔진 기준을 덧붙이는 편이 정보 손실이 적다).
- 검사 ①(기반 최고 달 누락): 엔진이 지목한 달의 '연·월'/'N월'/간지가 답변 어디에도 없으면 위반.
- 검사 ②(비후보 달 격상): 이벤트 후보·상담 결론에 없는 달을 언급한 문장이 결정 행동어
  (수락·계약 체결·도장·입사·실행에 옮김 등)를 담으면 위반. 부정·유보 문맥("~보다는", "미루",
  "삼가")이나 허용 달을 함께 언급한 문장은 모호하므로 건드리지 않는다(보수적).

이 모듈은 순수 함수만 둔다(사이드이펙트 없음) — chat_service가 플래그로 호출한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from saju_shared_types.llm_input import MonthOverviewRow

# 기반 최고 달 지목 우선순위(길 방향 등급만) — context_reducer._BEST_GRADE_PRIORITY와 동일 규격.
BEST_GRADE_PRIORITY: tuple[str, ...] = ("강한 용신운", "용신운(부분)")

# 결정 단계 행동어 — "이 달에 하라"는 권고로 읽히는 술어만(서술·경고 어휘 제외).
_DECISION_RE = re.compile(
    r"수락|계약(?:을|서를)?\s*(?:체결|진행|맺|하)|도장을\s*찍|입사|서명|"
    r"실행에\s*옮|이직을\s*(?:진행|실행|단행)|결정(?:을|하시|하셔|하는\s*것)|사인"
)
# 부정·유보 문맥 — 같은 문장에 있으면 "하지 말라"는 뜻일 수 있어 위반으로 잡지 않는다.
_NEGATION_RE = re.compile(r"보다는|말고|삼가|미루|피하|금물|않|마세요|말(?:아야|것)")
# 월 언급 — '2027년 1월' / '1월'. '12개월' 같은 기간 표현은 숫자 뒤가 '개'라 걸리지 않는다.
_MONTH_RE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월(?!\s*간)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")


@dataclass(frozen=True)
class PromotedSentence:
    """비후보 달에 결정 권고를 붙인 문장 1건."""

    sentence: str
    periods: tuple[str, ...]  # 그 문장이 가리킨 비허용 달(YYYY-MM)


@dataclass
class MonthCoverageAudit:
    """감사 결과 — 위반 목록과 교정에 필요한 엔진 확정값."""

    missing_best: list[MonthOverviewRow] = field(default_factory=list)
    promoted: list[PromotedSentence] = field(default_factory=list)
    allowed_periods: tuple[str, ...] = ()

    @property
    def violations(self) -> list[str]:
        """로그용 위반 종류 목록."""
        out: list[str] = []
        if self.missing_best:
            out.append("best_month_missing")
        if self.promoted:
            out.append("non_candidate_month_promoted")
        return out

    @property
    def passed(self) -> bool:
        """위반이 하나도 없으면 True."""
        return not self.violations


def best_quality_rows(rows: list[MonthOverviewRow], limit: int = 3) -> list[MonthOverviewRow]:
    """그 기간 운 품질 최고 행(강한 용신운 우선, 없으면 용신운 부분) — 최대 limit개.

    길 방향 등급만 대상이다(기신·혼합은 '좋은 달'로 지목하지 않는다).
    """
    for grade in BEST_GRADE_PRIORITY:
        hits = [r for r in rows if r.luck_grade == grade]
        if hits:
            return hits[:limit]
    return []


def _period_parts(period: str) -> tuple[int, int | None]:
    """'2026-10' → (2026, 10), '2026' → (2026, None)."""
    if len(period) >= 7 and period[4] == "-":
        return int(period[:4]), int(period[5:7])
    return int(period[:4]), None


def _mentions_period(text: str, row: MonthOverviewRow) -> bool:
    """답변이 그 행(달/해)을 언급했는가 — 연·월 표기, 'N월'(같은 달 번호), 간지 중 하나."""
    year, month = _period_parts(row.period)
    if row.ganji and row.ganji in text:
        return True
    if month is None:
        return f"{year}년" in text
    for m in _MONTH_RE.finditer(text):
        y_txt, m_txt = m.group(1), m.group(2)
        if int(m_txt) != month:
            continue
        if y_txt is None or int(y_txt) == year:
            return True
    return False


def _resolve_month_mentions(sentence: str, window: list[MonthOverviewRow]) -> list[str]:
    """문장 속 월 언급을 창 안의 기간 라벨(YYYY-MM)로 해석한다. 창 밖 언급은 버린다.

    연도 없는 'N월'은 창에서 같은 달 번호를 가진 기간 전부로 해석한다(창이 12개월을 넘으면
    복수 — 그중 하나라도 허용 달이면 호출자가 모호로 처리한다).
    """
    out: list[str] = []
    for m in _MONTH_RE.finditer(sentence):
        y_txt, mo = m.group(1), int(m.group(2))
        for row in window:
            year, month = _period_parts(row.period)
            if month != mo:
                continue
            if y_txt is not None and int(y_txt) != year:
                continue
            if row.period not in out:
                out.append(row.period)
    return out


def audit_month_coverage(
    answer: str,
    rows: list[MonthOverviewRow],
    allowed_periods: tuple[str, ...] | list[str],
) -> MonthCoverageAudit:
    """답변을 엔진 확정값(기반 최고 달·행동 허용 달)과 대조한다.

    Args:
        answer: LLM 답변(정규화 후).
        rows: 이번 턴 월별 요약 행(질문 창). 비어 있으면 검사할 것이 없어 통과.
        allowed_periods: 결정 행동을 붙여도 되는 달 = 이벤트 후보 기간(YYYY-MM). 비어 있으면
            검사 ②는 건너뛴다(후보가 없는 턴에 모든 달을 위반으로 만들지 않기 위해).

    Returns:
        MonthCoverageAudit — 위반이 없으면 passed=True.
    """
    audit = MonthCoverageAudit(allowed_periods=tuple(dict.fromkeys(allowed_periods)))
    if not answer or not rows:
        return audit
    audit.missing_best = [r for r in best_quality_rows(rows) if not _mentions_period(answer, r)]

    monthly = [r for r in rows if len(r.period) >= 7]
    if not audit.allowed_periods or not monthly:
        return audit
    allowed = set(audit.allowed_periods)
    for paragraph in answer.split("\n\n"):
        # 문단 안에서는 직전 문장이 세운 달이 이어진다 — 실로그: "2027년 1월 辛丑월은 …
        # 때입니다. 이때 들어오는 … 수락하여 실행에 옮기셔도 좋습니다."처럼 달과 권고가
        # 문장을 나눠 쓰인다. 문단이 바뀌면 승계를 끊는다(다른 달 문맥 오염 방지).
        carried: list[str] = []
        for sentence in _SENTENCE_SPLIT_RE.split(paragraph):
            s = sentence.strip()
            if not s:
                continue
            mentioned = _resolve_month_mentions(s, monthly)
            if mentioned:
                carried = mentioned
            if not _DECISION_RE.search(s) or _NEGATION_RE.search(s):
                continue
            periods = mentioned or carried
            if not periods or any(p in allowed for p in periods):
                continue  # 달 문맥 없음 / 허용 달 동반(모호) — 건드리지 않는다
            audit.promoted.append(PromotedSentence(sentence=s, periods=tuple(periods)))
    return audit


def _period_ko(period: str, ganji: str = "") -> str:
    """'2026-10'+'戊戌' → '2026년 10월(戊戌월)', '2027' → '2027년'."""
    year, month = _period_parts(period)
    base = f"{year}년" if month is None else f"{year}년 {month}월"
    unit = "년" if month is None else "월"
    return f"{base}({ganji}{unit})" if ganji else base


def build_coverage_notes(audit: MonthCoverageAudit, rows: list[MonthOverviewRow]) -> list[str]:
    """위반별 교정 문단(엔진 확정값만 사용, 단정 표현 없음). 위반이 없으면 빈 목록."""
    notes: list[str] = []
    if audit.missing_best:
        items = " · ".join(
            f"{_period_ko(r.period, r.ganji)}, {r.luck_grade}" for r in audit.missing_best
        )
        unit = "해" if any(len(r.period) < 7 for r in audit.missing_best) else "달"
        notes.append(
            f"덧붙여 엔진 기준으로 이 기간에 기반(전반 운)이 가장 좋은 {unit}은 {items}입니다. "
            f"질문하신 사건의 두드러진 신호가 이 {unit}에 없더라도, 준비와 기반 다지기에 "
            "가장 도움이 되는 시기로 봐 두시면 좋습니다."
        )
    if audit.promoted:
        ganji_of = {r.period: r.ganji for r in rows}
        bad = sorted({p for s in audit.promoted for p in s.periods})
        bad_ko = " · ".join(_period_ko(p, ganji_of.get(p, "")) for p in bad)
        ok_ko = " · ".join(_period_ko(p, ganji_of.get(p, "")) for p in audit.allowed_periods)
        notes.append(
            f"※ 엔진 기준으로 이 사건의 결정 단계(수락·계약) 판단 재료가 있는 달은 {ok_ko}입니다. "
            f"{bad_ko}은(는) 사건 후보에 오르지 않은 달이라 실행보다는 준비·검토 단계로 보는 편이 "
            "맞습니다."
        )
    return notes


def patch_month_coverage(answer: str, notes: list[str]) -> str:
    """교정 문단을 답변에 삽입한다 — 마지막 문단이 되묻기(?)면 그 앞에, 아니면 끝에.

    본문은 지우지 않는다. notes가 비어 있으면 원문 그대로 반환.
    """
    if not notes:
        return answer
    block = "\n\n".join(notes)
    parts = answer.rstrip().rsplit("\n\n", 1)
    if len(parts) == 2 and parts[1].strip().endswith("?"):
        return f"{parts[0]}\n\n{block}\n\n{parts[1]}"
    return f"{answer.rstrip()}\n\n{block}"
