"""총운 안전 템플릿 — 엔진 데이터만으로 조립하는 폴백 답변 (2026-07-27 데굴님 확정).

패치로도 관계 역전을 복구하지 못했을 때 **추가 LLM 호출 없이** 서버가 답변을 조립한다.
표현의 화려함은 줄어들지만, 사실관계가 틀린 재생성보다 서비스 품질이 높다는 판단이다.

원칙: 여기 들어가는 모든 문장은 엔진 확정값(간지·유불리·관계 판정·슬롯 상태)에서만
나온다. 새로운 명리 판단을 하지 않는다(절대원칙 1·10).
"""

from __future__ import annotations

from saju_shared_types.llm_input import PeriodFortune

_TYPE_KO = {"daily": "이 날", "monthly": "이 달", "yearly": "이 해"}


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
        parts.append(f"{unit}의 전체 기운은 {joined} 입니다.")
    if pf.solar_month_note:
        parts.append(pf.solar_month_note)

    # 관계는 엔진 확정 문장을 그대로 쓴다(자유 서술 금지).
    claims = [s.canonical_claim for s in pf.relation_semantics if s.canonical_claim]
    if claims:
        parts.append("운에서 들어온 글자가 명식과 맺는 관계는 다음과 같습니다.")
        parts += claims

    scored = [s for s in pf.slots if s.summary and not s.summary.startswith("점수")]
    if scored:
        parts.append("분야별로는 " + ", ".join(
            f"{s.name}({s.summary})" for s in scored[:3]
        ) + " 로 나타납니다.")

    parts.append(
        "이번에는 표현을 다듬지 않고 엔진 판정 그대로 전해 드렸어요. "
        "더 자세히 풀어 드릴 부분이 있으면 말씀해 주세요."
    )
    return "\n\n".join(parts)
