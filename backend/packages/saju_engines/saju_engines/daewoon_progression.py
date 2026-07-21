"""대운 발현 진행(progression) resolver — 서술 전용 inert 레이어 (2026-07-21 데굴님 확정).

목적: "전반 0-4년 천간 / 후반 5-9년 지지" 하드 이분 대신, 기존 신호를 요약해
"기본 그라데이션(계기 선인식→현실화 누적) + 즉시 발동 예외" 모드를 산출한다.
LLM에 원시 합충 목록의 재해석을 맡기지 않고 엔진이 모드를 확정한다(절대원칙 1).

읽기만 하는 기존 신호(luck_cycles가 이미 계산):
- ``DaewoonItem.relations_to_chart`` — "충:X-Y" / "삼합완성:元素" / "방합완성:元素" /
  "삼형:X-..." / "무례지형:X-Y" / "천간합:X-Y" 문자열
- ``DaewoonItem.gongmang_activation`` — "공망발동(충):..." 등
- ``DaewoonItem.branch_effect.is_void`` — 운 지지 자체의 공망 여부
- ``DaewoonItem.stem_ten_god`` / ``branch_ten_god`` — 간여지동 판정

신규 소계산은 '운 천간의 통근'(운 지지+원국 지지 본기·중기 대조) 하나뿐이며, 이는
서술 모드 판정에만 쓰인다. 불변식: 점수·길흉·confidence·후보·시점 절대 불변
(shared_types.daewoon_progression docstring·회귀 테스트로 고정).
"""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT, hidden_stems_for
from saju_shared_types.daewoon_progression import DaewoonProgressionProfile, ProgressionMode
from saju_shared_types.enums import Branch, HiddenStemType, Stem
from saju_shared_types.luck import DaewoonItem
from saju_shared_types.pillars import FourPillarsResult

# 핵심 궁위 = 일지(본인·배우자 기반)·월지(사회 환경) — 충·형이 닿으면 초입부터 현실 변동 가능.
_HYEONG_PREFIXES = ("삼형:", "무례지형:")


def _natal_partner(rel: str, luck_branch: str) -> str:
    """"충:X-Y" 류 쌍 문자열에서 원국 측 글자를 꺼낸다(운 글자가 앞이지만 방어적으로 판별)."""
    pair = rel.split(":", 1)[1].split("-")
    if len(pair) != 2:
        return ""
    return pair[1] if pair[0] == luck_branch else pair[0]


def _stem_rooted(stem: Stem, branches: list[Branch]) -> bool:
    """운 천간이 주어진 지지들(운 지지+원국 지지)의 본기·중기에 같은 오행 뿌리를 갖는가.

    strength/rooting의 통근 개념을 운 천간에 적용한 소계산(여기(residual)는 뿌리로 안 침).
    """
    el = STEM_ELEMENT[stem]
    for b in branches:
        for hstem, htype, _w in hidden_stems_for(b):
            if htype is HiddenStemType.RESIDUAL:
                continue
            if STEM_ELEMENT[hstem] is el:
                return True
    return False


