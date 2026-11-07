"""육친 성별 기준 주장 감사 — 결정론·재호출 없음 (2026-11-07).

실답(총운 F-06b, 남성 명식): 입력에 '남성=재성 아내·관성 자녀' 가드가 있어도 산출문이 "관성이
드러나지 않은 구조라 결혼이라는 현실적인 책임을 무겁게 느낀다"처럼 여성 기준(관성=남편) 해석을
섞었다.
문장 단위로 ①배우자성 반대 축 용어 ②결혼·배우자 용어가 같이 나오고 ③올바른 축 설명·부정문이 아닌
문장을 위반으로 기록한다. 리포트는 soft 위반(재생성 없음), 채팅은 로그 — 재발 빈도를 본 뒤 패치 여부
결정(검수는 실사용 답변으로).
"""

from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_OFFICER_TERMS = ("관성", "정관", "편관", "관살")
_WEALTH_TERMS = ("재성", "정재", "편재")
_MARRIAGE_TERMS = ("결혼", "배우자", "아내", "남편", "혼인", "부부", "신랑", "신부")
#: 올바른 축이 함께 설명된 문장은 제외 — 남성: 관성을 자녀·직장 축으로 쓴 문장.
_MALE_OK_TERMS = ("자녀", "자식", "직장", "직위", "명예", "규율", "직업", "승진", "조직")
#: 여성: 재성을 시댁·물질 축으로 쓴 문장.
_FEMALE_OK_TERMS = ("시댁", "물질", "재물", "경제", "돈", "유지 욕구")
#: 부정문('관성은 배우자가 아니라 …') — 단순 '않/없'은 위반 문장 자체에 흔해 쓰지 않는다.
_NEGATION = re.compile(r"(배우자|아내|남편|결혼)(이|가|은|는|와|과)?\s*아니")


def audit_gender_kin_claims(text: str, gender: str | None) -> list[str]:
    """성별 기준에 어긋난 육친 주장 문장을 찾는다.

    Args:
        text: 답변·섹션 본문.
        gender: 'male'/'female' — 그 외는 감사하지 않는다(빈 목록).

    Returns:
        위반 문장 앞 80자 목록(없으면 빈 목록).
    """
    star_terms: tuple[str, ...]
    ok_terms: tuple[str, ...]
    if gender == "male":
        star_terms, ok_terms = _OFFICER_TERMS, _MALE_OK_TERMS
    elif gender == "female":
        star_terms, ok_terms = _WEALTH_TERMS, _FEMALE_OK_TERMS
    else:
        return []
    hits: list[str] = []
    for sent in _SENT_SPLIT.split(text or ""):
        s = sent.strip()
        if not s:
            continue
        if not any(t in s for t in star_terms) or not any(t in s for t in _MARRIAGE_TERMS):
            continue
        if _NEGATION.search(s) or any(t in s for t in ok_terms):
            continue
        hits.append(s[:80])
    return hits
