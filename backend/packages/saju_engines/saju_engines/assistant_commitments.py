"""시스템 발언 원장 — 답변 속 추천·판정 문장의 추출·병합·검색·주입 (2026-10-01, 데굴님 승인).

배경(실로그 web-mup4m82l, 커튼 색): 2턴에서 "연두색이나 초록색 계열을 선택해 보세요"라고 말한
시스템이 4턴 "니가 … 추천해줬잖아"에 "… 드린 말씀이에요"로 자기 발언을 부인했다. 직전 답은 첫
문장(서두 반복 금지용)만 LLM에 전달돼 **자기가 무엇을 말했는지 알 길이 없었다**. docs/03의
`claim` 엔티티(시스템 답변 발)는 이벤트 요약만 담고 있었다.

설계 원칙:
  - 저장 대상은 **시스템 답변 문장 원문**이다. 옳다는 증거가 아니라 "말했다"는 증거다
    (user_facts 원장이 '사용자 명시 발화'만 담는 것과 대칭).
  - 추출은 rules-first: 추천·회피 수행 표지가 있는 문장만, 의문문·되물음 제외. LLM 미사용.
  - 검색은 어휘 중첩(사용자 발화의 내용어가 문장에 포함) — 색·방향·시기·사건 어느 주제든 같은
    방식으로 동작하며 주제별 사전이 없다.
  - 같은 대상어에 반대 극성의 새 발언이 오면 이전 건을 superseded 로 남긴다(삭제 금지) —
    "이전에 초록을 추천했으나 재검토 중"이라는 번복 이력이 답변 근거가 된다.
  - 순수 함수. 점수·판정·간지 불변(서술 근거 전용).
"""

from __future__ import annotations

import re

from saju_shared_types.conversation import AssistantCommitment

#: 저장 캡(스레드) — 오래된 active 부터 밀어내되 superseded 이력은 최근 것만 남긴다.
MAX_COMMITMENTS = 24
#: 답변 1건당 추출 캡.
MAX_PER_ANSWER = 8
_MAX_QUOTE = 160

# 추천(권장) 수행 표지 — 시스템이 '하라/고르라/두라'고 말한 문장.
_RECOMMEND_RE = re.compile(
    r"추천|권해|권합니다|권하고|선택해\s*보세요|골라\s*보세요|고르는\s*것|두세요|두어\s*보세요"
    r"|두는\s*것|배치하는\s*것|배치해\s*보세요|가까이\s*두|활용해\s*보세요|시도해\s*보세요"
    r"|가장\s*(?:좋|유리|적합)|이\s*좋아요|이\s*좋네요|가\s*좋아요|가\s*좋네요|좋은\s*선택"
    r"|어울려요|어울리|유리해요|유리한\s*(?:흐름|시기|선택)|적합해요|이로워요|이롭|도움이\s*돼요"
    r"|편이\s*(?:좋|낫|이롭|유리)|쪽이\s*(?:좋|낫|이롭|유리)|권장"
)
# 회피(비권장) 수행 표지 — '피하라/삼가라/줄이라/보다는'.
_AVOID_RE = re.compile(
    r"피하|피해\s*주세요|삼가|줄이|자제|않는\s*것이\s*좋|하지\s*마|않도록|말고|보다는"
    r"|무겁게\s*할\s*수|불리|부담이\s*될|좋지\s*않|맞지\s*않"
)
# 판정 표지 — 명리 판정 서술("용신은 화", "인성이 과다").
_JUDGMENT_RE = re.compile(r"용신|기신|희신|구신|한신|과다|부족|태과|신강|신약|격국|일주는")

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
_QUESTION_END_RE = re.compile(r"[?？]\s*$")
# 내용어 토큰 — 조사·어미를 떼어낸 2글자 이상 한글 덩어리. 일반어(stop)는 검색 근거에서 제외.
_TOKEN_RE = re.compile(r"[가-힣]{2,}")
_PARTICLE_RE = re.compile(
    r"(?:이나|이랑|으로|에서|에게|까지|부터|처럼|보다|이라|라서|인데|라고|계열|색깔|색상"
    r"|은|는|이|가|을|를|도|의|에|로|와|과|나|만|요|야|죠|고|며|서|면)$"
)
_STOP = frozenset({
    "사주", "공부", "학업", "운세", "기운", "지금", "오늘", "올해", "내년", "시기", "흐름", "경우",
    "정도", "사용", "추천", "질문", "말씀", "생각", "방법", "이번", "다음", "사람", "아들님",
    "그때", "그럼", "니가", "네가", "너가", "당신", "커튼", "커텐",
})


