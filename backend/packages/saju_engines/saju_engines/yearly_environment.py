"""세운 환경 블록 — 월주 상대 관점(2026-10-25 데굴님 승인, 별의당 「운명의 병오년」 번역층).

세운을 두 방향으로 읽는다.
  ① 환경 = 월주(명주가 살아가는 환경) ↔ 세운의 **상대 기운**
       - 월간 기준 세운 천간·지지 십성 + 세운 지지의 12운성(壬에게 丙=편재, 午=정재·胎地)
       - 세운 천간 기준 월주 천간·지지 십성 + 월지의 12운성(丙에게 壬=편관, 寅=편인·長生地)
       - 세운 지지 ↔ 월지 형충회합(寅午 반합 → 火 강화 → 운 천간에 힘)
       - 세운 천간 ↔ 월간 천간합·천간충(丙壬沖 = 긴장·관문, 소멸 아님)
       - 통근 비교(운 천간·월간이 {월지, 세운 지지} 지장간에 뿌리가 있는가)
  ② 태도 = 일간 기준 세운 십성·12운성 — 기존 `[세운:]` 줄(`incoming_ten_god_note`)이 담당.

이 모듈은 ①의 **사실**을 기존 순수 함수(`ten_god`·`twelve_unseong`·관계 상수표·지장간표)로 산출하고
사전(`interpretations/yearly_environment.json`)의 어휘를 붙여 렌더한다. 신규 명리 규칙은 없다.
학파 라벨 규약은 `career_field._render_ganji_school` 과 같다 — 머리말에 "[월주 상대 관점]" 을 붙이고
LLM 은 '월주와 세운의 상대 기운으로 보면 ~' 로 서술한다. 길흉·유불리는 일간 기준 용희기구한 판정이
정하며 이 층은 점수·후보·역할 판정에 관여하지 않는다(서술 전용, inert).
적용 범위: **세운 전용**(period_type == "year"). 대운·월운은 2026-10-25 데굴님 결정으로 미적용.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    DIRECTIONAL_COMBINATIONS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    STEM_CLASHES,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    THREE_HARMONY,
    hidden_stems_for,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

_DICT_DIR = Path(__file__).resolve().parents[3] / "dictionaries"
_DICT_FILE = "interpretations/yearly_environment.json"


@lru_cache(maxsize=2)
def _load_dict(path: str = "") -> dict:
    """사전 원본(JSON) — 경로 미지정이면 리포 기본 사전."""
    p = Path(path) if path else _DICT_DIR / _DICT_FILE
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class YearlyEnvironment:
    """월주 × 세운 상대 기운 사실(엔진 확정값, 서술 전용).

    Attributes:
        year_label: 세운 라벨('2026').
        luck_ganji: 세운 간지('丙午').
        month_ganji: 원국 월주 간지('壬寅').
        forward_stem_tg: 월간 기준 세운 천간 십성('편재').
        forward_branch_tg: 월간 기준 세운 지지 본기 십성('정재').
        forward_branch_main: 세운 지지 본기 천간('丁').
        forward_stage: 월간 기준 세운 지지 12운성('태').
        reverse_stem_tg: 세운 천간 기준 월간 십성('편관').
        reverse_branch_tg: 세운 천간 기준 월지 본기 십성('편인').
        reverse_branch_main: 월지 본기 천간('甲').
        reverse_stage: 세운 천간 기준 월지 12운성('장생').
        branch_relations: 세운 지지 ↔ 월지 관계 (키, 표시 라벨) 목록. 없으면 빈 목록.
        stem_relation: 세운 천간 ↔ 월간 관계 키('stem_clash'/'stem_combination') 또는 None.
        luck_rooted: 세운 천간이 {월지, 세운 지지} 지장간에 같은 오행 뿌리를 두는가.
        month_rooted: 월간이 같은 두 지지에 뿌리를 두는가.
        luck_roots: 세운 천간의 뿌리 지지 목록(표시용).
        month_roots: 월간의 뿌리 지지 목록(표시용).
    """

    year_label: str
    luck_ganji: str
    month_ganji: str
    forward_stem_tg: str
    forward_branch_tg: str
    forward_branch_main: str
    forward_stage: str
    reverse_stem_tg: str
    reverse_branch_tg: str
    reverse_branch_main: str
    reverse_stage: str
    branch_relations: list[tuple[str, str]] = field(default_factory=list)
    stem_relation: str | None = None
    luck_rooted: bool = False
    month_rooted: bool = False
    luck_roots: list[str] = field(default_factory=list)
    month_roots: list[str] = field(default_factory=list)

    @property
    def rooting_key(self) -> str:
        """통근 비교 4상태 키 — 사전 `rootingEnv` 와 1:1."""
        if self.luck_rooted and self.month_rooted:
            return "both"
        if self.luck_rooted:
            return "luck_only"
        if self.month_rooted:
            return "month_only"
        return "neither"


def _is_rooted(stem: Stem, branches: list[Branch]) -> list[str]:
    """`stem` 과 같은 오행의 지장간(본기·중기·여기)을 가진 지지 목록 — 통근(동오행 지장간) 판정."""
    el = STEM_ELEMENT[stem]
    out: list[str] = []
    for b in branches:
        if any(STEM_ELEMENT[hs] == el for hs, _typ, _w in hidden_stems_for(b)):
            out.append(b.value)
    return out


def _branch_pair_relations(luck: Branch, month: Branch) -> list[tuple[str, str]]:
    """세운 지지 ↔ 월지 두 글자만으로 성립하는 형충회합(키, 라벨).

    두 글자 관계에 한정한다 — 원국 다른 자리까지 끌어들인 삼합 완성·삼형은 기존 grounding
    (`relations_to_chart`·계층 블록)이 담당하므로 여기서 중복 판정하지 않는다. 반합은 엔진
    (`luck_cycles._relations_to_chart`)과 같은 기준으로 왕지가 포함될 때만 '반합'이고, 아니면
    '삼합 부분 가세(미약)'로 낸다.
    """
    out: list[tuple[str, str]] = []
    pair = frozenset({luck, month})
    lb, mb = luck.value, month.value
    if luck == month:
        if luck in SELF_PUNISHMENT:
            out.append(("branch_self_punishment", f"{lb}{mb}자형"))
        return out
    if pair in BRANCH_CLASHES:
        out.append(("branch_clash", f"{lb}{mb}충"))
    if pair in SIX_COMBINATIONS:
        out.append(("branch_six_combination", f"{lb}{mb}육합({SIX_COMBINATIONS[pair].value})"))
    for members, element, royal in THREE_HARMONY:
        if pair <= members:
            if royal in pair:
                out.append(("branch_half_harmony", f"{lb}{mb}반합({element.value})"))
            else:
                out.append(("branch_harmony_partial", f"{lb}{mb} 삼합 부분({element.value})"))
    for members, element in DIRECTIONAL_COMBINATIONS:
        if pair <= members:
            out.append(("branch_directional_partial", f"{lb}{mb} 방합 부분({element.value})"))
    if pair in PUNISHMENT_MUTUAL or any(pair <= t for t in PUNISHMENT_TRIPLES):
        out.append(("branch_punishment", f"{lb}{mb}형"))
    if pair in BRANCH_BREAKS:
        out.append(("branch_break", f"{lb}{mb}파"))
    if pair in BRANCH_HARMS:
        out.append(("branch_harm", f"{lb}{mb}해"))
    return out


def build_yearly_environment(
    result: ManseV2Result, luck_pillar: object
) -> YearlyEnvironment | None:
    """세운 1개에 대한 월주 상대 기운 사실을 만든다. 세운이 아니거나 계산 불가면 None.

    Args:
        result: 만세 결과(월주 필요).
        luck_pillar: 해당 연 LuckPillar(period_type == "year", ganji 2자).

    Returns:
        YearlyEnvironment 또는 None(세운 아님·원국 없음·간지 비정상).
    """
    if result.pillars is None:
        return None
    if getattr(luck_pillar, "period_type", "") != "year":
        return None
    ganji = str(getattr(luck_pillar, "ganji", "") or "")
    if len(ganji) != 2:
        return None
    try:
        ls, lb = Stem(ganji[0]), Branch(ganji[1])
        ms, mb = Stem(result.pillars.month.stem), Branch(result.pillars.month.branch)
    except ValueError:
        return None
    lb_main = main_hidden_stem(lb)
    mb_main = main_hidden_stem(mb)
    stem_pair = frozenset({ls.value, ms.value})
    stem_relation: str | None = None
    if ls != ms:
        if stem_pair in STEM_CLASHES:
            stem_relation = "stem_clash"
        elif frozenset({ls, ms}) in STEM_COMBINATIONS:
            stem_relation = "stem_combination"
    roots = [mb, lb]
    luck_roots = _is_rooted(ls, roots)
    month_roots = _is_rooted(ms, roots)
    return YearlyEnvironment(
        year_label=str(getattr(luck_pillar, "label", "")),
        luck_ganji=ganji,
        month_ganji=f"{ms.value}{mb.value}",
        forward_stem_tg=str(ten_god(ms, ls)),
        forward_branch_tg=str(ten_god(ms, lb_main)),
        forward_branch_main=lb_main.value,
        forward_stage=twelve_unseong(ms, lb),
        reverse_stem_tg=str(ten_god(ls, ms)),
        reverse_branch_tg=str(ten_god(ls, mb_main)),
        reverse_branch_main=mb_main.value,
        reverse_stage=twelve_unseong(ls, mb),
        branch_relations=_branch_pair_relations(lb, mb),
        stem_relation=stem_relation,
        luck_rooted=bool(luck_roots),
        month_rooted=bool(month_roots),
        luck_roots=luck_roots,
        month_roots=month_roots,
    )


def render_yearly_environment(env: YearlyEnvironment | None, *, dict_path: str = "") -> list[str]:
    """'[월주 상대 관점 — 시절이 만드는 환경]' 블록(LLM 입력 줄). env 가 None 이면 빈 목록.

    사실 줄 5개 + 서술 규칙 1줄. 어휘는 전부 사전에서 고르기만 한다(즉석 작문 없음).
    """
    if env is None:
        return []
    d = _load_dict(dict_path)
    label, nar = d["label"], d["narration"]
    tg = {it["tenGod"]: it for it in d["tenGodEnv"]}
    st = {it["stage"]: it for it in d["stageEnv"]}
    rel, root = d["relationEnv"], d["rootingEnv"]
    ls, lb = env.luck_ganji[0], env.luck_ganji[1]
    ms, mb = env.month_ganji[0], env.month_ganji[1]

    def _stage(name: str) -> str:
        it = st.get(name)
        return f"{name}({it['hanja']})지" if it else f"{name}지"

    def _stage_text(name: str) -> str:
        it = st.get(name)
        return it["text"] if it else ""

    lines = [
        f"[{label} — 시절이 만드는 환경 (학파 서술: '{nar} ~'로 쓸 것. 일간 기준 용신·길흉 판정과 "
        "합산·상쇄 금지, 단정 금지. 아래 사실과 어휘 밖의 십성·운성을 새로 계산하지 말 것)]",
        f"- 환경 자리: 월주 {env.month_ganji}(월간 {ms}·월지 {mb}) × 세운 {env.year_label} "
        f"{env.luck_ganji}",
        (
            f"- 월간 {ms}에게 세운 {env.luck_ganji}: 천간 {ls}={env.forward_stem_tg} · "
            f"지지 {lb}={env.forward_branch_tg}(본기 {env.forward_branch_main}) · "
            f"{lb}={ms}의 {_stage(env.forward_stage)} — "
            f"{tg.get(env.forward_stem_tg, {}).get('forward', '')}; 지지 쪽은 "
            f"{tg.get(env.forward_branch_tg, {}).get('forward', '')}; "
            f"상태: {_stage_text(env.forward_stage)}"
        ),
        (
            f"- 세운 천간 {ls}에게 월주 {env.month_ganji}: 천간 {ms}={env.reverse_stem_tg} · "
            f"지지 {mb}={env.reverse_branch_tg}(본기 {env.reverse_branch_main}) · "
            f"{mb}={ls}의 {_stage(env.reverse_stage)} — "
            f"{tg.get(env.reverse_stem_tg, {}).get('reverse', '')}; 지지 쪽은 "
            f"{tg.get(env.reverse_branch_tg, {}).get('reverse', '')}; "
            f"상태: {_stage_text(env.reverse_stage)}"
        ),
    ]
    if env.branch_relations:
        parts = [f"{lab} — {rel.get(key, '')}" for key, lab in env.branch_relations]
        lines.append(f"- 지지 관계(세운 {lb} ↔ 월지 {mb}): " + " / ".join(parts))
    else:
        lines.append(f"- 지지 관계(세운 {lb} ↔ 월지 {mb}): 없음 — {rel['none']}")
    if env.stem_relation == "stem_clash":
        lines.append(f"- 천간 관계(세운 {ls} ↔ 월간 {ms}): {ls}{ms}충 — {rel['stem_clash']}")
    elif env.stem_relation == "stem_combination":
        lines.append(f"- 천간 관계(세운 {ls} ↔ 월간 {ms}): {ls}{ms}합 — {rel['stem_combination']}")
    else:
        lines.append(f"- 천간 관계(세운 {ls} ↔ 월간 {ms}): 합·충 없음")

    def _mark(roots: list[str]) -> str:
        return "·".join(f"{b}({'○' if b in roots else '×'})" for b in (mb, lb))

    lines.append(
        f"- 통근(월지·세운 지지 기준): 세운 천간 {ls} → {_mark(env.luck_roots)} / "
        f"월간 {ms} → {_mark(env.month_roots)} — {root[env.rooting_key]}"
    )
    lines.append(f"- 서술 규칙: {d['synthesis']}")
    return lines


__all__ = ["YearlyEnvironment", "build_yearly_environment", "render_yearly_environment"]
