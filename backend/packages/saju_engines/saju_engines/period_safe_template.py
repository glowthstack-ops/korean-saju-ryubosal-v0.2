"""총운 안전 템플릿 — 엔진 데이터만으로 조립하는 폴백 답변 (2026-07-27 데굴님 확정).

패치로도 관계 역전을 복구하지 못했을 때 **추가 LLM 호출 없이** 서버가 답변을 조립한다.
표현의 화려함은 줄어들지만, 사실관계가 틀린 재생성보다 서비스 품질이 높다는 판단이다.

원칙: 여기 들어가는 모든 문장은 엔진 확정값(간지·유불리·관계 판정·슬롯 상태)에서만
나온다. 새로운 명리 판단을 하지 않는다(절대원칙 1·10).

2026-10-13 보완(데굴님 승인): 사용자가 그대로 보는 문장이므로 ①LLM 지시문이 붙은
`solar_month_note` 대신 사용자용 `solar_month_user_note`만 쓰고 ②내부 점수·슬롯 코드가
드러나는 슬롯 요약('의사결정운 50 — …', '점수 …')은 내보내지 않는다.
"""

from __future__ import annotations

import re

from saju_shared_types.llm_input import PeriodFortune, PeriodFortuneSlot

_TYPE_KO = {"daily": "이 날", "monthly": "이 달", "yearly": "이 해"}

#: 내부 점수 자체가 요약인 슬롯 — 사용자 문장으로 번역할 재료가 없어 제외한다.
_INTERNAL_SLOT_NAMES = frozenset({"활용법", "행동전략", "일·돈·관계·건강"})
#: 숫자 점수가 드러나는 요약('점수 62'·'의사결정운 50 — …').
_SCORE_SUMMARY = re.compile(r"^점수|의사결정운|\d+\s*—")


def _user_facing_slots(slots: list[PeriodFortuneSlot]) -> list[PeriodFortuneSlot]:
    """사용자에게 그대로 보여도 되는 슬롯만 남긴다(간지·주의일 등 사실 재료)."""
    return [
        s for s in slots
        if s.name not in _INTERNAL_SLOT_NAMES
        and s.summary
        and not _SCORE_SUMMARY.search(s.summary)
    ]


def build_safe_period_answer(pf: PeriodFortune) -> str:
    """총운 블록만으로 조립한 안전 답변.

    Args:
        pf: 이번 턴 총운 블록(엔진 확정값).

    Returns:
        사용자에게 그대로 전달 가능한 한국어 답변.
    """
    unit = _TYPE_KO.get(pf.fortune_type, "이 기간")
    parts: list[str] = [f"{pf.period_label} {pf.ganji} 기준으로 정리해 드릴게요."]

    if pf.luck_label or pf.luck_summary:
        joined = " — ".join(x for x in (pf.luck_label, pf.luck_summary) if x)
        parts.append(f"{unit}의 전체 기운은 {joined}이에요.")
    # 절기월 안내는 사용자용 문장만 — solar_month_note는 LLM 지시문이 붙은 프롬프트 전용.
    if pf.solar_month_user_note:
        parts.append(pf.solar_month_user_note)

    # 관계는 엔진 확정 문장을 그대로 쓴다(자유 서술 금지).
    claims = [s.canonical_claim for s in pf.relation_semantics if s.canonical_claim]
    if claims:
        parts.append("운에서 들어온 글자가 명식과 맺는 관계는 다음과 같아요.")
        parts += claims

    shown = _user_facing_slots(pf.slots)[:3]
    if shown:
        parts.append(
            "분야별 엔진 판정은 다음과 같아요.\n"
            + "\n".join(f"· {s.name} — {s.summary}" for s in shown)
        )

    parts.append(
        "이번에는 표현을 다듬지 않고 엔진 판정 그대로 전해 드렸어요. "
        "더 자세히 풀어 드릴 부분이 있으면 말씀해 주세요."
    )
    return "\n\n".join(parts)