# 토큰 정규화기 — 동의어·범주 묶기(색 어휘 → 'COLOR:木' 등). 범주 토큰('XXX:…')은 서로 다른 표면형
# ('녹색'↔'초록색')을 같은 대상으로 보게 하며, 충돌(번복) 판정의 강한 근거가 된다. 다른 주제(방향·
# 음식)가 사전을 갖추면 같은 자리에 정규화기를 추가한다 — 추출·검색 규칙 자체는 주제 무관.
def _color_normalizer(token: str) -> str | None:
    from .yongsin_color import color_element_of  # 지연 import — 사전 로드 비용은 1회

    el = color_element_of(token)
    return f"COLOR:{el}" if el else None


_NORMALIZERS = (_color_normalizer,)


def _normalize(base: str) -> str:
    for fn in _NORMALIZERS:
        cat = fn(base)
        if cat:
            return cat
    return base


def content_tokens(text: str, *, normalize: bool = True) -> set[str]:
    """발화의 내용어 집합 — 조사 제거 후 2글자 이상, 일반어 제외. 검색·충돌 판정 공용.

    normalize=True 면 범주 정규화('녹색'·'초록색' → 'COLOR:木')를 적용한다. 사용자가 거른 **특정**
    선택지를 다시 내밀었는지 볼 때는 False(표면형 그대로) — 붉은색을 거른 사용자에게 분홍을 제안한
    것은 재제시가 아니다.
    """
    out: set[str] = set()
    for tok in _TOKEN_RE.findall(text):
        base = _PARTICLE_RE.sub("", tok)
        base = _PARTICLE_RE.sub("", base)  # '초록색계열' → '초록색' → '초록'
        if len(base) >= 2 and base not in _STOP:
            out.add(_normalize(base) if normalize else base)
    return out


def _conflicts(a: set[str], b: set[str]) -> bool:
    """번복 판정 근거 — 범주 토큰('COLOR:木')이 1개라도 겹치거나, 일반 내용어가 2개 이상 겹칠 때."""
    common = a & b
    if any(":" in t for t in common):
        return True
    return len(common) >= 2


def _polarity(sentence: str) -> str | None:
    """문장의 수행 극성 — avoid 가 recommend 보다 우선(같은 문장에 '…보다는 ○이 좋아요')."""
    if _AVOID_RE.search(sentence):
        return "avoid"
    if _RECOMMEND_RE.search(sentence):
        return "recommend"
    if _JUDGMENT_RE.search(sentence):
        return "judgment"
    return None


def extract_commitments(
    answer: str, turn: int, topic: str | None = None
) -> list[AssistantCommitment]:
    """답변 본문에서 추천·회피·판정 문장을 뽑는다(의문문·되물음 제외, 캡 적용).

    Args:
        answer: 시스템 답변 원문.
        turn: 답변이 나온 턴 번호.
        topic: 당시 활성 도메인(Domain value) — 없으면 None.
    """
    if not answer:
        return []
    out: list[AssistantCommitment] = []
    for raw in _SENT_SPLIT_RE.split(answer.strip()):
        sent = raw.strip()
        if len(sent) < 12 or _QUESTION_END_RE.search(sent):
            continue
        pol = _polarity(sent)
        if pol is None:
            continue
        out.append(AssistantCommitment(
            quote=sent[:_MAX_QUOTE], source_turn=turn, polarity=pol, topic=topic,
        ))
        if len(out) >= MAX_PER_ANSWER:
            break
    return out


