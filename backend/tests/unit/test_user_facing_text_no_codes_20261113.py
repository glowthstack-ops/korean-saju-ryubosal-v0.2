"""만세력 화면에 그대로 실리는 문구에 영문 코드가 섞이지 않는다(2026-11-13).

데굴님 "만세력 등에서 가끔 한글이 아닌 영문 변수명으로 출력되는 값들이 있어. 모두 수정해줘 —
기각·강등: 水(overwhelmed_by_wealth)". 용신 패널이 그대로 그리는 필드(경고·선정 경로·축 충돌·
기각 사유·후보 라벨)를 표본 명식으로 훑는다. 기계용 코드 필드(`reason`·`model_type`)는
대상이 아니다.
"""

from __future__ import annotations

import random
import re
from datetime import date, time

from saju_manse_analysis.yongsin.candidates import rejected_reason_ko

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

#: 영문 식별자(세 글자 이상) — 한자·한글·숫자·기호는 통과.
_ENGLISH = re.compile(r"[A-Za-z][A-Za-z_]{2,}")


def _sample_charts(n: int = 60):
    rng = random.Random(20261113)
    for _ in range(n):
        yield calculate(BirthInput(
            birth_date=date(rng.randint(1950, 2010), rng.randint(1, 12), rng.randint(1, 28)),
            birth_time=time(rng.randint(0, 23), rng.randint(0, 59)),
            birth_place_name="서울", gender=rng.choice(["male", "female"]),
        ))


def test_yongsin_panel_text_has_no_english_codes() -> None:
    seen_rejected = seen_warning = 0
    for r in _sample_charts():
        y = r.yongsin_analysis
        assert y is not None and y.decision_trace is not None
        shown = [
            *(y.warnings or []),
            y.decision_trace.problem,
            y.decision_trace.chosen_path,
            *(y.decision_trace.collateral or []),
            *(m.label for m in y.candidate_models),
        ]
        if y.decision_trace.axis_conflict:
            shown.append(str(y.decision_trace.axis_conflict["resolution"]))
        for rej in y.decision_trace.rejected:
            # 화면은 reason_ko 만 쓴다 — 모든 기각·강등 항목에 한글 사유가 있어야 한다.
            assert rej.get("reason_ko"), rej
            shown.append(rej["reason_ko"])
            seen_rejected += 1
        seen_warning += len(y.warnings or [])
        for text in shown:
            assert not _ENGLISH.search(text or ""), text
    # 반례 보장: 표본에 경고·기각 항목이 실제로 있어야 검사가 의미가 있다.
    assert seen_rejected > 20 and seen_warning > 20


def test_rejected_reason_ko_translates_every_code() -> None:
    assert rejected_reason_ko("overwhelmed_by_wealth") == "재성에 눌려 힘을 못 씀"
    assert rejected_reason_ko("overwhelmed_by_peer") == "비겁에 눌려 힘을 못 씀"
    assert rejected_reason_ko("climate_demote") == "조후 역행으로 강등"
    assert rejected_reason_ko("climate_penalty:mild(×0.4)") == "조후 역행 약한 감점(×0.4)"
    assert rejected_reason_ko("climate_penalty:severe(×0.2)") == "조후 역행 강한 감점(×0.2)"
    # 이미 한글인 사유는 그대로다. 기계용 코드(reason)는 바꾸지 않는다(다른 테스트가 코드로 검사).
    assert rejected_reason_ko("경쟁 후보(점수 차 0.12)") == "경쟁 후보(점수 차 0.12)"
    for code in ("overwhelmed_by_output", "overwhelmed_by_resource", "overwhelmed_by_officer"):
        assert not _ENGLISH.search(rejected_reason_ko(code)), code
