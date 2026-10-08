"""원국 관계 목록의 순서 결정성 — 합·방합 글자는 원국 자리 순, 자형은 12지 정의 순 (2026-10-08).

배경: 사례집 재생 비교에서 `three_harmony:未卯亥` ↔ `未亥卯` 처럼 같은 관계의 글자 나열이
프로세스마다 달랐다(frozenset 순회 + 문자열 해시 무작위화). 판정 로직은 그대로 두고 표기 순서만
고정한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from saju_api.services.manse_service import calculate
from saju_manse_core.relations.relations import detect
from saju_shared_types.birth_input import BirthInput

_CHARTS = ("1963-01-03 00:30 male", "1985-10-29 22:20 female", "1980-11-22 09:40 male",
           "1951-03-15 06:00 male")

# 하위 프로세스용 — 테스트 모듈을 import 하지 않고 엔진만 부른다(해시 시드 독립성 검사).
_SNIPPET = """
import json
from saju_api.services.manse_service import calculate
from saju_manse_core.relations.relations import detect
from saju_shared_types.birth_input import BirthInput
out = []
for spec in %r:
    d, t, g = spec.split()
    r = calculate(BirthInput(calendar_type="solar", birth_date=d, birth_time=t,
                             birth_place_name="서울", gender=g))
    out.append([[x.rel_type, x.positions, x.members] for x in detect(r.pillars)])
print("@@" + json.dumps(out, ensure_ascii=False))
"""


def test_harmony_members_follow_pillar_order() -> None:
    """삼합·반합·방합 구성 글자가 연→월→일→시 등장 순으로 나열된다."""
    for spec in _CHARTS:
        d, t, g = spec.split()
        r = calculate(BirthInput(calendar_type="solar", birth_date=d, birth_time=t,
                                 birth_place_name="서울", gender=g))
        order = [p.branch for p in (r.pillars.year, r.pillars.month, r.pillars.day,
                                    r.pillars.hour) if p is not None]
        for rel in detect(r.pillars):
            if rel.rel_type in ("three_harmony", "half_harmony", "directional"):
                first_pos = [next(i for i, b in enumerate(order) if b == m)
                             for m in rel.members]
                assert first_pos == sorted(first_pos), (spec, rel.rel_type, rel.members)


def test_relation_list_identical_across_hash_seeds() -> None:
    """PYTHONHASHSEED 를 바꾼 별도 프로세스에서도 관계 목록(종류·자리·글자 순서)이 동일하다."""
    outs = []
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        res = subprocess.run([sys.executable, "-c", _SNIPPET % (_CHARTS,)], capture_output=True,
                             text=True, env=env, cwd=os.getcwd(), check=True)
        line = next(ln for ln in res.stdout.splitlines() if ln.startswith("@@"))
        outs.append(json.loads(line[2:]))
    assert outs[0] == outs[1] == outs[2]
    assert any(rel[0] in ("three_harmony", "half_harmony", "directional")
               for chart in outs[0] for rel in chart)  # 검사 대상 관계가 실제로 있다
