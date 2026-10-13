"""도화(桃花) 구조 판정 — 원국 기준 순수 함수 (2026-10-13 데굴님 확정 정비 기준).

새 명리 계산을 하지 않는다 — 진도화는 신살 집계기(`sinsal_aggregator`)와 같은 상대 12신살
역조회(`branch_of_sinsal(base, "년살")`)를, 십성은 만세 결과의 지지 본기 십성을 그대로 쓴다
(절대원칙 1). 이 모듈은 그 사실들을 '어느 기준에서 어느 자리에 어떤 십성으로 성립했는가'로
구조화할 뿐이다. 판정 원칙은 `saju_shared_types.dohwa` 모듈 docstring 참조.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from saju_shared_types.dohwa import (
    DohwaBase,
    DohwaEstablishment,
    DohwaProfile,
    DohwaTenGodGroup,
    PillarSlot,
    SajeongMarker,
)
from saju_shared_types.enums import Branch
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.pillars import Pillar
from saju_shared_types.twelve_sinsal import branch_of_sinsal, trine_group_label

#: 子午卯酉 — 사정지(왕지) 보유 표지. 신살 집계기 SAJEONG 과 같은 집합.
_SAJEONG: frozenset[Branch] = frozenset({Branch.JA, Branch.O, Branch.MYO, Branch.YU})

#: 십성 → 십성군. 편관·정관은 관성, 편인·정인은 인성으로 묶는다.
_TEN_GOD_GROUP: dict[str, DohwaTenGodGroup] = {
    "비견": DohwaTenGodGroup.PEER, "겁재": DohwaTenGodGroup.PEER,
    "식신": DohwaTenGodGroup.OUTPUT, "상관": DohwaTenGodGroup.OUTPUT,
    "편재": DohwaTenGodGroup.WEALTH, "정재": DohwaTenGodGroup.WEALTH,
    "편관": DohwaTenGodGroup.OFFICER, "정관": DohwaTenGodGroup.OFFICER,
    "편인": DohwaTenGodGroup.RESOURCE, "정인": DohwaTenGodGroup.RESOURCE,
}


def analyze_dohwa(result: ManseV2Result) -> DohwaProfile | None:
    """원국 도화 구조를 판정한다(운 미반영).

    Args:
        result: 만세 계산 결과.

    Returns:
        DohwaProfile. 명식이 없으면 None.
    """
    p = result.pillars
    if p is None:
        return None
    slots: list[tuple[PillarSlot, Pillar]] = [
        ("year", p.year), ("month", p.month), ("day", p.day),
    ]
    hour_known = p.hour is not None
    if p.hour is not None:
        slots.append(("hour", p.hour))

    bases_src: list[tuple[Literal["year", "day"], Branch]] = [
        ("year", Branch(p.year.branch)), ("day", Branch(p.day.branch)),
    ]
    established: list[DohwaEstablishment] = []
    for position, pillar in slots:
        branch = Branch(pillar.branch)
        bases = [
            DohwaBase(slot=slot, branch=base.value, trine=trine_group_label(base))
            for slot, base in bases_src
            if branch_of_sinsal(base, "년살") == branch
        ]
        if not bases:
            continue
        # 십성은 만세 결과가 항상 10종 중 하나로 산출한다 — 모르는 값이면 결함이므로 숨기지 않는다.
        group = _TEN_GOD_GROUP[pillar.branch_main_ten_god]
        established.append(DohwaEstablishment(
            position=position, branch=branch.value, bases=bases,
            ten_god=pillar.branch_main_ten_god, group=group, wolldam=position == "hour",
        ))

    markers = [
        SajeongMarker(position=position, branch=pillar.branch)
        for position, pillar in slots
        if Branch(pillar.branch) in _SAJEONG
    ]
    wolldam: Literal["established", "not_established", "undetermined"]
    if not hour_known:
        wolldam = "undetermined"
    elif any(e.wolldam for e in established):
        wolldam = "established"
    else:
        wolldam = "not_established"
    return DohwaProfile(
        established=established, sajeong_markers=markers,
        wolldam_status=wolldam, hour_known=hour_known,
    )


_DOHWA_TEXT_PATH = (
    Path(__file__).resolve().parents[3] / "dictionaries" / "interpretations" / "dohwa_text.json"
)


@lru_cache(maxsize=1)
def load_dohwa_texts() -> dict[str, dict]:
    """도화 해석 사전 → {'type:<key>': 항목, 'combo:<군>': 항목}.

    reviewed:false 도 그대로 돌려준다 — 검수는 실제 사용자 답변을 확인해야 가능하므로 풀이에
    연결하고, 노출 원장(로그 `dohwa_text_exposed`)으로 실답 검수 경로를 둔다(2026-10-13).
    """
    data = json.loads(_DOHWA_TEXT_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {f"type:{t['key']}": t for t in data["types"]}
    out.update({f"combo:{c['group']}": c for c in data["combos"]})
    return out
