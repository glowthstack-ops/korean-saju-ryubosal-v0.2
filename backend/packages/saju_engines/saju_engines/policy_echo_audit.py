"""내부 지시문 에코 차단 (P0.5 — 2026-07-27 데굴님 지적).

프롬프트에 넣은 서술 정책('~ 서술 금지', 'guard_codes' 등)은 LLM 지침이지 사용자
문장이 아니다. LLM이 이를 그대로 답변에 옮겨 적으면 내부 통제 문구가 노출된다.

데이터 분리(문구 후보 / 서술 정책)가 1차 방어이고, 이 모듈은 생성 후 2차 방어다.
발견 시 삭제만 하지 않는다 — 문장이 통째로 사라지면 문맥이 끊기므로, 해당 문장을
지우고 자연스러운 사용자 문장으로 대체할 수 있게 위치를 함께 돌려준다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

#: 내부 지침이 그대로 노출된 흔적. 사용자 문장에는 나올 이유가 없는 표현들이다.
_ECHO_PATTERNS = (
    re.compile(r"서술\s*금지"),
    re.compile(r"표현\s*금지"),
    re.compile(r"단정\s*금지"),
    re.compile(r"확대\s*금지"),
    re.compile(r"옮겨\s*적지"),
    re.compile(r"반드시\s*[^.]{0,20}로만\s*서술"),
    re.compile(r"내부\s*지침|지시문|지침일\s*뿐"),
    re.compile(r"guard_codes|slot_status|raw_status|activation_status"),
    re.compile(r"엔진\s*확정값"),
    re.compile(r"문구\s*후보"),
    re.compile(r"[A-Z]{3,}_[A-Z_]{3,}"),  # LOCAL_FAVORABLE_ONLY 같은 내부 enum
)


class PolicyEcho(BaseModel):
    """정책 문구가 노출된 문장 1건."""

    sentence_index: int
    sentence: str
    matched: str


def detect_policy_echo(answer: str) -> list[PolicyEcho]:
    """답변에 내부 지시문이 그대로 노출됐는지 찾는다.

    Args:
        answer: LLM 답변 원문.

    Returns:
        노출된 문장 목록(없으면 빈 리스트).
    """
    from .relation_claim_audit import split_sentences

    out: list[PolicyEcho] = []
    for sentence in split_sentences(answer):
        for pattern in _ECHO_PATTERNS:
            found = pattern.search(sentence.text)
            if found is None:
                continue
            out.append(PolicyEcho(
                sentence_index=sentence.index,
                sentence=sentence.text,
                matched=found.group(),
            ))
            break
    return out


def strip_policy_echo(answer: str, echoes: list[PolicyEcho]) -> tuple[str, int]:
    """노출된 문장을 제거한다(문장 단위, 앞뒤 공백 정리).

    Args:
        answer: 답변 원문.
        echoes: 감지된 노출 목록.

    Returns:
        (정리된 답변, 제거한 문장 수).
    """
    if not echoes:
        return answer, 0
    from .relation_claim_audit import split_sentences

    sentences = split_sentences(answer)
    targets = {e.sentence_index for e in echoes}
    out = answer
    removed = 0
    for idx in sorted(targets, reverse=True):  # 뒤에서부터 잘라야 오프셋이 안 밀린다
        if idx >= len(sentences):
            continue
        s = sentences[idx]
        out = (out[: s.start] + out[s.end :]).replace("  ", " ")
        removed += 1
    return re.sub(r"\n{3,}", "\n\n", out).strip(), removed
