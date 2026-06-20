"""결혼·자산 자원 구조 분석 단위 테스트 (v2.2).

실사례(둘 다 丙火 여성, 60대 = 1961-09-30, 같은 년월일·다른 시주):
- 午시(甲午): 시주 인성·비겁 → 부모 혜택·보호 구조(parental).
- 卯시(辛卯): 시주 정재 → 결혼 후·결과 자리 재성(시댁 재력 잠재 = spouse_family) + 卯酉충 발동.

핵심 검증 = **시주 하나가 자산 출처 경향을 가른다**(구조 신호, 예측 아님). 여성 명식에서 관성이
드러나지 않아도(투간·본기 기준) 재성 환경이 강하면 spouse_family 잠재가 잡힌다.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_shared_types.birth_input import BirthInput


def _profile(time_: str):
    return analyze_marriage_resource(
        calculate(
            BirthInput(
                calendar_type="solar", birth_date="1961-09-30", birth_time=time_,
                birth_place_name="서울", gender="female",
            )
        )
    )


def test_hour_pillar_splits_wealth_source() -> None:
    """같은 년월일·다른 시주 → 자산 출처 경향이 갈린다(午시=parental만, 卯시=+spouse_family)."""
    left = _profile("12:00")   # 甲午시 — 시주 인성
    right = _profile("06:00")  # 辛卯시 — 시주 정재
    assert left.wealth_element == "金"  # 丙火 → 재성 金
    # 왼쪽: 재성 시주 없음 → spouse_family 미성립, 시주 자원=보호(인성).
    assert not left.wealth_in_result_palace
    assert "spouse_family" not in left.wealth_source_leans
    assert "parental" in left.wealth_source_leans
    assert "인성" in left.hour_resource_role
    # 오른쪽: 재성 시주 있음 → spouse_family 성립, 시주 자원=재물, 재성궁 충.
    assert right.wealth_in_result_palace
    assert "spouse_family" in right.wealth_source_leans
    assert "재물" in right.hour_resource_role
    assert right.wealth_palace_clash  # 卯酉충


def test_visible_officer_absent_but_spouse_family_present() -> None:
    """여성 명식 — 관성이 투간/본기로 드러나지 않아도 재성 환경(시댁 재력 잠재)은 잡힌다."""
    right = _profile("06:00")
    assert right.gender == "female" and right.spouse_star == "관성"
    assert right.spouse_star_present is False  # 水 관성 투간·본기 부재(지장간 癸는 제외)
    assert "spouse_family" in right.wealth_source_leans  # 그래도 재성 환경 강


# E3 배우자 인연 결(중립·비낙인) — 도화/홍염·배우자 별 과다/미투출(궁합 자료 ⑤⑥).
def test_charm_and_spouse_star_fields() -> None:
    prof = _profile("12:00")  # 1961-09-30 여성 — 酉월(사정지) → 도화 성립
    assert isinstance(prof.spouse_star_excess, bool)
    assert isinstance(prof.charm_present, bool)
    # 酉(사정지) 포함 → 도화 끌림 경향.
    assert prof.charm_present is True
    # 미투출 플래그는 존재 플래그의 보수적 반대(일관성).
    assert prof.spouse_star_absent == (not prof.spouse_star_present)


def test_neutral_labels_no_stigma() -> None:
    # '바람둥이/과부상' 류 낙인 표현이 flags에 절대 들어가지 않는다(중립 가드).
    for time_ in ("12:00", "06:00"):
        prof = _profile(time_)
        joined = " ".join(prof.flags)
        for banned in ("바람둥이", "과부", "팔자", "사주가 나쁨"):
            assert banned not in joined


# E3 렌더 — marriage_resource_lines가 새 배우자 인연 결 신호를 실제로 출력(chat·report 공용).
def test_lines_render_bond_signals() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    mr = _profile("12:00")  # 酉(도화) 포함
    text = " ".join(marriage_resource_lines(mr))
    assert "배우자 인연 결" in text  # 새 신호 줄이 실제 렌더됨(이전엔 누락)
    assert "도화" in text
    # 낙인 표현 절대 금지(중립 가드).
    for banned in ("바람둥이", "과부"):
        assert banned not in text
