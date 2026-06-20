"""ExamOutcomeModifier 검증 (이벤트 엔진 Phase 6b).

시험·합격·취업의 결과 길흉(favorability)을 십성 구조 합·불 패턴으로 보정하되,
사건 종류·표시 점수는 바꾸지 않음(favorability 채널 fav_adj 전용)을 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.exam_outcome_modifier import ExamOutcomeModifier
from saju_shared_types.event_engine import EventCandidateV2, TenGod

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> ExamOutcomeModifier:
    return ExamOutcomeModifier(_DICTS)


def _cand(event: str, score: int = 60) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score)


def test_gwaninsangsaeng_boosts_favorability() -> None:
    # 관인상생(정관+정인) → education_admission favorability 상승, 점수·종류 불변.
    e = _eng()
    gods = {TenGod.ZHENGGUAN, TenGod.ZHENGYIN}
    out = e.apply([_cand("education_admission", 60)], gods)
    c = out[0]
    assert c.event_key.value == "education_admission"
    assert c.score == 60  # 점수(활성) 불변
    assert c.contributions["fav_adj"] > 0
    assert "EXAM_PASS_관인상생" in c.reason_codes


def test_sanggwangyeongwan_penalizes_favorability() -> None:
    # 상관견관(상관+정관) → 불합격 위험: favorability 하락.
    e = _eng()
    gods = {TenGod.SHANGGUAN, TenGod.ZHENGGUAN}
    out = e.apply([_cand("education_admission", 60)], gods)
    c = out[0]
    assert c.score == 60
    assert c.contributions["fav_adj"] < 0
    assert "EXAM_FAIL_상관견관" in c.reason_codes


def test_non_target_event_untouched() -> None:
    # 시험·취업 대상이 아닌 이벤트는 보정하지 않는다.
    e = _eng()
    gods = {TenGod.SHANGGUAN, TenGod.ZHENGGUAN}
    out = e.apply([_cand("relocation", 60)], gods)
    assert "fav_adj" not in out[0].contributions


def test_no_pattern_no_change() -> None:
    # 패턴 쌍이 없으면 변화 없음.
    e = _eng()
    out = e.apply([_cand("job_gain", 60)], {TenGod.BIJIAN})
    assert "fav_adj" not in out[0].contributions


def test_cap_limits_accumulation() -> None:
    # 합·불 패턴이 여럿 겹쳐도 fav_adj는 cap(±0.5) 내로 제한.
    e = _eng()
    gods = {
        TenGod.ZHENGGUAN, TenGod.ZHENGYIN, TenGod.QISHA,  # 관인상생 + 살인상생
        TenGod.ZHENGCAI,  # 재생관 등 추가 매칭
    }
    out = e.apply([_cand("job_gain", 60)], gods)
    assert out[0].contributions["fav_adj"] <= 0.5