def resolve_daewoon_progression(
    item: DaewoonItem, pillars: FourPillarsResult
) -> DaewoonProgressionProfile:
    """대운 1개의 발현 진행 모드를 기존 신호 요약으로 판정한다(점수·판정 불변).

    우선순위(doc/v2_2/DAEWOON_PROGRESSION_NARRATIVE.md §5):
    ①공망전실+합국 완성 동시(상충) → indeterminate ②조기 발동+천간 작동 → coactivated
    ③간여지동(지지 공망 아님) → coactivated ④조기 발동 → branch_early_activation
    ⑤천간 통근·미합거 → stem_persistent ⑥천간 무근/합거+지지 공망 → weak_manifestation
    ⑦그 외 → default_gradient.
    """
    rels = item.relations_to_chart
    codes: list[str] = []

    # ── 지지 조기 발동 신호(핵심 궁위 충·형 / 합국 완성 / 공망 충발) ──
    day_b, month_b = pillars.day.branch, pillars.month.branch
    for r in rels:
        if r.startswith("충:"):
            partner = _natal_partner(r, item.branch)
            if partner == day_b:
                codes.append("BRANCH_CLASH_DAY_PALACE")
            elif partner == month_b:
                codes.append("BRANCH_CLASH_MONTH_PALACE")
        elif r.startswith(_HYEONG_PREFIXES):
            if r.startswith("삼형:"):
                codes.append("SAMHYEONG")
            else:
                partner = _natal_partner(r, item.branch)
                if partner in (day_b, month_b):
                    codes.append("BRANCH_HYEONG_CORE_PALACE")
        elif r.startswith("삼합완성:"):
            codes.append("SAMHAP_COMPLETE")
        elif r.startswith("방합완성:"):
            codes.append("BANGHAP_COMPLETE")
    void_clash = any(g.startswith("공망발동(충)") for g in item.gongmang_activation)
    if void_clash:
        codes.append("VOID_ACTIVATED_BY_CLASH")
    branch_early = bool(codes)

    # ── 천간 작동성(통근/천간합) — 서술 모드 판정 전용 소계산 ──
    # 지속(persistent) 판정은 '운 천간이 운 지지 자체에 통근'한 경우로 좁힌다 — 원국 어딘가의
    # 뿌리까지 인정하면 거의 모든 대운이 지속형이 되어 기본 그라데이션이 사라진다. 원국 통근은
    # 무근(약발현) 판정에만 쓴다.
    stem = Stem(item.stem)
    rooted_in_luck = _stem_rooted(stem, [Branch(item.branch)])
    rooted_in_natal = _stem_rooted(stem, [Branch(p.branch) for p in _natal_pillars(pillars)])
    combined = any(r.startswith("천간합:") for r in rels)
    if rooted_in_luck:
        codes.append("STEM_ROOTED_IN_LUCK_BRANCH")
    elif rooted_in_natal:
        codes.append("STEM_ROOTED_IN_NATAL")
    else:
        codes.append("STEM_NO_ROOT")
    if combined:
        rooted_any = rooted_in_luck or rooted_in_natal
        codes.append("STEM_COMBINED_BOUND" if rooted_any else "STEM_COMBINED_AWAY")
    stem_active = rooted_in_luck and not combined
    weak_stem = not (rooted_in_luck or rooted_in_natal)  # 합거(합+무근)는 무근에 포섭

    # ── 지지 공망(전실 — 발동 없는 공망) / 간여지동 ──
    is_void = bool(item.branch_effect is not None and item.branch_effect.is_void)
    if is_void and not void_clash:
        codes.append("VOID_PLAIN")
    ganyeojidong = bool(item.stem_ten_god) and item.stem_ten_god == item.branch_ten_god
    if ganyeojidong:
        codes.append("GANYEOJIDONG")

    mode: ProgressionMode
    harmony_complete = any(c in ("SAMHAP_COMPLETE", "BANGHAP_COMPLETE") for c in codes)
    if is_void and not void_clash and harmony_complete:
        # 공망전실(저하)과 합국 완성(발동)이 동시 — 어느 쪽인지 단정 불가.
        mode = "indeterminate"
    elif branch_early and stem_active:
        mode = "coactivated"
    elif ganyeojidong and not is_void:
        mode = "coactivated"
    elif branch_early:
        mode = "branch_early_activation"
    elif stem_active:
        mode = "stem_persistent"
    elif weak_stem and is_void:
        mode = "weak_manifestation"
    else:
        mode = "default_gradient"

    return DaewoonProgressionProfile(
        daewoon_index=item.index,
        ganji=item.ganji,
        start_age=item.start_age,
        mode=mode,
        reason_codes=list(dict.fromkeys(codes)),  # 동일 신호 다중 성립 시 중복 제거(순서 보존)
    )


def resolve_all_daewoon_progressions(
    daewoon_table: list[DaewoonItem], pillars: FourPillarsResult
) -> list[DaewoonProgressionProfile]:
    """대운표 전체에 대한 발현 진행 모드 목록(대운표 렌더·디렉티브 주입용)."""
    return [resolve_daewoon_progression(d, pillars) for d in daewoon_table]


def _natal_pillars(pillars: FourPillarsResult) -> list:
    """원국 기둥 목록(시주는 있을 때만) — luck_cycles._natal과 동일 규약."""
    items = [pillars.year, pillars.month, pillars.day]
    if pillars.hour is not None:
        items.append(pillars.hour)
    return items
