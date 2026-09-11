"""lifetime_scan 엔진(채팅·리포트 공용 승격, 2026-08-13) 단위 테스트.

채팅 동작 불변(별칭·기본 상한 12/3)은 test_lifetime_scan_routing이 계속 검증한다.
여기서는 승격으로 추가된 리포트 전용 축 — 의미 클러스터 상한(per_cluster_cap)과
조립 헬퍼(lifetime_pillars/merge_yearly_luck)의 계약을 고정한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_engines.lifetime_scan import (
    CHAT_TABLE_MAX_YEARS,
    PER_CLUSTER_CAP,
    PER_DECADE_CAP,
    REPORT_TABLE_MAX_YEARS,
    select_lifetime_years,
)


@dataclass
class _Sig:
    type: str = "hap"
    weight: float = 1.0


@dataclass
class _C:
    """EventCandidate 최소 대역 — select가 읽는 필드만."""

    period: str
    score: int
    event_key: str = "CAREER_CHANGE"
    quality: str = "opportunity"
    favorability: float = 0.5
    signals: list = field(default_factory=lambda: [_Sig()])


def test_constants_contract() -> None:
    """채팅 12/3 유지 + 리포트 20/클러스터 2 — docs/10 3-1 상한 계약."""
    assert CHAT_TABLE_MAX_YEARS == 12
    assert PER_DECADE_CAP == 3
    assert REPORT_TABLE_MAX_YEARS == 20
    assert PER_CLUSTER_CAP == 2


def test_cluster_cap_blocks_same_event_domination() -> None:
    """같은 사건×방향×지배신호 클러스터는 상한(2)까지만 — 3번째 연도는 다른 클러스터에 양보."""
    cands = [
        _C("2030", 90), _C("2041", 88), _C("2052", 86),  # 같은 클러스터(CAREER/pos/hap)
        _C("2063", 60, event_key="WEALTH_CHANGE"),
    ]
    picked = select_lifetime_years(cands, 2030, 2080, per_cluster_cap=2)  # type: ignore[arg-type]
    assert 2030 in picked and 2041 in picked
    assert 2052 not in picked  # 클러스터 상한 초과
    assert 2063 in picked  # 다른 클러스터는 점수가 낮아도 선정


def test_cluster_cap_none_keeps_chat_behavior() -> None:
    """per_cluster_cap 미지정(채팅 경로) — 같은 클러스터도 구간 캡 안에서 전부 선정."""
    cands = [_C("2030", 90), _C("2041", 88), _C("2052", 86)]
    picked = select_lifetime_years(cands, 2030, 2080)  # type: ignore[arg-type]
    assert picked == [2030, 2041, 2052]


def test_year_best_candidate_drives_cluster() -> None:
    """클러스터 판정은 그 해 최고점 후보 기준 — 저점 후보의 클러스터가 아니라."""
    cands = [
        _C("2030", 95),
        _C("2030", 50, event_key="WEALTH_CHANGE"),  # 같은 해 저점 후보(무시돼야 함)
        _C("2040", 90),
        _C("2050", 85),
    ]
    picked = select_lifetime_years(cands, 2030, 2080, per_cluster_cap=2)  # type: ignore[arg-type]
    assert picked == [2030, 2040]  # 2050은 CAREER 클러스터 3번째라 제외


def test_lifetime_pillars_and_merge() -> None:
    """대운표 sewoon 수집 + 부족 연도 반환 + 병합 정렬 — 조립 계약(원본 불변)."""
    from types import SimpleNamespace

    def _pl(label: str) -> SimpleNamespace:
        return SimpleNamespace(label=label, ganji="甲子")

    dw = SimpleNamespace(sewoon=[_pl("2031"), _pl("2032")])
    lc = SimpleNamespace(daewoon_table=[dw], yearly_luck=[_pl("2032")])

    class _Result:
        luck_cycles = lc

        def model_copy(self, deep: bool = False) -> _Result:
            new = _Result()
            new.luck_cycles = SimpleNamespace(
                daewoon_table=lc.daewoon_table, yearly_luck=list(lc.yearly_luck)
            )
            return new

    from saju_engines.lifetime_scan import lifetime_pillars, merge_yearly_luck

    from_dw, missing = lifetime_pillars(_Result(), 2030, 2033)  # type: ignore[arg-type]
    assert [p.label for p in from_dw] == ["2031"]  # 2032는 yearly_luck에 이미 존재
    assert missing == [2030, 2033]

    merged = merge_yearly_luck(_Result(), [_pl("2030")])  # type: ignore[arg-type]
    assert [p.label for p in merged.luck_cycles.yearly_luck] == ["2030", "2032"]
    assert [p.label for p in lc.yearly_luck] == ["2032"]  # 원본 불변
