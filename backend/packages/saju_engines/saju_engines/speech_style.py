"""해요체 사전 문장 → 페르소나 말투(합쇼체·하게체·반말체) 결정론 변환 (docs/17 §26-3, 2026-11-08).

채팅 답변에 **코드가 직접 삽입·교체**하는 문장(단식 참고 문단)은 LLM 을 거치지 않으므로 설정 말투가
적용되지 않았다(데굴님 실답: 합쇼체 답 한가운데 해요체 문단). 이 모듈은 종결어미만 바꾼다 —
내용·어휘·숫자는 그대로다(페르소나 = 문체 전용, CLAUDE.md 원칙 12). 지난 기간 질문용 과거형
변환(`to_past`, 2026-11-10)도 같은 원칙 — 문장 끝만 바꾸고 권유 문장은 뺀다.

대상은 우리 사전 문장(단식·이번 달 층·조언)이라 종결 형태가 한정돼 있다. 규칙은 한글 자모 분해로
일반화하되, 불규칙(ㅂ·르·으 탈락)은 표로 둔다. 커버리지는 `test_speech_style_20261108` 가 사전 전
문장 × 3말투로 잔여 해요체 어미가 없음을 강제한다.
"""

from __future__ import annotations

import re

#: 지원 말투(페르소나 SpeechStyle 과 같은 키). 해요체는 변환 없음.
STYLES: tuple[str, ...] = ("haeyo", "hapsyo", "hagae", "banmal_chae")

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_TAIL_RE = re.compile(r"^(?P<body>.*?)(?P<punct>[.!?]*)(?P<paren>\)?)$", re.S)

# 자모 인덱스(유니코드 한글 음절 = 0xAC00 + (초성*21 + 중성)*28 + 종성).
_JUNG_A, _JUNG_AE, _JUNG_EO, _JUNG_E, _JUNG_YEO = 0, 1, 4, 5, 6
_JUNG_O, _JUNG_WA, _JUNG_WAE, _JUNG_OE = 8, 9, 10, 11
_JUNG_U, _JUNG_WO, _JUNG_EU, _JUNG_I = 13, 14, 18, 20
_JONG_NONE, _JONG_L, _JONG_B = 0, 8, 17

#: 축약 모음 → 어간 본래 모음(해요체 '어요' 축약 복원): 쳐←치, 와←오, 여←이 …
_UNCONTRACT: dict[int, int] = {_JUNG_YEO: _JUNG_I, _JUNG_WA: _JUNG_O, _JUNG_WO: _JUNG_U}

#: 불규칙·고빈도 특수형 — (해요체 접미) → (합쇼체, 반말체, 하게체). 접미 일치(긴 것 우선).
_IRREGULAR: tuple[tuple[str, tuple[str, str, str]], ...] = (
    ("거예요", ("겁니다", "거야", "걸세")),
    ("쉬워요", ("쉽습니다", "쉬워", "쉽네")),
    ("려워요", ("렵습니다", "려워", "렵네")),
    ("빨라요", ("빠릅니다", "빨라", "빠르네")),
    ("몰라요", ("모릅니다", "몰라", "모르네")),
    ("달라요", ("다릅니다", "달라", "다르네")),
    ("커요", ("큽니다", "커", "크네")),
    ("돼요", ("됩니다", "돼", "되네")),
    ("해요", ("합니다", "해", "하네")),
)
_STYLE_COL = {"hapsyo": 0, "banmal_chae": 1, "hagae": 2}


def _decompose(ch: str) -> tuple[int, int, int] | None:
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return None


def _compose(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + (cho * 21 + jung) * 28 + jong)


def _imperative(stem: str, style: str, prev: str) -> tuple[str, str]:
    """'~세요' 권유형 → (앞 단어 치환, 새 단어). '하지 마세요' 는 '하지 않는 …' 으로."""
    if stem == "마" and prev.endswith("지"):
        base = "않는"
        new_prev = prev
    else:
        s = stem[:-1] if stem.endswith("으") else stem
        base = f"{s}는"
        new_prev = prev
    tail = {"hapsyo": " 것이 좋습니다", "banmal_chae": " 게 좋아", "hagae": " 게 좋겠네"}[style]
    return new_prev, base + tail


def _generic(word: str, style: str) -> str | None:
    """'~어요/~아요/축약형' 서술형 종결 변환. 처리 불가면 None."""
    if len(word) < 2 or not word.endswith("요"):
        return None
    col = _STYLE_COL[style]
    if word.endswith("이에요"):
        stem = word[:-3]
        return (stem + "입니다", stem + "이야", stem + "일세")[col]
    if word.endswith("예요"):
        stem = word[:-2]
        return (stem + "입니다", stem + "야", stem + "일세")[col]
    for suffix, forms in _IRREGULAR:
        if word.endswith(suffix):
            return word[: -len(suffix)] + forms[col]
    # 비축약 '어요/아요': 어간 끝 음절에 받침이 있다.
    if word[-2] in ("어", "아") and len(word) >= 3:
        stem = word[:-2]
        d = _decompose(stem[-1])
        if d is None:
            return None
        cho, jung, jong = d
        if style == "banmal_chae":
            return word[:-1]
        if jong == _JONG_L:  # ㄹ 탈락: 늘어요→늡니다/느네
            base = stem[:-1] + _compose(cho, jung, _JONG_NONE)
            if style == "hapsyo":
                return base[:-1] + _compose(cho, jung, _JONG_B) + "니다"
            return base + "네"
        if jong == _JONG_NONE:  # 어간이 모음으로 끝나는데 비축약(드물다) — 받침 ㅂ 결합
            if style == "hapsyo":
                return stem[:-1] + _compose(cho, jung, _JONG_B) + "니다"
            return stem + "네"
        return stem + ("습니다" if style == "hapsyo" else "네")
    # 축약형: 마지막 음절(요 앞)에 어미가 녹아 있다 — 쳐요/와요/내요/서요/가요/나요/새요.
    syl = word[-2]
    d = _decompose(syl)
    if d is None:
        return None
    cho, jung, jong = d
    if jong != _JONG_NONE:
        return None
    if style == "banmal_chae":
        return word[:-1]
    base_jung = _UNCONTRACT.get(jung, jung)
    if style == "hapsyo":
        return word[:-2] + _compose(cho, base_jung, _JONG_B) + "니다"
    return word[:-2] + _compose(cho, base_jung, _JONG_NONE) + "네"


