"""연운 시대 기운 + 부/귀 지향 단위 테스트 (v2.2).

'개인을 사회운(시대 기운) 안에서 본다'와 '부로 가나 귀로 가나'는 사주 풀이의 기본 축이다.
시대 기운은 명리 한정(경제 예측 없음), 부/귀는 격국·분포 기반 방향(우열 아님)임을 검증한다.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.era_energy import era_energy_profile
from saju_engines.wealth_status_lean import analyze_wealth_status_lean
from saju_shared_types.birth_input import BirthInput


def test_era_energy_2026_byeong_o() -> None:
    """2026 丙午 — 여름 火왕 + 음양 교차(하지). 경제·시장 단정 문구 없음."""
    era = era_energy_profile("丙", "午")
    assert era.dominant_element == "火" and era.season == "여름"
    assert "교차" in era.yinyang  # 午 = 양→음 교차
    assert "드러남" in era.keywords  # 火 통설 키워드
    # 명리 기운 톤만 — 경제·시장 '예측' 어휘 미포함('경제 단정 아님' 면책 문구는 허용).
    assert all(w not in era.summary for w in ("부동산", "주식", "채용", "취업률", "시장"))


def test_wealth_status_lean_wealth_chart() -> None:
    """재격·재성 우세 → 부 지향(우열 아님, 방향)."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))
    w = analyze_wealth_status_lean(r)
    assert w.lean in ("부", "귀", "부귀겸전", "뚜렷하지 않음")
    assert w.lean == "부"  # 정재격 + 재성 30% > 관성 11%
    assert w.geokguk_group == "wealth" and "방향" in w.note
