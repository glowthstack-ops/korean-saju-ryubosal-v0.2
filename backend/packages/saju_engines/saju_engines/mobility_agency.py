"""이동 주체 미상 — 지시문·감사 어구 SSOT (2026-10-15 데굴님 승인, 채팅·리포트 공용).

배경(라이브 실측): 실사례(1980-11-22 09:40 서울 남, 2026-10 戊戌월 실제 권고사직)에 "내가 원해서
나가는 걸까, 회사가 내보내는 걸까"를 물었더니 답이 "외부의 강요에 의한 이탈이라기보다 … 자발적인
성격이 강하며", "단순히 밀려나는 것이 아니라 본인이 주도"로 주체를 단정했다. 이동 시드 문구는
'자의·타의 모두·단정 금지'였고 극성도 '조건부'였다 — **입력 계약은 지켜지고 답변 단계에서 깨진다.**
그래서 지시문으로 막고 로그 전용 결정론 감사(재호출·문장 교체 없음)로 관측한다. 자발·비자발은
용신·기신으로 결정하지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

MOBILITY_AGENCY_DIRECTIVE = (
    "[이동 주체 미상] 직장·역할 이동 후보가 있어도 그 이동이 자발(독립·이직)인지 타의(권고사직·"
    "배치 전환)인지는 사주로 특정할 수 없다. 용신운·강한 운·주도권 같은 근거로 '본인 의지'로 "
    "추정하거나 '밀려나는 것이 아니다'·'외부 강요가 아니다'라고 쓰지 말고, 두 경우를 모두 열어 둔 "
    "채 '이동이 걸릴 수 있는 기간'으로만 말할 것. 사용자가 둘 중 무엇인지 물으면 사주로는 정해지지 "
    "않는다고 답하고, [사용자 제공 사실]에 확인된 사실이 있을 때만 그 사실을 쓸 것."
)
#: 질문이 이동의 주체(자발·타의)를 묻는 어휘.
AGENCY_QUESTION_RE = re.compile(
    r"자발|스스로|원해서|내보내|내보낼|잘리|잘릴|권고사직|해고|타의|자의|밀려|떠밀"
)
#: 지시문·감사 대상 사건(직장·역할 이동).
MOBILITY_EVENT_KEYS: frozenset[str] = frozenset({"career_change"})
#: 답변의 주체 단정 어구 — ①자발 단정 ②타의 부정(비교 부정 '보다' 포함) ③타의 단정.
#: 가능성 병기("…일 수도")는 잡지 않는다.
AGENCY_CLAIM_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:자발적|본인의\s*의지|스스로\s*(?:택|원|선택)|본인이\s*주도)[^.\n]{0,15}"
        r"(?:강하|높|크|성격|쪽|바탕)"
    ),
    re.compile(
        r"(?:밀려나는\s*것이\s*아니|강요[^.\n]{0,10}(?:아니|보다)|타의가\s*아니"
        r"|비자발[^.\n]{0,6}아니)"
    ),
    re.compile(
        r"(?:권고사직|해고|내보내|잘릴)[^.\n]{0,12}(?:가능성이\s*(?:높|크)|확실|될\s*것|분명)"
    ),
)


def _event_key_str(candidate: Any) -> str:
    key = getattr(candidate, "event_key", "")
    return str(getattr(key, "value", key))


def has_mobility_candidate(candidates: Iterable[Any]) -> bool:
    """후보 목록에 직장·역할 이동 사건이 있는가(채팅·리포트 후보 모델 공용)."""
    return any(_event_key_str(c) in MOBILITY_EVENT_KEYS for c in candidates)


def mobility_agency_directive_needed(question: str, candidates: Iterable[Any]) -> bool:
    """지시문이 필요한가 — 질문이 주체(자발·타의)를 묻거나 이동 후보가 실렸을 때."""
    if AGENCY_QUESTION_RE.search(question or ""):
        return True
    return has_mobility_candidate(candidates)


def mobility_agency_claims(text: str) -> list[str]:
    """본문에서 주체 단정 어구를 모은다(결정론, 교체 없음 — 로그용)."""
    return [m.group(0) for rx in AGENCY_CLAIM_RES for m in rx.finditer(text or "")]
