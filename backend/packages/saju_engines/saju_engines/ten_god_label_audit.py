"""원국 자리 십성 표기 감사 — 생성 후 결정론 교정 (2026-10-13 데굴님 지시).

사고: 프롬프트에 '월주 丙子 · 지지 편관'으로 정확히 실렸는데 답변이 "월지에 자리한 정관의 기운"으로
썼다. 원국의 특정 자리에 붙인 십성 설명을 엔진값과 대조해 **명확한 불일치만** 고친다.

범위를 일부러 좁게 둔다(오탐이 정상 답을 망가뜨리는 것을 더 경계한다):
- 대상: 원국 지지 자리어(연지·년지·월지·일지·시지) 바로 뒤의 십성(비견…정인) 또는 십성군
  (비겁·식상·재성·관성·인성). 자리어와 십성 사이에는 간지 글자(+한글 병기)와 짧은 연결어
  ('에 자리한'·'의' 등)만 허용.
- 천간 자리어(연간·월간)는 제외한다 — '연간 계획'·'월간 수입'처럼 일상어와 겹친다.
- 건너뜀: 자리어가 나열된 문장('월지와 시지에 자리한 편관과 편인'), 십성이 나열된 경우, 적힌 간지
  글자가 그 자리의 원국 글자와 다를 때(운 기둥일 수 있음), 바로 앞에 운 표현(대운·세운·월운·일운·
  일진)이 있을 때, 시주 미상으로 엔진값이 없을 때.
- 교정: LLM 재호출 없이 그 십성 단어만 엔진값으로 바꾼다(십성군으로 썼으면 십성군으로). 바로 뒤에
  붙은 조사는 새 단어의 받침에 맞춘다('정재라서' → '식신이라서').
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from saju_shared_types.llm_input import PillarDetail
from saju_shared_types.pillars import FourPillarsResult

_SLOT_BY_WORD: dict[str, str] = {
    "연지": "year", "년지": "year", "월지": "month", "일지": "day", "시지": "hour",
}
_TEN_GODS = ("비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인")
_GROUP_MEMBERS: dict[str, frozenset[str]] = {
    "비겁": frozenset({"비견", "겁재"}), "식상": frozenset({"식신", "상관"}),
    "재성": frozenset({"편재", "정재"}), "관성": frozenset({"편관", "정관"}),
    "인성": frozenset({"편인", "정인"}),
}
_GROUP_OF: dict[str, str] = {tg: g for g, ms in _GROUP_MEMBERS.items() for tg in ms}
_TG_ALT = "|".join(_TEN_GODS + tuple(_GROUP_MEMBERS))
_GANJI_CHARS = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"

_PATTERN = re.compile(
    r"(?P<pos>연지|년지|월지|일지|시지)"
    rf"(?:\s*(?P<glyph>[{_GANJI_CHARS}])(?:\s*\([가-힣]{{1,3}}\))?)?"
    # '에 든'은 지장간 서술('일지 亥에 든 정인(甲)')이라 자리 본기 표기로 보지 않는다
    # (2026-10-14 검수).
    r"\s*(?:에\s*(?:자리한|자리 잡은|자리잡은|있는|놓인|앉은|위치한)|의|인|은|는|=)?\s*"
    rf"(?P<tg>{_TG_ALT})"
)
_COORD_BEFORE = re.compile(r"(?:연지|년지|월지|일지|시지)\s*(?:와|과|·|,|및)\s*$")
_LUCK_BEFORE = re.compile(r"(?:대운|세운|월운|일운|일진)(?:의|에서|에)?\s*$")
_COORD_AFTER = re.compile(rf"^\s*(?:과|와|·|,|및)\s*(?:{_TG_ALT})")


#: 받침 유무로 갈리는 조사 쌍(받침 있음, 받침 없음) — 긴 것부터 대조한다.
#: 서술격 조사 '이-'(이죠·이지만·이네요·이면·이다·이든·이야·이란)는 주격 '이/가'보다 먼저 대조한다
#: — 2026-10-14 검수: '식신이죠'→'정재가죠' 비문. 받침 없는 단어 뒤에선 '이'가 탈락한다.
_JOSA_PAIRS: tuple[tuple[str, str], ...] = (
    ("이에요", "예요"), ("이었", "였"), ("이라", "라"), ("이고", "고"), ("이며", "며"),
    ("이죠", "죠"), ("이지", "지"), ("이네", "네"), ("이면", "면"), ("이다", "다"),
    ("이든", "든"), ("이야", "야"), ("이란", "란"),
    ("으로", "로"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"),
)


def _has_batchim(word: str) -> bool:
    """마지막 음절에 받침이 있는가(ㄹ 받침도 받침으로 본다 — '으로/로'는 십성 단어에 ㄹ 없음)."""
    code = ord(word[-1]) - 0xAC00
    return 0 <= code < 11172 and code % 28 != 0


def _fix_josa(tail: str, corrected: str) -> str:
    """교체한 단어 바로 뒤에 붙은 조사를 새 단어의 받침에 맞춘다(띄어 쓴 경우는 손대지 않는다)."""
    batchim = _has_batchim(corrected)
    for with_b, without_b in _JOSA_PAIRS:
        for current in (with_b, without_b):
            if tail.startswith(current):
                want = with_b if batchim else without_b
                return want + tail[len(current):]
    return tail


@dataclass(frozen=True)
class TenGodLabelFix:
    """교정 1건 — 어느 자리의 어떤 표기를 무엇으로 바꿨는가."""

    position: str
    written: str
    corrected: str
    excerpt: str


#: 자리(slot) → (지지 본기 십성, 지지 글자).
BranchFacts = dict[str, tuple[str, str]]


def facts_from_pillar_details(details: list[PillarDetail]) -> BranchFacts:
    """LLM 입력의 기둥 상세(엔진 확정값)에서 지지 자리별 십성·글자를 뽑는다."""
    return {
        d.palace: (d.branch_ten_god, d.ganji[1])
        for d in details
        if d.palace in ("year", "month", "day", "hour") and len(d.ganji) == 2
    }


def facts_from_pillars(pillars: FourPillarsResult) -> BranchFacts:
    """만세 결과 기둥에서 지지 자리별 십성·글자를 뽑는다(시주 미상이면 시지 없음)."""
    out: BranchFacts = {}
    for slot in ("year", "month", "day", "hour"):
        p = getattr(pillars, slot)
        if p is not None:
            out[slot] = (p.branch_main_ten_god, p.branch)
    return out


def audit_ten_god_labels(text: str, facts: BranchFacts) -> tuple[str, list[TenGodLabelFix]]:
    """원국 지지 자리에 붙인 십성 표기를 엔진값과 대조해 명확한 불일치만 고친다.

    Args:
        text: 답변 원문.
        facts: 자리별 (지지 본기 십성, 지지 글자) — 엔진 확정값.

    Returns:
        (교정된 텍스트, 교정 목록). 불일치가 없으면 원문 그대로.
    """
    fixes: list[TenGodLabelFix] = []
    out: list[str] = []
    cursor = 0
    for m in _PATTERN.finditer(text):
        slot = _SLOT_BY_WORD[m.group("pos")]
        fact = facts.get(slot)
        if fact is None:
            continue
        engine_tg, engine_glyph = fact
        before = text[max(0, m.start() - 8): m.start()]
        if _COORD_BEFORE.search(before) or _LUCK_BEFORE.search(before):
            continue
        if _COORD_AFTER.match(text[m.end(): m.end() + 8]):
            continue
        glyph = m.group("glyph")
        if glyph is not None and glyph != engine_glyph:
            continue
        written = m.group("tg")
        if written in _GROUP_MEMBERS:
            if engine_tg in _GROUP_MEMBERS[written]:
                continue
            corrected = _GROUP_OF.get(engine_tg)
        else:
            if written == engine_tg:
                continue
            corrected = engine_tg
        if not corrected or corrected not in _TEN_GODS + tuple(_GROUP_MEMBERS):
            continue
        out.append(text[cursor: m.start("tg")])
        out.append(corrected)
        cursor = m.end("tg")
        fixes.append(TenGodLabelFix(
            position=m.group("pos"), written=written, corrected=corrected,
            excerpt=text[m.start(): m.end()],
        ))
    if not fixes:
        return text, []
    out.append(text[cursor:])
    return _apply_josa(out, fixes), fixes


def _apply_josa(parts: list[str], fixes: list[TenGodLabelFix]) -> str:
    """교체 단어 뒤 조각의 조사를 받침에 맞춘다. parts = [앞, 교체어, 사이, 교체어, …, 끝]."""
    for i in range(1, len(parts), 2):
        parts[i + 1] = _fix_josa(parts[i + 1], parts[i])
    return "".join(parts)
