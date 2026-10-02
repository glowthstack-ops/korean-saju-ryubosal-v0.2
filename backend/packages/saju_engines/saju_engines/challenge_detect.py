"""이의(challenge) 발화 감지 — 파서 Q12와 대화 링크(CHALLENGE)가 공유하는 단일 규칙.

배경(2026-10-01 실로그 web-mup4m82l): "니가 연두색이나 초록색계열 커튼을 추천해줬잖아"가
파서의 `했잖아` 리터럴에 걸리지 않아 이의가 아니라 **직전 답 말미 되물음에 대한 답**(offer-slot)
으로 링크됐고, LLM은 "이번 발화는 네 질문에 대한 답이다"라는 지시를 받아 자기 추천을 인정하지
않는 답을 냈다. 이의 감지를 한 곳에서 일반화하고, 링크 규칙에서 되물음 답 판정보다 앞에 둔다.

규칙(rules-first, 도메인 무관):
  ① 2인칭 지칭(니가/네가/너가/당신이/너는/넌) + 발화 인용·수행 표지(…했잖/줬잖/랬잖/라고 했/
     그랬/말했/했다) — "니가 추천해줬잖아", "네가 좋다고 했잖아", "너 그랬잖아".
  ② 시점 참조(아까/앞서/방금/조금 전/직전에/처음에/지난번/전 답변) + **발화 동사**(말했/알려줬/
     추천했/얘기했/라고 했/그랬/했다고/라더니/라며) — "아까는 9월이 좋다고 했잖아".
     시점 참조만으로는
     잡지 않는다("3년 전에 이사했잖아"는 사용자 자신의 사실).
  ③ 기존 리터럴(아니야?/틀렸/헷갈려/다시 체크/라던데 맞아/했잖아)은 그대로 유지.
"""

from __future__ import annotations

import re

_SECOND_PERSON = r"(?:니가|네가|너가|당신이|너는|넌|너\s|네[가는]?\s)"
_TIME_REF = r"(?:아까|앞서|방금|조금\s*전|직전에|처음에|지난번|이전\s*답|전\s*답변|앞\s*답변)"
_SPEECH_VERB = (
    r"(?:말했|말해\s*줬|알려\s*줬|알려줬|추천(?:했|해\s*줬|해줬)|얘기했|이야기했|라고\s*했"
    r"|그랬|했다고|라더니|라며|했었|권했|권해\s*줬|골라\s*줬|짚어\s*줬|써\s*줬"
    r"|알려\s*준|말한|말해\s*준|추천한|추천해\s*준|얘기한)"
)
_QUOTE_END = r"(?:[했줬랬댔봤왔갔]잖|라고\s*했|그랬|말했|했다)"

CHALLENGE_RE = re.compile(
    rf"{_SECOND_PERSON}[^.!?\n]{{0,30}}?{_QUOTE_END}"
    rf"|{_TIME_REF}[^.!?\n]{{0,30}}?{_SPEECH_VERB}"
    r"|아니야\s*\?|틀렸|헷갈려|다시\s*체크|라던데\s*맞아|했잖아|라고\s*했잖"
)
# 사용자 자신의 발화·사실 절 — "내가 아까 말한 아들 사주로", "3년 전에 이사했잖아". 시점 참조·
# `했잖아` 리터럴이 걸려도 그 절의 주어가 1인칭이거나 '…전에'의 과거 사실이면 이의가 아니다.
_FIRST_PERSON_RE = re.compile(r"(?:내가|나는|난\s|제가|저는|우리가)")
_PAST_FACT_RE = re.compile(r"\d+\s*(?:년|개월|달|주|일)\s*전에")
_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n]+")


def _clause_at(text: str, pos: int) -> str:
    start = 0
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        if m.start() >= pos:
            return text[start:m.start()]
        start = m.end()
    return text[start:]


def is_challenge(text: str) -> bool:
    """직전 답변(시스템 발언)에 대한 이의·인용 반문이면 True.

    걸린 절에 2인칭 지칭이 없고 1인칭 주어("내가 아까 말한 …")나 과거 사실 표지("3년 전에
    이사했잖아")가 있으면 사용자 자신의 발화·사실이라 이의로 보지 않는다.
    """
    for m in CHALLENGE_RE.finditer(text):
        clause = _clause_at(text, m.start())
        if re.search(_SECOND_PERSON, clause):
            return True  # 2인칭 지칭이 있으면 사용자 자신의 절일 수 없다
        if _FIRST_PERSON_RE.search(clause) or _PAST_FACT_RE.search(clause):
            continue  # "내가 아까 말한…", "3년 전에 이사했잖아" — 사용자 자신의 발화·사실
        return True
    return False
