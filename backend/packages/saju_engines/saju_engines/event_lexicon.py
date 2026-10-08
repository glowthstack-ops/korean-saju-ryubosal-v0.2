"""사건 어휘 층 — 공통 사건 유형 결정론 분류 + 사건 서술 계약 지시문 (2026-09-18 데굴님 승인).

배경(전문가 참고 기준): 작용(합충·십성·신살)과 생활 사건 사이에 "어떤 종류의 문제/개선인가"를
나타내는 중간 층이 없어 LLM이 '쟁합 → 돈을 빼앗김'처럼 사건을 바로 확정했다. 이 모듈은
- `dictionaries/event_process_types.json`의 결정론 규칙으로 후보마다 공통 사건 유형(경쟁·경합,
  지연·보류, 기회 유입, 선발·통과·승인 …)을 붙이고(점수·판정 불변, 서술 참고),
- `dictionaries/life_event_lexicon.json`의 체감→관찰 가능 사건 번역 표·분리 원칙으로 사건 서술
  계약 지시문을 만든다(채팅·리포트 공용).
두 사전은 검증(validate_dictionaries)만 거치고 런타임에 원본을 읽는다(event_forms.json 선례).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from .dictionaries import EventProcessTypesFile, LifeEventLexiconFile

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_FAVORABILITY_BAND_TH = 0.2  # context_reducer._FAVORABILITY_BAND_TH와 같은 밴드 경계
_MAX_TYPES_PER_CANDIDATE = 3


@lru_cache(maxsize=4)
def load_process_types(dictionaries_dir: Path = _DICTS_DEFAULT) -> EventProcessTypesFile:
    """공통 사건 유형 사전(검증 스키마로 로드, 프로세스당 1회)."""
    raw = json.loads((dictionaries_dir / "event_process_types.json").read_text("utf-8"))
    return EventProcessTypesFile.model_validate(raw)


@lru_cache(maxsize=4)
def load_life_event_lexicon(dictionaries_dir: Path = _DICTS_DEFAULT) -> LifeEventLexiconFile:
    """생활 사건 어휘 사전(검증 스키마로 로드)."""
    raw = json.loads((dictionaries_dir / "life_event_lexicon.json").read_text("utf-8"))
    return LifeEventLexiconFile.model_validate(raw)


def _band(favorability: float) -> str:
    if favorability >= _FAVORABILITY_BAND_TH:
        return "favorable"
    if favorability <= -_FAVORABILITY_BAND_TH:
        return "adverse"
    return "neutral"


def derive_process_types(
    event_key: str,
    reason_codes: Iterable[str],
    signal_texts: Iterable[str],
    favorability: float,
    *,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> list[str]:
    """후보 1건 → 공통 사건 유형 이름 목록(최대 3, 사전 순서 보존).

    규칙(사전 match_rules): reason_prefixes(startswith) / signal_keywords(부분일치) /
    event_keys(사건 키 제한 — 비면 무관) 중 하나라도 맞고, favorability 조건(any|adverse|
    favorable)을 만족하면 후보. '손실·손상'은 다른 유형의 자동 결론이 아니므로 favorability가
    adverse 밴드이고 손상 근거 코드가 있을 때만 붙는다(사전 규칙이 이미 그렇게 제한).
    """
    codes = list(reason_codes)
    texts = " ".join(signal_texts)
    band = _band(favorability)
    out: list[str] = []
    for spec in load_process_types(dictionaries_dir).items:
        m = spec.match
        if m.favorability == "adverse" and band != "adverse":
            continue
        if m.favorability == "favorable" and band != "favorable":
            continue
        key_ok = not m.event_keys or event_key in m.event_keys
        hit = any(c.startswith(p) for c in codes for p in m.reason_prefixes) or any(
            k in texts for k in m.signal_keywords
        )
        if m.event_keys and not m.reason_prefixes and not m.signal_keywords:
            hit = key_ok  # 사건 키만으로 정의된 유형
        if hit and key_ok:
            out.append(spec.name_ko)
        if len(out) >= _MAX_TYPES_PER_CANDIDATE:
            break
    return out


def process_type_legend(dictionaries_dir: Path = _DICTS_DEFAULT) -> str:
    """후보 블록 범례 한 줄 — 유형은 '문제/개선의 종류'이지 사건·손실 확정이 아니다."""
    return (
        "(사건 유형 읽는 법: 엔진이 근거 코드·신호로 분류한 '어떤 종류의 문제 또는 개선인가'다. "
        "사건명·길흉 확정이 아니며, 경쟁이 생기는 것≠탈락≠손실, 기회 유입≠성취≠유지다. "
        "'손실·손상' 유형이 없으면 손실을 결론으로 쓰지 말고 확인 대상으로만 둔다.)"
    )


def event_narration_directive(dictionaries_dir: Path = _DICTS_DEFAULT) -> str:
    """사건 서술 계약 지시문(채팅·리포트 공용, 플래그 ON일 때만 부착).

    사전의 분리 원칙·체감→관찰 가능 사건 번역 표를 그대로 싣는다(즉석 작문 금지 — 사전 SSOT).
    """
    lex = load_life_event_lexicon(dictionaries_dir)
    rules = "\n".join(f"- {r}" for r in lex.separation_rules)
    table = "\n".join(
        f"- '{row.perceived}' → {row.observable}" for row in lex.perceived_to_observable
    )
    return (
        "[사건 서술 계약 — 항상 적용(전문가 참고 기준 2026-09-18)]\n"
        "① 사건은 '발생(기회) → 진행 → 결과(성취) → 후속 영향(유지)'을 나눠 쓴다. 신호가 뜬 단계와 "
        "결과가 실현되는 단계는 다르며, 제공된 [상담 결론]의 단계별 행동 지침이 이 네 단계에 "
        "대응한다(기회=발생, 과정=진행, 결정=결과, 실행·실속=후속).\n"
        "② 분리 원칙:\n" + rules + "\n"
        "③ 체감·평가 표현은 확인 가능한 사건으로 번역해 쓴다(예시 표 — 이 형식을 따르되 제공된 "
        "근거에 있는 사건만 고른다):\n" + table + "\n"
        "④ 좋은 사건도 '돈을 얻거나 합격하는 일'로 좁히지 말고 회복·해소·부담 경감·손실 방지·"
        "선택권 확대를 함께 본다. 이직·결혼·사업 확장 자체가 항상 좋은 사건은 아니다 — 본인이 "
        "원했는지·조건이 개선됐는지·부담을 감당할 수 있는지를 함께 본다.\n"
        "⑤ 상속 분쟁·이혼·소송·입원처럼 구체적인 사건은 그 생활 상황이 실제로 있는지 확인되기 "
        "전에는 고르지 않는다 — '경쟁'·'손상' 신호만으로 바로 선택 금지.\n"
        "⑥ 후보의 '사건 유형' 줄이 있으면 그 종류 안에서 서술하고, 그 줄에 없는 종류(특히 손실)를 "
        "결론으로 만들지 않는다."
    )
