"""2026-10-26 연애운 서술층 실답 감수 후속 교정 회귀.

① 결혼 시기·형태 프레임: 늦춤 신호가 없으면 **미성립 줄**을 낸다(종전엔 줄 자체가 빠져 LLM이
'늦게 하는 게 좋은 사주?' 질문 프레임에 동조). ② 女 무재 '재성 미투출' 문장은 인연 결 줄에만
본문이 있고 프레임 줄은 참조로 축약(중복 제거). ③ [혼기 경향] 축 라벨은 한글 기둥명.
④ 방위 지침 ⑩ — 블록에 없는 방향 추가 금지. ⑤ 토픽 요약 '○○ 중심'은 상위 사건 키 복수.
⑥ 시드 미등록 출생지 + 좌표 없음 → chat 422(종전 500).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import saju_engines.structural_context as sc
from saju_api.location import LocationResolveError, resolve
from saju_api.main import app
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import build_birth_summary
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.sinsal_direction import SINSAL_DIRECTION_INSTRUCTION
from saju_engines.topic_builder import _lead_event_keys
from saju_shared_types.birth_input import BirthInput

_FRAME = "결혼 시기·형태 프레임"


def _mr(y: int, m: int, d: int, hm: str, gender: str, place: str = "서울"):
    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name=place, gender=gender,
    ))
    return r, analyze_marriage_resource(r, build_birth_summary(r).useful_gods, age=None)


def test_frame_absent_line_when_no_late_signal() -> None:
    """남 1985-08-20 14:00(실답 명식): 늦춤 신호 0 → 미성립 줄 필수·'늦게가 좋다' 단정 차단."""
    _, mr = _mr(1985, 8, 20, "14:00", "male", place="부산")
    assert mr.late_marriage_notes == []  # 반례 전제 — 이 명식엔 늦춤 신호가 없다
    frame = [ln for ln in sc.marriage_resource_lines(mr) if ln.startswith(_FRAME)]
    assert len(frame) == 1
    assert "늦춤 쪽 구조 신호" in frame[0] and "없음" in frame[0]
    assert "단정하지 말고" in frame[0]


def test_frame_present_line_has_no_absent_marker_and_no_duplicate_wealth_text() -> None:
    """女 1990-05-15 10:30: 무재·비겁 과다 → 신호 줄만(미성립 문구 없음), 무재 본문은 한 줄에만."""
    _, mr = _mr(1990, 5, 15, "10:30", "female")
    assert mr.wealth_absent and mr.late_marriage_notes
    lines = sc.marriage_resource_lines(mr)
    frame = [ln for ln in lines if ln.startswith(_FRAME)]
    assert len(frame) == 1 and "늦춤 쪽 구조 신호" not in frame[0]
    assert "재성 미투출(인연 결 줄 참조)" in frame[0]
    # 본문 문장("붙잡아 유지하려는 욕구")은 인연 결 줄 한 곳에만.
    assert sum("붙잡아 유지하려는 욕구" in ln for ln in lines) == 1


def test_age_prior_positions_are_korean(monkeypatch) -> None:
    """[혼기 경향] 축 라벨 year·month·hour → 연주·월주·시주."""
    monkeypatch.setattr(sc, "active_marriage_aux", lambda *a, **k: {"mt6_age_prior": True})
    r, _ = _mr(1990, 5, 15, "10:30", "female")
    text = " ".join(sc.marriage_age_prior_lines(r))
    assert "연주" in text or "월주" in text or "시주" in text
    for en in ("year", "month", "day", "hour"):
        assert en not in text


def test_direction_instruction_forbids_unlisted_direction() -> None:
    assert "⑩" in SINSAL_DIRECTION_INSTRUCTION
    assert "블록에 없는 방향" in SINSAL_DIRECTION_INSTRUCTION


class _Sig:
    def __init__(self, key: str | None, w: float) -> None:
        self.event_key, self.weight = key, w


def test_lead_event_keys_distinct_top3_by_weight() -> None:
    sigs = [_Sig("a", 0.2), _Sig("b", 0.5), _Sig("a", 0.4), _Sig("c", 0.3), _Sig("d", 0.1)]
    assert _lead_event_keys(sigs, "연애") == "b·a·c"
    assert _lead_event_keys([_Sig(None, 0.3)], "연애") == "연애"
    assert _lead_event_keys(sigs, "연애", limit=1) == "b"


def test_unseeded_place_raises_typed_error() -> None:
    with pytest.raises(LocationResolveError):
        resolve("대구", None, None, None)


def test_chat_unseeded_place_returns_422_not_500() -> None:
    client = TestClient(app)
    res = client.post("/api/v2/chat", json={
        "birth": {"birth_date": "1996-02-03", "birth_time": "22:10",
                  "birth_place_name": "대구", "gender": "female"},
        "question": "올해 연애운", "dry_run": True,
    })
    assert res.status_code == 422, res.text
    assert "대구" in res.json()["detail"]
