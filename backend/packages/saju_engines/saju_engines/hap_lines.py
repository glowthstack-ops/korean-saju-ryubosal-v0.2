"""천간합 작용 모드 → LLM 입력용 한 줄 텍스트 (Phase 2a — HAP_INTERACTION_SPEC §F-4).

manse_analysis의 `resolve_stem_hap`(판정)을 호출해, 합화/합반/합거/본신지합/쟁투를 **모드+영향+
신뢰도**가 담긴 사람용 한 줄로 직렬화한다. 단정 금지(절대원칙 3) — 신뢰도(확정/조건부/불성)로 표현.

원국 합(natal)은 캐시되는 고정 prefix(serialize_chart_prefix)에, 운 합(luck)은 기간 grounding에
주입한다. 점수 반영은 Phase 2b.
"""

from __future__ import annotations

from saju_manse_analysis.relations.hap_modes import StemHapResolution, resolve_stem_hap

from saju_shared_types.constants import STEM_INDEX
from saju_shared_types.enums import Stem
from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import favorability_map

_TIER_KO = {"confirmed": "확정", "conditional": "조건부", "none": "불성"}
_EFFECT_KO = {"boon": "유리(흉 제거)", "harm": "불리(길 상실)", "neutral": ""}


def _affected_txt(a: object) -> str:
    """묶인 천간 1개 → '辛 정관=희신 불리(길 상실)' 형식."""
    stem = getattr(a, "stem", "")
    god = getattr(a, "ten_god", "")
    role = getattr(a, "role", "")
    eff = _EFFECT_KO.get(getattr(a, "effect", ""), "")
    s = f"{stem} {god}" + (f"={role}" if role else "")
    return f"{s} {eff}".rstrip()


def _format(r: StemHapResolution, fav: dict[str, str]) -> str:
    """StemHapResolution → 한 줄(모드+영향+신뢰도). 운 합은 '운 ' 접두."""
    # 표기 순서를 천간 표준순(甲→癸)으로 정규화 — 자리 순서에 따른 戊癸/癸戊 중복 방지.
    a, b = sorted(r.pair, key=lambda s: STEM_INDEX[Stem(s)])
    pair = f"{a}{b}合"
    prefix = "운 " if r.luck_origin else ""

    if r.blocked:
        body = f"불성립({r.block_reason})"
    elif r.hap_mode == "combine_self":
        body = "본신지합(합거 아님)"
        if r.affected:
            body += f" · {_affected_txt(r.affected[0])} 유지"
    elif r.hap_mode == "transform":
        el = r.transform_element or ""
        body = f"합화 {el}({fav.get(el, '역할 미상')})"
    else:  # bind — 합반 + 합거 효과
        eff = " · ".join(_affected_txt(a) for a in r.affected)
        body = "합반(化 불성)" + (f" · {eff}" if eff else "")
        if r.direction == "away":
            body += " · 합거"

    tail = f" · 化 {_TIER_KO.get(r.transform_tier, '')}" if r.transform_element else ""
    flags = []
    if r.weakened:
        flags.append("隔位 약화")
    if r.contend:
        flags.append("쟁합·투합")
    if flags:
        tail += " · " + "·".join(flags)
    return f"{prefix}{pair} → {body}{tail}"


def natal_hap_mode_lines(result: ManseV2Result) -> list[str]:
    """원국 천간합의 작용 모드 줄(운 무관 — 캐시 고정 prefix용)."""
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    # 쟁합(동일 글자 다자)으로 같은 줄이 중복될 수 있어 순서 보존 dedup.
    return list(dict.fromkeys(_format(r, fav) for r in resolve_stem_hap(result.pillars, fav)))


def luck_hap_mode_lines(result: ManseV2Result, luck_stems: list[str]) -> list[str]:
    """운(運) 천간이 원국과 맺는 천간합의 작용 모드 줄(기간 grounding용).

    원국 합은 natal_hap_mode_lines에서 다루므로, 운 관여(luck_origin) 합만 반환한다.
    """
    if result.pillars is None or not luck_stems:
        return []
    fav = favorability_map(result)
    res = resolve_stem_hap(result.pillars, fav, luck_stems=luck_stems)
    return list(dict.fromkeys(_format(r, fav) for r in res if r.luck_origin))
