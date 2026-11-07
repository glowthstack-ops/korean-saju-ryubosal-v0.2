"""리포트 본문 문체·시제·단위 감사(2026-11-07 데굴님 "제안대로 진행 + 문체 통일").

재호출 없는 결정론 교정.

세 가지를 생성 직후 섹션 단위로 적용한다(간지·숫자는 건드리지 않는다).

1. **해요체 통일**(`unify_haeyo`): 페르소나 기본 말투(해요체)인데 본문이 하다체("~한다.")·합쇼체
   ("~습니다.")와 섞여 나오던 결함 — 입력 자료(사전 문장·지시문)가 하다체라 LLM이 그대로 베낀다.
   안전한 활용만 바꾼다: 과거(ㅆ 받침)+다 → 어요 / 한다·된다·이다·있다·없다·않는다 / 받침 어간+
   는다·다(모음조화) / 자주 쓰는 모음 어간 whitelist(간다·본다·준다 …) / 합쇼체(습니다·ㅂ니다).
   ㅂ·ㅅ·ㄷ·ㅎ 불규칙 가능 어간·르 어간·ㄹ 탈락 가능성이 있는 ㄴ다 형은 **바꾸지 않고 로그만**
   (`unresolved`) — 틀린 활용을 만드는 것보다 혼용 한 문장이 낫다.
2. **과거 대운 회고 어미**(`hedge_retrospective`): 지난 대운 페이지의 "~있었네요/~힘들었어요/~였다"
   같은 과거 사실 단정을 "~있었을 수 있어요"로 바꿔 적중 확인 유도형으로 만든다. 이미 가능성·
   확인형("수 있", "가능성", "보여요", "듯해요", "것 같아요", "셨죠", 물음표)은 건드리지 않는다.
3. **월 단위 제거**(`strip_month_detail`): 대운별 페이지 입력은 연 단위뿐인데 "2027년 1월"처럼
   달을 지어내면 "2027년"으로 줄인다(연도는 입력값). 연도 없는 "8월에"는 로그만.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HANGUL_BASE = 0xAC00
_JUNG_A, _JUNG_EO, _JUNG_E, _JUNG_AE = 0, 4, 5, 1
_JUNG_O, _JUNG_U, _JUNG_EU, _JUNG_I, _JUNG_OE, _JUNG_YEO = 8, 13, 18, 20, 11, 6
_JONG_NONE, _JONG_N, _JONG_D, _JONG_B, _JONG_S, _JONG_SS = 0, 4, 7, 17, 19, 20
#: 받침 어간 + 다/는다/습니다 에서 규칙 활용으로 바꾸지 않는 받침(불규칙 가능 — ㅂ·ㅅ·ㄷ).
_SKIP_JONG = {_JONG_B, _JONG_S, _JONG_D, _JONG_N}
#: ㅂ 받침이지만 규칙 활용이 확실한 어간 끝 음절(잡아요·입어요 …) — 그 외 ㅂ은 미교정.
_B_REGULAR = frozenset("잡입접좁뽑씹")
#: ㅎ 불규칙(그렇다→그래요) 어간 끝 음절 — 그 외 ㅎ 받침(좋다·넣다·놓다·쌓다)은 규칙 활용.
_H_IRREGULAR = frozenset("렇랗얗멓맣떻")
#: 모음 어간 ㄴ다/다 형 whitelist(끝 음절 → 해요체 끝 음절).
#: ㄴ다 형에서 ㄹ 탈락 어간일 수 있는 끝 음절(산다=살다/사다, 안다=알다, 논다=놀다 …)은
#: `_N_DA_AMBIGUOUS` 로 따로 막는다 — 틀린 활용보다 미교정이 낫다.
_VOWEL_STEM_MAP: dict[str, str] = {
    "가": "가요", "오": "와요", "보": "봐요", "주": "줘요", "내": "내요", "쓰": "써요",
    "지": "져요", "치": "쳐요", "켜": "켜요", "되": "돼요", "하": "해요", "나": "나요",
    "자": "자요", "타": "타요", "서": "서요", "끼": "껴요", "크": "커요", "세": "세요",
    "펴": "펴요", "사": "사요", "두": "둬요", "배": "배요", "매": "매요", "건너": "건너요",
    "모으": "모아요", "기다리": "기다려요",
}


_N_DA_AMBIGUOUS = frozenset("사아노드우푸여파거머미부떠마무러비시")


def _decompose(ch: str) -> tuple[int, int, int] | None:
    code = ord(ch) - _HANGUL_BASE
    if not 0 <= code < 11172:
        return None
    return code // 588, (code % 588) // 28, code % 28


def _compose(cho: int, jung: int, jong: int) -> str:
    return chr(_HANGUL_BASE + cho * 588 + jung * 28 + jong)


def _has_batchim(ch: str) -> bool:
    d = _decompose(ch)
    return d is not None and d[2] != _JONG_NONE


def _harmony_suffix(stem_last: str) -> str | None:
    """받침 어간 끝 음절의 모음조화 어미('아요'/'어요') — 불규칙 가능 받침은 None."""
    d = _decompose(stem_last)
    if d is None or d[2] == _JONG_NONE:
        return None
    if (d[2] in _SKIP_JONG and stem_last not in _B_REGULAR) or stem_last in _H_IRREGULAR:
        return None
    return "아요" if d[1] in (_JUNG_A, _JUNG_O) else "어요"


def _vowel_stem_to_haeyo(stem: str) -> str | None:
    """모음 어간(받침 없음) → 해요체. whitelist 우선, 그 외 모음별 규칙(르 어간 제외)."""
    if not stem:
        return None
    for n in (3, 2, 1):
        key = stem[-n:]
        if key in _VOWEL_STEM_MAP:
            return stem[:-n] + _VOWEL_STEM_MAP[key]
    last = stem[-1]
    d = _decompose(last)
    if d is None or d[2] != _JONG_NONE or last == "르":
        return None
    cho, jung, _ = d
    if jung in (_JUNG_A, _JUNG_EO, _JUNG_E, _JUNG_AE, _JUNG_YEO):
        return stem + "요"
    if jung == _JUNG_O:
        return stem[:-1] + _compose(cho, 9, 0) + "요"  # ㅗ → ㅘ
    if jung == _JUNG_U:
        return stem[:-1] + _compose(cho, 14, 0) + "요"  # ㅜ → ㅝ
    if jung == _JUNG_I:
        return stem[:-1] + _compose(cho, _JUNG_YEO, 0) + "요"  # ㅣ → ㅕ
    if jung == _JUNG_OE:
        return stem[:-1] + _compose(cho, 10, 0) + "요"  # ㅚ → ㅙ
    if jung == _JUNG_EU:
        return stem[:-1] + _compose(cho, _JUNG_EO, 0) + "요"  # ㅡ 탈락 → ㅓ
    return None


def _ida_to_haeyo(prefix: str) -> str:
    """'X이다' → 'X이에요'(받침) / 'X예요'(모음)."""
    if prefix and _has_batchim(prefix[-1]):
        return prefix + "이에요"
    return prefix + "예요"


def _convert_word(word: str) -> str | None:
    """문장 끝 낱말 하나를 해요체로. 바꿀 수 없으면 None(로그 대상)."""
    # ── 합쇼체 ──
    if word.endswith("십시오"):
        return word[:-3] + "세요"  # 보십시오 → 보세요
    if word.endswith("입니다"):
        return _ida_to_haeyo(word[:-3])
    if word.endswith("습니다"):
        stem = word[:-3]
        suf = _harmony_suffix(stem[-1]) if stem else None
        return stem + suf if suf else None
    if word.endswith("니다"):
        head = word[:-2]  # '합' 같은 ㅂ 받침 음절
        if head:
            d = _decompose(head[-1])
            if d is not None and d[2] == _JONG_B:
                base = head[:-1] + _compose(d[0], d[1], 0)
                return _vowel_stem_to_haeyo(base)
        return None
    if not word.endswith("다"):
        return None
    stem = word[:-1]
    if not stem:
        return None
    last = stem[-1]
    d = _decompose(last)
    if d is None:
        return None
    # ── 과거·추측(ㅆ 받침: 았/었/였/했/됐/겠/셨 …) → 어요 ──
    if d[2] == _JONG_SS:
        return stem + "어요"
    # ── 고빈도 고정형 ──
    for tail, rep in (
        ("않는다", "않아요"), ("않다", "않아요"), ("한다", "해요"), ("된다", "돼요"),
        ("있다", "있어요"), ("없다", "없어요"), ("하다", "해요"), ("되다", "돼요"),
        ("싶다", "싶어요"), ("같다", "같아요"), ("좋다", "좋아요"), ("많다", "많아요"),
        ("크다", "커요"), ("작다", "작아요"), ("높다", "높아요"), ("낮다", "낮아요"),
    ):
        if word.endswith(tail):
            return word[: -len(tail)] + rep
    if word.endswith("이다"):
        return _ida_to_haeyo(word[:-2])
    # ── 받침 어간 + 는다 ──
    if word.endswith("는다"):
        base = word[:-2]
        suf = _harmony_suffix(base[-1]) if base else None
        return base + suf if suf else None
    # ── 모음 어간 + ㄴ다(간다·본다 …) — whitelist·규칙 ──
    if d[2] == _JONG_N:
        base = stem[:-1] + _compose(d[0], d[1], 0)
        key = base[-1]
        if key in _N_DA_AMBIGUOUS:
            return None  # ㄹ 탈락 가능(산다·안다·논다) — 로그만
        kd = _decompose(key)
        if key in _VOWEL_STEM_MAP or key in ("되", "하") or (
            kd is not None and kd[1] in (_JUNG_I, _JUNG_YEO, _JUNG_OE)
        ):
            return _vowel_stem_to_haeyo(base)  # 열린다→열려요, 생긴다→생겨요, 된다→돼요
        return None
    # ── 받침 어간 + 다(좋다·작다 …) ──
    if d[2] != _JONG_NONE:
        suf = _harmony_suffix(last)
        return stem + suf if suf else None
    # ── 모음 어간 + 다(크다·가다 …) ──
    return _vowel_stem_to_haeyo(stem)


#: 문장 끝 낱말(한글) + 종결부호. 괄호·따옴표 안이나 '~다는/~다고'(비종결)는 걸리지 않는다.
_SENTENCE_END_RE = re.compile(r"([가-힣]+)(?=[.!?](?:\s|$))")


@dataclass
class StyleAuditResult:
    """문체 통일 결과 — 본문·교정 목록·미해결 어미(로그 전용)."""

    text: str
    fixes: list[tuple[str, str]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def unify_haeyo(text: str) -> StyleAuditResult:
    """하다체·합쇼체 종결을 해요체로(안전한 활용만). 간지·숫자·비종결 어미는 불변."""
    fixes: list[tuple[str, str]] = []
    unresolved: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        word = m.group(1)
        if word.endswith(("요", "죠", "네", "게", "세", "까")):
            return word  # 해요체(요·죠)·하게체·물음은 그대로(하게체는 페르소나 검사 영역)
        if not word.endswith(("다", "니다", "십시오")):
            return word
        conv = _convert_word(word)
        if conv is None:
            unresolved.append(word)
            return word
        fixes.append((word, conv))
        return conv

    out = _SENTENCE_END_RE.sub(_sub, text)
    return StyleAuditResult(text=out, fixes=fixes, unresolved=unresolved)


# ── 과거 대운 회고 어미 ──────────────────────────────────────────────────────

#: ㅆ 받침이지만 과거가 아닌 어간 끝 음절 — 있(현재)·겠(추측).
_NOT_PAST_SS = frozenset("있겠")
_HEDGED_MARKERS = (
    "수 있", "가능성", "보여요", "듯해요", "것 같아요", "셨죠", "셨나요", "셨는지", "?",
)
#: 과거 사실 단정 종결 — 'ㅆ 받침 음절(았/었/였/했/렸 …) + (어요|네요|다)'. ㅆ 받침 판정은 코드.
_PAST_END_RE = re.compile(r"([가-힣]+)(어요|네요|다)(?=[.!](?:\s|$))")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def hedge_retrospective(text: str) -> tuple[str, list[tuple[str, str]]]:
    """지난 대운 페이지의 과거 사실 단정 종결을 '~을 수 있어요'로(적중 확인 유도형).

    문단(줄) 구조를 보존하고 문장 단위로 판정한다 — 이미 가능성·확인형 표지가 있는 문장은 불변.
    """
    fixes: list[tuple[str, str]] = []

    def _sub(m: re.Match[str]) -> str:
        last = m.group(1)[-1]
        d = _decompose(last)
        if d is None or d[2] != _JONG_SS or last in _NOT_PAST_SS:
            return m.group(0)  # 과거(ㅆ 받침)가 아니면 불변 — '있어요'(현재)·'겠어요'(추측) 제외
        new = m.group(1) + "을 수 있어요"
        fixes.append((m.group(0), new))
        return new

    out_lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        sentences = _SENTENCE_SPLIT_RE.split(line)
        fixed = [
            sent if any(mk in sent for mk in _HEDGED_MARKERS) else _PAST_END_RE.sub(_sub, sent)
            for sent in sentences
        ]
        out_lines.append(" ".join(fixed))
    return "\n".join(out_lines), fixes


# ── 월 단위 제거 ─────────────────────────────────────────────────────────────

_YEAR_MONTH_RE = re.compile(r"(\d{4})년\s*(1[0-2]|[1-9])월")
_BARE_MONTH_RE = re.compile(r"(?<![\d년])\b(1[0-2]|[1-9])월(?=[에은는의부터까지까지쯤경]|\s)")


def strip_month_detail(text: str) -> tuple[str, list[str], list[str]]:
    """'YYYY년 M월' → 'YYYY년'(연 단위 입력만 받은 페이지). 연도 없는 'M월'은 로그만.

    Returns:
        (교정 본문, 제거한 '년 월' 표기 목록, 연도 없는 달 표기 목록).
    """
    stripped: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        stripped.append(m.group(0))
        return f"{m.group(1)}년"

    out = _YEAR_MONTH_RE.sub(_sub, text)
    bare = [m.group(0) for m in _BARE_MONTH_RE.finditer(out)]
    return out, stripped, bare
