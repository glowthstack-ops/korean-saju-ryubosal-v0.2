"""표면 부재 오행의 지장간 잠복·유통 완화 — LLM 명식 prefix 배선 (2026-07-03 데굴님 확정).

원리: 겉면 부재 ≠ 완전 부재 — 지장간에 있으면 '숨은 형태로 존재'(잠재·조건부 작동).
유통이 원활하면 신약 판정은 유지하되 완화(적응력·회복력) 프레임으로. 신강 뒤집기 금지.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.context_reducer import build_birth_summary, serialize_chart_prefix
from saju_shared_types.birth_input import BirthInput


def _prefix(birth_date: str, birth_time: str = "09:40") -> tuple[list[str], str]:
    b = BirthInput(
        calendar_type="solar", birth_date=birth_date, birth_time=birth_time,
        birth_place_name="서울", gender="male", reference_date="2026-07-03",
    )
    r = calculate(b)
    summary = build_birth_summary(r)
    lines = serialize_chart_prefix(summary, build_chart_interpretation(r))
    return lines, "\n".join(lines)


def test_case_chart_gets_hidden_latent_line_with_ten_god() -> None:
    """사례 명식(木 표면 부재·亥 중 甲) — 잠복 라인에 출처 지지·단계·십성이 실린다."""
    _, text = _prefix("1980-11-22")
    assert "[표면 부족 오행의 잠재 신호 — 지장간]" in text
    assert "木: 표면에 없음" in text
    assert "亥 중기 甲(정관)" in text
    # 과대평가 방지 가드 — 투출과 동급 금지·잠재/조건부·충 자극=사건화.
    assert "'존재'와 '작동'이 다르다" in text
    assert "잠재·조건부" in text
    assert "사건화·변동 동반" in text


def test_case_chart_gets_flow_note_without_flipping_strength() -> None:
    """신약 + 유통 양호 — 완화 프레임 라인이 실리되 신강 뒤집기 금지 가드 포함."""
    _, text = _prefix("1980-11-22")
    assert "[오행 유통] 유통 양호(상생 고리 5/5)" in text
    assert "신강으로 뒤집지 말 것" in text
    assert "적응력·회복력" in text
    # 신약 판정 자체는 헤더에 그대로 유지된다.
    assert "강약 신약" in text


def test_chart_with_all_elements_visible_has_no_latent_line() -> None:
    """표면에 5오행이 모두 드러난 명식 — 잠복 라인 미부착(불필요 토큰 방지)."""
    # 1984-04-17 10:00 — 표면 오행 구족 여부를 계산해 조건부 검증한다.
    b = BirthInput(
        calendar_type="solar", birth_date="1984-04-17", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date="2026-07-03",
    )
    r = calculate(b)
    assert r.force_analysis is not None
    raw = r.force_analysis.five_elements.raw_visible
    summary = build_birth_summary(r)
    text = "\n".join(serialize_chart_prefix(summary, build_chart_interpretation(r)))
    if all(v > 0 for v in raw.values()):
        assert "[표면 부족 오행의 잠재 신호" not in text
    else:
        # 표면 부재 오행이 있으면 그 오행만 잠복 라인에 오른다(존재 오행 미포함).
        absent = {el for el, v in raw.items() if v == 0}
        for el in ("木", "火", "土", "金", "水"):
            if el not in absent:
                assert f"{el}: 표면에 없음" not in text


def test_prefix_is_deterministic_for_cache() -> None:
    """같은 명식이면 prefix가 바이트 동일(고정 프롬프트 캐시 조건)."""
    _, a = _prefix("1980-11-22")
    _, b = _prefix("1980-11-22")
    assert a == b
