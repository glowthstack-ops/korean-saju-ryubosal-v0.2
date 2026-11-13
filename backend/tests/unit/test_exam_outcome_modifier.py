"""ExamOutcomeModifier 검증 (이벤트 엔진 Phase 6b).

시험·합격·취업 후보에 합격 기류(합·불 패턴의 양의 합)를 favorability 로 반영하되,
사건 종류·표시 점수는 바꾸지 않음(favorability 채널 fav_adj 전용)을 확인한다.
합격 기류는 '있다'만 말한다(2026-11-11 데굴님) — 합이 0 이하이면 후보를 그대로 둔다.
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


def test_fail_pattern_alone_leaves_candidate_untouched() -> None:
    # 상관견관(상관+정관)만 성립 — 합격 기류가 없을 뿐 불합격 위험이 아니다: 감점·사유 없음.
    e = _eng()
    gods = {TenGod.SHANGGUAN, TenGod.ZHENGGUAN}
    cand = _cand("education_admission", 60)
    out = e.apply([cand], gods)
    assert out[0] is cand
    assert "fav_adj" not in out[0].contributions
    assert not [r for r in out[0].reason_codes if r.startswith("EXAM_")]


def test_fail_pattern_only_offsets_pass_pattern() -> None:
    # 관인상생(+0.3)·상관패인(+0.2)에 상관견관(−0.3)이 겹친다 — 합 +0.2 만큼만 합격 기류로
    # 가산하고, 사유는 합격 패턴만 붙는다(불합격 패턴은 상쇄에만 쓰인다).
    e = _eng()
    gods = {TenGod.ZHENGGUAN, TenGod.ZHENGYIN, TenGod.SHANGGUAN}
    out = e.apply([_cand("job_gain", 60)], gods)
    c = out[0]
    assert abs(c.contributions["fav_adj"] - 0.2) < 1e-9
    assert {r for r in c.reason_codes if r.startswith("EXAM_")} == {
        "EXAM_PASS_관인상생", "EXAM_PASS_상관패인",
    }
    # 재극인(편재+정인, −0.25)까지 겹쳐 합이 −0.05 가 되면 후보는 그대로다(감점 없음).
    gods_neg = {TenGod.ZHENGGUAN, TenGod.ZHENGYIN, TenGod.SHANGGUAN, TenGod.PIANCAI, TenGod.JIECAI}
    cand = _cand("job_gain", 60)
    assert e.apply([cand], gods_neg)[0] is cand


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