def restyle_sentence(sentence: str, style: str) -> str:
    """문장 하나의 종결어미를 말투에 맞게 바꾼다. 해요체·미지원 말투·변환 불가면 원문."""
    if style not in STYLES or style == "haeyo" or not sentence.strip():
        return sentence
    m = _TAIL_RE.match(sentence.rstrip())
    assert m is not None
    body, punct, paren = m.group("body"), m.group("punct"), m.group("paren")
    words = body.split(" ")
    last = words[-1]
    prev = words[-2] if len(words) >= 2 else ""
    if last.endswith("세요") and not last.endswith("이세요"):
        new_prev, new_last = _imperative(last[:-2], style, prev)
        if len(words) >= 2:
            words[-2] = new_prev
        words[-1] = new_last
    else:
        converted = _generic(last, style)
        if converted is None:
            return sentence
        words[-1] = converted
    return " ".join(words) + punct + paren


def restyle(text: str, style: str) -> str:
    """문단(여러 문장)의 종결어미를 말투에 맞게 바꾼다. 문장 사이 공백은 한 칸으로 정규화."""
    if style not in STYLES or style == "haeyo" or not text.strip():
        return text
    parts = [p for p in _SENT_SPLIT_RE.split(text.strip()) if p]
    return " ".join(restyle_sentence(p, style) for p in parts)


_JONG_SS = 20  # 받침 ㅆ — 과거 선어말어미 '-았/었-'
#: 과거형 특수 치환(문장 끝 일치, 긴 것 우선) — 일반 규칙('~ㅆ을 수 있어요')이 어색해지는 꼴.
_PAST_SPECIAL: tuple[tuple[str, str], ...] = (
    ("나타나기도 해요", "나타났을 수 있어요"),  # '~기도 했을 수 있어요' 이중 완곡 회피
    ("수 있어요", "수 있었어요"),  # '~ㄹ 수 있었을 수 있어요' 회피
)


def past_sentence(sentence: str) -> str | None:
    """해요체 **현재** 서술 문장 하나를 과거형으로 바꾼다(지난 기간 질문의 단식 문단용, 2026-11-10).

    - 서술격('~이에요/~예요' — 간지·구조 사실): '~이었어요/~였어요'(사실이라 추정형으로 흐리지
      않는다).
    - 그 밖의 서술('~어요/~아요/축약형'): 끝 음절에 ㅆ + '을 수 있어요' — 과거 추정형
      (움직여요→움직였을 수 있어요, 쉬워요→쉬웠을 수 있어요). 단식 문장은 그 십성의 일반 장면이라
      지난 일을 단정하지 않는다(회고 모드 지시 `_RETRO_TENSE_DIRECTIVE` 와 같은 꼴).
    - 권유('~세요')·종결어미 없는 조언('서류는 꼼꼼히.')은 None — 지난 기간에는 싣지 않는다.

    내용·어휘·숫자는 그대로다(문체 전용). 문장 가운데 연결어미('~지만', '~면')는 손대지 않는다.
    """
    if not sentence.strip():
        return None
    m = _TAIL_RE.match(sentence.rstrip())
    assert m is not None
    body, punct, paren = m.group("body"), m.group("punct"), m.group("paren")
    for suffix, repl in _PAST_SPECIAL:
        if body.endswith(suffix):
            return body[: -len(suffix)] + repl + punct + paren
    words = body.split(" ")
    last = words[-1]
    if last.endswith("세요") or not last.endswith("요") or len(last) < 2:
        return None
    if last.endswith("이에요"):
        words[-1] = last[:-3] + "이었어요"
    elif last.endswith("예요"):
        words[-1] = last[:-2] + "였어요"
    else:
        d = _decompose(last[-2])
        if d is None or d[2] != _JONG_NONE:
            return None
        cho, jung, _ = d
        words[-1] = last[:-2] + _compose(cho, jung, _JONG_SS) + "을 수 있어요"
    return " ".join(words) + punct + paren


def to_past(text: str) -> str:
    """문단(여러 문장)을 과거형으로 — 바꿀 수 없는 문장(권유·조언)은 뺀다. `past_sentence` 참조."""
    if not text.strip():
        return text
    parts = [p for p in _SENT_SPLIT_RE.split(text.strip()) if p]
    return " ".join(s for s in (past_sentence(p) for p in parts) if s)


_HAEYO_RESIDUE_RE = re.compile(r"(?:요|세요)[.!?]?\)?$")


def has_haeyo_ending(sentence: str) -> bool:
    """문장이 해요체 어미로 끝나는가(커버리지 검사용)."""
    return bool(_HAEYO_RESIDUE_RE.search(sentence.strip()))