def merge_commitments(
    existing: list[AssistantCommitment], new: list[AssistantCommitment]
) -> list[AssistantCommitment]:
    """원장 병합 — 반대 극성 충돌이면 이전 건을 superseded 로 표시하고, 캡을 넘으면 오래된 것부터
    제거한다.

    충돌 판정: 새 문장(recommend/avoid)과 기존 active 문장의 내용어가 1개 이상 겹치고 극성이
    반대이면 기존 건은 `superseded`(삭제 아님 — 번복 이력 보존). 판정(judgment) 문장은 충돌
    판정에 참여하지 않는다.
    """
    kept = list(existing)
    for nf in new:
        if any(k.quote == nf.quote for k in kept):
            continue
        if nf.polarity in ("recommend", "avoid"):
            toks = content_tokens(nf.quote)
            for i, old in enumerate(kept):
                if (
                    old.status == "active"
                    and old.polarity in ("recommend", "avoid")
                    and old.polarity != nf.polarity
                    and _conflicts(toks, content_tokens(old.quote))
                ):
                    kept[i] = old.model_copy(
                        update={"status": "superseded", "superseded_by_turn": nf.source_turn}
                    )
        kept.append(nf)
    if len(kept) > MAX_COMMITMENTS:
        kept = kept[-MAX_COMMITMENTS:]
    return kept


def match_commitments(
    commitments: list[AssistantCommitment], text: str, limit: int = 5
) -> list[AssistantCommitment]:
    """사용자 발화와 내용어가 겹치는 원장 문장 — 겹침 수 내림차순, 같은 수면 최근 턴 우선."""
    toks = content_tokens(text)
    if not toks or not commitments:
        return []
    scored: list[tuple[int, int, AssistantCommitment]] = []
    for c in commitments:
        overlap = len(toks & content_tokens(c.quote))
        if overlap:
            scored.append((overlap, c.source_turn, c))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [c for _, _, c in scored[:limit]]


def mentions_commitment(commitments: list[AssistantCommitment], text: str) -> bool:
    """발화가 시스템이 추천·회피한 대상어를 언급하는가(선택지 확인 후속 링크용).

    판정(judgment) 문장은 제외한다.
    """
    toks = content_tokens(text)
    if not toks:
        return False
    for c in commitments:
        if c.polarity in ("recommend", "avoid") and toks & content_tokens(c.quote):
            return True
    return False


_POL_KO = {"recommend": "추천", "avoid": "비권장", "judgment": "판정"}


def prior_statement_lines(matched: list[AssistantCommitment]) -> list[str]:
    """LLM 입력용 줄 — '(T2 추천·유효) “…”' / 번복된 건은 '(…→T3에서 반대 발언으로 대체됨)'."""
    lines: list[str] = []
    for c in matched:
        status = (
            "유효" if c.status == "active"
            else f"T{c.superseded_by_turn}에서 반대 발언으로 대체됨"
        )
        pol = _POL_KO.get(c.polarity, c.polarity)
        lines.append(f"- (T{c.source_turn} {pol}·{status}) “{c.quote}”")
    return lines


PRIOR_STATEMENTS_HEADER = (
    "[이전 발언 원문 — 이 스레드에서 네가 실제로 한 말 중 사용자 발화와 관련된 문장. 사용자가 "
    "'네가 추천했잖아/그렇게 말했잖아'라고 하면 아래 원문으로 사실 여부를 먼저 확인하고 답할 것. "
    "원문에 있는 발언을 부인하거나 '그런 뜻이었다'로 바꿔 말하지 말고, 원문에 없는 발언은 "
    "부드럽게 '그 말씀은 드리지 않았다'고 밝힐 것. 이 원문은 네가 말했다는 증거일 뿐 그 내용이 "
    "옳다는 근거는 아니다 — 옳고 그름은 엔진 자료([원국·명식 구조]·용희기구한·후보)로 다시 판단할 "
    "것]"
)
