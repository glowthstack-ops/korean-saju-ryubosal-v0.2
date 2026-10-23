"""확장 공망 산출 — 旬 머리·사대공망(납음)·절로공망·호환공망 (사실 산출만, 2026-10-23 데굴님 승인).

해석 규칙은 도입하지 않는다(절대 원칙 10). 정의 출처(웹 확인, SSOT §7):
- 사대공망(四大空亡): 납음 오행 결손. 甲子·甲午旬은 납음 水가, 甲寅·甲申旬은 납음 金이 없다
  (甲辰·甲戌旬은 오행 완비). 판정 기둥은 **일주**, 지장간은 **미포함**(데굴님 확정). 다른 세 기둥의
  납음이 결 오행이면 '해당'.
- 절로공망(截路空亡): 시간(時干)이 壬·癸 — 甲己日 申酉時·乙庚日 午未時·丙辛日 辰巳時·丁壬日 寅卯時·
  戊癸日 子丑時와 동치.
- 호환공망(互換空亡): 연주와 일주(또는 일주와 시주)가 서로의 旬 공망 글자를 지지로 가진 경우.
- 旬 머리: 일주가 속한 甲X旬 — 동반자 동순(同旬) 비교용 사실.
"""

from __future__ import annotations

from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_shared_types.constants import BRANCH_INDEX, BRANCHES, STEM_INDEX
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.gongmang import ExtendedGongmang
from saju_shared_types.pillars import FourPillarsResult

_NAEUM_KO_ELEMENT = {"금": "金", "목": "木", "수": "水", "화": "火", "토": "土"}
_SADAE_MISSING: dict[str, str] = {"子": "水", "午": "水", "寅": "金", "申": "金"}
_POS_KO = {"year": "연주", "month": "월주", "hour": "시주"}


def xun_head_branch(stem: Stem, branch: Branch) -> Branch:
    """간지가 속한 旬의 머리(甲의 지지)."""
    return BRANCHES[(BRANCH_INDEX[branch] - STEM_INDEX[stem]) % 12]


def naeum_element(naeum: str | None) -> str | None:
    """납음 한글 이름('해중금') → 오행 한자('金')."""
    if not naeum:
        return None
    return _NAEUM_KO_ELEMENT.get(naeum[-1])


def extended_gongmang(pillars: FourPillarsResult) -> ExtendedGongmang:
    """확장 공망 사실 산출(일주 기준)."""
    d_stem, d_branch = Stem(pillars.day.stem), Branch(pillars.day.branch)
    head = xun_head_branch(d_stem, d_branch)
    xun = f"甲{head}旬"
    facts: list[str] = [f"일주 {xun}"]

    missing = _SADAE_MISSING.get(str(head))
    hits: list[str] = []
    if missing is not None:
        for pos in ("year", "month", "hour"):
            p = getattr(pillars, pos, None)
            if p is not None and naeum_element(p.naeum) == missing:
                hits.append(_POS_KO[pos])
        if hits:
            facts.append(
                f"사대공망 해당({xun} 납음 {missing} 결 — {'·'.join(hits)} 납음 {missing})"
            )

    jeollo = pillars.hour is not None and pillars.hour.stem in ("壬", "癸")
    if jeollo:
        assert pillars.hour is not None
        facts.append(f"절로공망(시간 {pillars.hour.stem})")

    day_void = set(gongmang_branches(d_stem, d_branch))
    hohwan: list[str] = []
    y_void = set(gongmang_branches(Stem(pillars.year.stem), Branch(pillars.year.branch)))
    if Branch(pillars.year.branch) in day_void and d_branch in y_void:
        hohwan.append("연↔일")
    if pillars.hour is not None:
        h_void = set(gongmang_branches(Stem(pillars.hour.stem), Branch(pillars.hour.branch)))
        if Branch(pillars.hour.branch) in day_void and d_branch in h_void:
            hohwan.append("일↔시")
    if hohwan:
        facts.append("호환공망 " + "·".join(hohwan))

    return ExtendedGongmang(
        xun_head=xun, sadae_missing_element=missing, sadae_hits=hits, jeollo=jeollo,
        hohwan=hohwan, facts_ko=facts,
    )
