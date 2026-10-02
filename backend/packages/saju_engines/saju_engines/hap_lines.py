"""천간합 작용 모드 → LLM 입력용 한 줄 텍스트 (Phase 2a — HAP_INTERACTION_SPEC §F-4).

manse_analysis의 `resolve_stem_hap`(판정)을 호출해, 합화/합반/합거/본신지합/쟁투를 **모드+영향+
신뢰도**가 담긴 사람용 한 줄로 직렬화한다. 단정 금지(절대원칙 3) — 신뢰도(확정/조건부/불성)로 표현.

원국 합(natal)은 캐시되는 고정 prefix(serialize_chart_prefix)에, 운 합(luck)은 기간 grounding에
주입한다. 점수 반영은 Phase 2b.
"""

from __future__ import annotations

from saju_manse_analysis.relations.hap_modes import (
    BranchHapResolution,
    StemHapResolution,
    resolve_branch_hap,
    resolve_stem_hap,
)

from saju_shared_types.constants import BRANCH_CLASHES, STEM_INDEX, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

from . import period_v2_config
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


_TEN_GOD_GROUP_KO = {
    "정관": "관성", "편관": "관성", "정재": "재성", "편재": "재성",
    "정인": "인성", "편인": "인성", "식신": "식상", "상관": "식상", "비견": "비겁", "겁재": "비겁",
}


def _contend_label(r: StemHapResolution, day_master: str | None) -> str:
    """쟁합·투합 표기 — RELATION_TERMS_V2면 다투는 글자의 십성군(관성/재성/인성 쟁합)을 병기.

    참고 기준(2026-09-18): 관성 쟁합=직위·선발·인정의 경쟁, 재성 쟁합=수익·거래·자원 배분의
    경쟁, 인성 쟁합=지원·문서·자격을 둘러싼 경쟁 — '몫 절반'·삼각관계 단정은 하지 않는다.
    """
    if not (period_v2_config.RELATION_TERMS_V2_ENABLED and r.contested_stem and day_master):
        return "쟁합·투합"
    try:
        god = str(ten_god(Stem(day_master), Stem(r.contested_stem)))
    except (KeyError, ValueError):
        return "쟁합·투합"
    group = _TEN_GOD_GROUP_KO.get(god)
    if r.contested_stem == day_master:
        return "쟁합·투합(일간을 두고 다툼 — 관계·선택의 경쟁)"
    return f"쟁합·투합({group} 쟁합 — {god} {r.contested_stem})" if group else "쟁합·투합"


def _format(r: StemHapResolution, fav: dict[str, str], day_master: str | None = None) -> str:
    """StemHapResolution → 한 줄(모드+영향+신뢰도). 운 합은 '운 ' 접두."""
    # 표기 순서를 천간 표준순(甲→癸)으로 정규화 — 자리 순서에 따른 戊癸/癸戊 중복 방지.
    a, b = sorted(r.pair, key=lambda s: STEM_INDEX[Stem(s)])
    pair = f"{a}{b}合"
    prefix = "운 " if r.luck_origin else ""

    if r.blocked:
        body = f"불성립({r.block_reason})"
    elif r.hap_mode == "combine_self":
        if r.chart_transform:
            el = r.transform_element or ""
            body = f"본신지합 → 化氣格 후보(일간이 化神 {el}({fav.get(el, '역할 미상')})으로 化)"
        else:
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
        flags.append(_contend_label(r, day_master))
    if flags:
        tail += " · " + "·".join(flags)
    return f"{prefix}{pair} → {body}{tail}"


def _format_branch(r: BranchHapResolution) -> str:
    """BranchHapResolution(육합/삼합/방합) → 한 줄."""
    prefix = "운 " if r.luck_origin else ""
    mem = "".join(r.members)
    tier = _TIER_KO.get(r.transform_tier, "")
    if r.kind == "six":
        if r.hap_mode == "transform":
            body = f"{mem}合 → 합화 {r.transform_element}({r.role}) · 化 {tier}"
        else:
            eff = " · ".join(_affected_txt(a) for a in r.affected)
            body = f"{mem}合 → 합반(化 불성·묶임)" + (f" · {eff}" if eff else "")
            if r.direction == "away":
                body += " · 합거"
            body += f" · 化 {tier}"
    elif r.kind in ("three_harmony", "half"):
        kname = "삼합" if r.kind == "three_harmony" else "반합"
        royal = "(왕지)" if r.kind == "half" and r.royal_included else ""
        suffix = " 성립" if r.kind == "three_harmony" else ""
        body = f"{mem} {kname}{royal} {r.transform_element}국({r.role}){suffix} · {tier}"
    else:  # directional
        comp = "방합" if len(r.members) == 3 else "방합(부분)"
        body = f"{mem} {comp} {r.transform_element}({r.role}) 강화"
    if r.co_relations:
        body += " · 동시 " + "·".join(r.co_relations)
    return f"{prefix}{body}"


def natal_hap_mode_lines(result: ManseV2Result) -> list[str]:
    """원국 천간합·지지합의 작용 모드 줄(운 무관 — 캐시 고정 prefix용)."""
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    p = result.pillars
    # 쟁합(동일 글자 다자)으로 같은 줄이 중복될 수 있어 순서 보존 dedup.
    lines = [_format(r, fav, p.day_master) for r in resolve_stem_hap(p, fav)]
    lines += [_format_branch(r) for r in resolve_branch_hap(p, fav) if not r.luck_origin]
    return list(dict.fromkeys(lines))


def luck_hap_mode_lines(
    result: ManseV2Result,
    luck_stems: list[str] | None = None,
    luck_branches: list[str] | None = None,
) -> list[str]:
    """운(運) 천간·지지가 원국과 맺는 합의 작용 모드 줄(기간 grounding용).

    원국 합은 natal_hap_mode_lines에서 다루므로, 운 관여(luck_origin) 합만 반환한다.
    """
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    p = result.pillars
    lines: list[str] = []
    if luck_stems:
        lines += [
            _format(r, fav, p.day_master)
            for r in resolve_stem_hap(p, fav, luck_stems=luck_stems)
            if r.luck_origin
        ]
    if luck_branches:
        natal_branches = [
            Branch(x.branch) for x in (p.year, p.month, p.day, p.hour) if x is not None
        ]
        for r in resolve_branch_hap(p, fav, luck_branches=luck_branches):
            if not r.luck_origin:
                continue
            line = _format_branch(r)
            if period_v2_config.RELATION_TERMS_V2_ENABLED and r.kind == "six":
                line += _hapcheo_bongchung_suffix(r, natal_branches)
            lines.append(line)
    return list(dict.fromkeys(lines))


def _hapcheo_bongchung_suffix(r: BranchHapResolution, natal_branches: list[Branch]) -> str:
    """합처봉충(合處逢沖) 표기 — 합으로 연결된 두 글자 중 하나를 원국 다른 지지가 충하면 병기.

    참고 기준(2026-09-18): 계약·협업·관계의 재편, 유지하던 연결의 흔들림. 표기 전용이며
    충 자체의 점수·변동성은 관계 판정이 이미 반영한다(중복 계산 없음).
    """
    hits: list[str] = []
    for m in r.members:
        mb = Branch(m)
        for nb in natal_branches:
            if nb != mb and frozenset({mb, nb}) in BRANCH_CLASHES:
                tag = f"{nb}충{mb}"
                if tag not in hits:
                    hits.append(tag)
    if not hits:
        return ""
    return " · 합처봉충(" + "·".join(hits) + " — 합 자리에 충 개입: 연결의 재편·흔들림)"
