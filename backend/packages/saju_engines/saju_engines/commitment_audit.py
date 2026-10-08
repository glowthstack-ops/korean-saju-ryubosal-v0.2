"""정정·조건 준수 감사(shadow) — 이의 턴 답변을 이전 발언·사용자 조건과 대조한다(2026-10-01).

목표는 "이전 답과 항상 같은 결론"이 아니라
**"결론이 바뀌었다면 바뀐 사실을 인정하고 근거를 밝혔는가"**,
그리고 사용자가 거른 선택지를 다시 내밀지 않았는가다. 1단계는 shadow(로그만, 재생성·교체 없음) —
데굴님 결정(2026-10-01). 로그가 쌓이면 교체 정책을 따로 승인받는다.

검사 3종(결정론, LLM 미사용):
  - no_acknowledgment : 원장 매치가 있는 이의 턴인데 자기 발언을 인정·확인하는 표지가 없다.
  - excluded_reoffered: 사용자가 배제한 선택지 어휘가 추천 수행 문장에 다시 등장한다.
  - effect_assertion  : 색·방향 같은 생활 보완 요소가 심리·성과를 직접 바꾼다는 인과 단정.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .assistant_commitments import _RECOMMEND_RE, content_tokens

# 자기 발언 인정 표지 — 이전 추천을 '했다'고 확인하는 표현. "…드린 말씀이에요"(그런 뜻이었다)는
# 실로그에서 부인에 쓰인 표현이라 인정으로 치지 않는다.
_ACK_RE = re.compile(
    r"맞아요|맞습니다|말씀드렸|말씀드린\s*(?:대로|것처럼|바)|추천(?:했|해\s*드렸|드렸|해\s*드린\s*것)"
    r"|제가\s*(?:앞서|먼저|이전에|직전에|방금|앞에서)|앞서\s*(?:제가|저는|추천|말씀|드린)"
    r"|정정|바로잡|번복|사과|죄송|잘못\s*(?:말씀|안내|추천|했)|앞뒤가\s*맞지"
)
_EFFECT_ASSERT_RE = re.compile(
    r"(?:색|색상|색깔|커튼|벽지|방향|방위)[^.!?\n]{0,24}?(?:때문에|으로\s*인해|탓에)[^.!?\n]{0,24}?"
    r"(?:늘어|줄어|떨어|높아|낮아|무거워|흐려|바뀌)"
    r"|(?:잡생각|집중력|실행력|성적|학업\s*효율)[^.!?\n]{0,10}?(?:이|가|을|를)\s*"
    r"(?:늘려|줄여|높여|낮춰|떨어뜨려|끌어올려)\s*(?:줘요|줍니다|주네요|요\b)"
)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
_CLAUSE_SPLIT_RE = re.compile(r"[,，]|(?<=다면)\s|(?<=라면)\s|(?<=면)\s|(?<=고)\s|(?<=며)\s")
_PIVOT_RE = re.compile(r"부담|대신|말고|빼고|제외|않|싫|거르|어렵다면|곤란")


@dataclass
class CommitmentAuditResult:
    """감사 결과 — violations 가 비면 통과. shadow 단계에서는 로그 재료로만 쓴다."""

    violations: list[str] = field(default_factory=list)
    details: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.violations


def audit_answer(
    answer: str,
    *,
    is_challenge: bool,
    matched_quotes: list[str],
    excluded_quotes: list[str],
) -> CommitmentAuditResult:
    """답변을 정정 계약·배제 조건·효과 단정 기준으로 감사한다(순수 함수).

    Args:
        answer: LLM 답변 본문.
        is_challenge: 이번 턴이 이의(challenge/recheck) 턴인가.
        matched_quotes: 프롬프트에 주입된 이전 발언 원문(비면 인정 검사 생략).
        excluded_quotes: 사용자 배제 조건 인용("붉은색은 좀 그래").
    """
    res = CommitmentAuditResult()
    if not answer:
        return res
    if is_challenge and matched_quotes and not _ACK_RE.search(answer):
        res.violations.append("no_acknowledgment")
        res.details["no_acknowledgment"] = [q[:60] for q in matched_quotes[:3]]
    if excluded_quotes:
        # 표면형 토큰(정규화 없음) — 거른 것은 '붉은색'이라는 특정 선택지다(분홍 제안은 재제시
        # 아님).
        excl_tokens: set[str] = set()
        for q in excluded_quotes:
            excl_tokens |= content_tokens(q, normalize=False)
        hits: list[str] = []
        for sent in _SENT_SPLIT_RE.split(answer):
            if not _RECOMMEND_RE.search(sent):
                continue
            # 절 단위로 본다 — "붉은색이 부담스럽다면 분홍을 …"처럼 거른 선택지를 **전제로만**
            # 언급한 절
            # (양보·대체 표지 동반)은 재제시가 아니다.
            for clause in _CLAUSE_SPLIT_RE.split(sent):
                if _PIVOT_RE.search(clause):
                    continue
                if excl_tokens & content_tokens(clause, normalize=False):
                    hits.append(sent.strip()[:80])
                    break
        if hits:
            res.violations.append("excluded_reoffered")
            res.details["excluded_reoffered"] = hits[:3]
    eff = [m.group(0)[:80] for m in _EFFECT_ASSERT_RE.finditer(answer)]
    if eff:
        res.violations.append("effect_assertion")
        res.details["effect_assertion"] = eff[:3]
    return res
