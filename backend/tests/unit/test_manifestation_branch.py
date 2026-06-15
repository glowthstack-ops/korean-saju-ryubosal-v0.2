"""발현 분기(Manifestation Branch) 단위 테스트 — 2026-06-14.

같은 EVENT_CATEGORY 계열에서 같은 시점에 점수화된 형제 사건만 강도순으로 분기 노출하고,
형제가 없으면(계열 내 1종) 분기를 만들지 않음(추측 배제)을 검증한다.
"""

from __future__ import annotations

from saju_engines.manifestation_branch import (
    branch_events,
    branch_line,
    branch_summary,
)
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventPolarity,
    EventType,
)


def _c(event: str, score: int, period: str = "2025-08") -> EventCandidate:
    return EventCandidate(
        event_key=event, event_type=EventType.PROGRESS, period=period, score=score,
        confidence=Confidence.MEDIUM, polarity=EventPolarity.NEUTRAL,
    )


def test_branch_same_family_ranked_by_score() -> None:
    """이직(career_change)·이사(relocation)는 같은 'move' 계열 — 강도순 형제로 묶인다."""
    cands = [_c("career_change", 80), _c("relocation", 64), _c("job_gain", 70)]
    ranked = branch_events("career_change", cands)
    assert ranked == [("career_change", 80), ("relocation", 64)]  # move 계열만, 강도순
    # job_gain(career 계열)은 섞이지 않는다.
    assert all(k != "job_gain" for k, _ in ranked)


def test_branch_none_when_no_family_sibling() -> None:
    """비(非)상호교환 계열에 형제가 1종뿐이면 분기 없음(career는 co-scored 필요)."""
    cands = [_c("job_gain", 80), _c("health_attention", 60)]  # career 계열은 취업 1종뿐
    assert branch_events("job_gain", cands) == []
    assert branch_line("job_gain", cands) is None


def test_branch_move_surfaces_implied_relocation() -> None:
    """move(이직↔이사)는 상호교환 계열 — 이사가 점수화 안 돼도 잠재 형제로 surfacing된다.

    실제 사주 2025-08처럼 relocation이 후보로 점수화되지 않아도, 같은 역마·이동 에너지인
    이직이 점수화되면 이사를 분기로 노출해야 한다(2026-06-14 확인).
    """
    cands = [_c("career_change", 100), _c("job_gain", 90)]  # relocation 미점수화
    ranked = branch_events("career_change", cands)
    assert ("relocation", 0) in ranked  # 잠재 형제로 포함
    assert ranked[0] == ("career_change", 100)  # 점수화된 쪽이 우세
    line = branch_line("career_change", cands)
    assert line is not None and "이사·이동" in line


def test_branch_distinct_keys_keep_max_score() -> None:
    """같은 event_key가 여러 신호로 점수화돼도 distinct·최댓값으로 합산한다."""
    cands = [_c("relocation", 50), _c("relocation", 64), _c("career_change", 80)]
    ranked = branch_events("relocation", cands)
    assert ranked == [("career_change", 80), ("relocation", 64)]


def test_branch_line_mentions_family_and_siblings() -> None:
    """분기 줄에 계열 라벨과 형제 한글명이 강도순으로 포함된다."""
    cands = [_c("career_change", 80), _c("relocation", 64)]
    line = branch_line("career_change", cands)
    assert line is not None
    assert "이동·변동" in line  # move 계열 라벨
    assert "이직·직업 변화" in line and "이사·이동" in line
    assert line.index("이직·직업 변화") < line.index("이사·이동")  # 강도순


def test_branch_money_family_generalizes() -> None:
    """이사 외 일반화 — 재물 변화·횡재는 'money' 계열로 함께 분기된다."""
    cands = [_c("wealth_change", 70), _c("windfall", 55)]
    line = branch_line("wealth_change", cands)
    assert line is not None and "재물" in line and "횡재" in line


def test_branch_summary_covers_all_focal_families() -> None:
    """초점이 여러 사건이면 각 계열의 형제를 모두 surfacing — 1위 단일 초점 누락 방지.

    2025-08처럼 취업(career)·이직(move)이 동점 상위일 때, 어느 쪽이 1위든 이동·변동
    (이직↔이사) 분기가 반드시 포함돼야 한다.
    """
    cands = [
        _c("job_gain", 100), _c("career_change", 100), _c("relocation", 95),
        _c("promotion", 90), _c("wealth_change", 80),
    ]
    # 1위가 취업(career)이어도, 초점에 이직이 있으면 이동·변동(이사) 분기가 포함된다.
    line = branch_summary(["job_gain", "career_change"], cands)
    assert line is not None
    assert "이동·변동" in line and "이사·이동" in line  # 누락되지 않음
    assert "직업·성취" in line  # career 계열도 함께

    # 계열별 형제는 cap개로 제한된다(노이즈 방지).
    capped = branch_summary(["job_gain"], cands, cap=2)
    assert capped is not None and capped.count("/") <= 1  # career 계열 2개까지


def test_branch_summary_none_when_no_sibling() -> None:
    """비상호교환 계열에 co-scored 형제가 없으면 분기 없음(None)."""
    cands = [_c("job_gain", 80), _c("health_attention", 60)]  # career 1종 + 건강(단독)
    assert branch_summary(["job_gain"], cands) is None



def test_interchangeable_generalizes_beyond_move() -> None:
    """이사만 특수처리하지 않음 — money(재물↔횡재)·study(진학↔수료)도 잠재 형제 surfacing."""
    # 재물 변화만 점수화 → 횡재가 잠재 형제로.
    money = branch_line("wealth_change", [_c("wealth_change", 90)])
    assert money is not None and "횡재" in money
    # 진학·자격만 점수화 → 수료·졸업이 잠재 형제로.
    study = branch_line("education_admission", [_c("education_admission", 80)])
    assert study is not None and "수료·졸업" in study
    # career(6종)는 제외 — 취업만 점수화되면 형제 없음(co-scored 필요).
    assert branch_line("job_gain", [_c("job_gain", 80)]) is None
