"""A′ — 시점 그룹화 기반 대표 선정 (2026-07-30 데굴님 지적 교정).

결함: 사건 행을 top-8 로 **먼저 자른 뒤** 시점을 보는 구조라 같은 달이 슬롯을
독점했다(실측: career top-8 의 고유 시점 4개, 2027-02 가 5슬롯).

교정 계약 — 여섯 조건을 여기서 고정한다.

    ① 그룹화는 top-K 절단 **전에** 수행한다
    ② 같은 기간이 출력 슬롯을 둘 이상 차지하지 않는다
    ③ 대표는 기존 `_CANDIDATE_RANK_KEY` 1위다(새 점수·타이브레이크 금지)
    ④ 고유 기간이 K 보다 적으면 중복으로 억지 충원하지 않는다
    ⑤ global 과 domain 경로가 같은 헬퍼를 쓴다
    ⑥ 구성원은 보존하고 프롬프트 전달 수만 제한한다
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402


@dataclass
class _Cand:
    """순위 키가 읽는 필드만 갖춘 최소 후보."""

    period: str
    event_key: str
    score: int
    life_fit: float = 0.0
    personal_match: float = 0.0


def _ranked(cands: list[_Cand]) -> list[_Cand]:
    """기존 순위 키로 정렬 — 헬퍼 입력 계약(정렬된 풀)."""
    return sorted(cands, key=R._CANDIDATE_RANK_KEY)


# ── ① 그룹화가 절단보다 먼저 ─────────────────────────────────────────────


def test_grouping_happens_before_top_k_truncation() -> None:
    """같은 달이 앞자리를 채워도 뒤쪽 시점이 살아남아야 한다.

    절단이 먼저면 2027-02 다섯 건이 슬롯을 다 먹고 고유 시점은 1개가 된다.
    """
    pool = _ranked([
        *[_Cand("2027-02", f"e{i}", 90 - i) for i in range(5)],
        _Cand("2028-02", "x1", 80),
        _Cand("2029-02", "x2", 79),
        _Cand("2030-02", "x3", 78),
    ])
    reps, groups = R._period_representatives(pool, 3, R._CANDIDATE_RANK_KEY)
    assert [c.period for c in reps] == ["2027-02", "2028-02", "2029-02"]
    assert len(groups) == 3


# ── ② 한 기간이 슬롯을 둘 이상 차지하지 않음 ─────────────────────────────


def test_one_period_occupies_at_most_one_slot() -> None:
    pool = _ranked([
        _Cand("2027-02", "a", 90), _Cand("2027-02", "b", 89),
        _Cand("2027-03", "c", 88), _Cand("2027-03", "d", 87),
    ])
    reps, _ = R._period_representatives(pool, 4, R._CANDIDATE_RANK_KEY)
    periods = [c.period for c in reps]
    assert len(periods) == len(set(periods))


# ── ③ 대표는 기존 순위 1위 ───────────────────────────────────────────────


def test_representative_is_the_existing_rank_winner_not_insertion_order() -> None:
    """입력 배열 순서에 의존해 마지막 원소가 남는 사고를 막는다."""
    pool = [
        _Cand("2027-02", "weak", 10),
        _Cand("2027-02", "strong", 99),
        _Cand("2027-02", "mid", 50),
    ]
    reps, groups = R._period_representatives(pool, 1, R._CANDIDATE_RANK_KEY)
    assert reps[0].event_key == "strong"
    assert len(groups["2027-02"]) == 3     # 나머지는 삭제되지 않는다


def test_representative_uses_life_fit_before_score() -> None:
    """순위 키는 현실적합 > 과거유사 > 점수. 점수만 보면 안 된다."""
    pool = [
        _Cand("2027-02", "fit", 10, life_fit=9.0),
        _Cand("2027-02", "high_score", 99, life_fit=0.0),
    ]
    reps, _ = R._period_representatives(pool, 1, R._CANDIDATE_RANK_KEY)
    assert reps[0].event_key == "fit"


# ── ④ 고유 기간 부족 시 억지 충원 금지 ───────────────────────────────────


def test_short_pool_is_not_padded_with_duplicate_periods() -> None:
    pool = _ranked([
        _Cand("2027-02", "a", 90), _Cand("2027-02", "b", 89),
        _Cand("2027-03", "c", 88),
    ])
    reps, _ = R._period_representatives(pool, 8, R._CANDIDATE_RANK_KEY)
    assert len(reps) == 2                  # 8 로 부풀리지 않는다
    assert [c.period for c in reps] == ["2027-02", "2027-03"]


def test_empty_pool_yields_empty_result() -> None:
    reps, groups = R._period_representatives([], 8, R._CANDIDATE_RANK_KEY)
    assert reps == [] and groups == {}


# ── ⑤ global·domain 경로가 같은 헬퍼 ─────────────────────────────────────


def test_both_paths_share_one_grouping_implementation() -> None:
    """도메인 경로가 예전처럼 `score` 로만 병합하면 두 경로 판정이 갈린다."""
    src = inspect.getsource(R._ReportData.domain_candidates)
    assert "_period_representatives" in src
    assert "_CANDIDATE_RANK_KEY" in src
    # 예전 구현의 흔적(직접 병합)이 남아 있으면 안 된다.
    assert "merged[c.period] = c" not in src
    init = inspect.getsource(R._ReportData.__init__)
    assert "_period_representatives" in init


# ── ⑥ 구성원 보존 + 전달만 제한 ──────────────────────────────────────────


def test_members_are_preserved_while_prompt_delivery_is_capped() -> None:
    """저장은 전체, 전달은 시점당 2건 — 둘을 섞으면 토큰이 새거나 근거가 사라진다."""
    assert R._PROMPT_COMPANIONS_PER_PERIOD == 2
    pool = _ranked([
        _Cand("2027-02", "rep", 99),
        *[_Cand("2027-02", f"co{i}", 90 - i) for i in range(5)],
    ])
    reps, groups = R._period_representatives(pool, 1, R._CANDIDATE_RANK_KEY)
    assert len(groups["2027-02"]) == 6     # 보존은 전부
    assert reps[0].event_key == "rep"


def test_co_signal_lines_dedupe_by_event_key_and_respect_the_cap() -> None:
    """같은 event_key 중복 후보를 다시 나열하지 않고 상한을 지킨다."""
    data = R._ReportData.__new__(R._ReportData)   # 엔진 실행 없이 렌더링만 시험
    rep = _Cand("2027-02", "rep", 99)
    data.period_groups = {
        "2027-02": [
            rep,
            _Cand("2027-02", "dup", 90),
            _Cand("2027-02", "dup", 89),      # 같은 키 — 한 번만
            _Cand("2027-02", "other", 88),
            _Cand("2027-02", "third", 87),    # 상한 초과 — 전달 제외
        ]
    }
    data._domain_period_groups = {}
    lines = data._co_signal_lines([rep])
    assert len(lines) == 1
    assert lines[0].startswith("2027-02: ")
    names = lines[0].split(": ", 1)[1].split(", ")
    assert names == ["dup", "other"]
    assert "third" not in names
    assert "rep" not in names


# ── 다중 view 병합 후 companion 재압축 ───────────────────────────────────
#
# view 내부에서는 상한·중복 제거를 지키지만, 같은 달을 가리키는 두 view 를 이어
# 붙이면 2+2 가 되고 같은 event_key 가 겹친다(실측: 상한초과 1 · 중복 1).


def _view(view_id: str, groups) -> R.PeriodView:
    keys = {str(c.event_key) for g in groups for c in (g.representative, *g.members)}
    return R.PeriodView(
        view_id=view_id, representatives=tuple(g.representative for g in groups),
        groups=tuple(groups), qualifying_event_keys=frozenset(keys),
        qualifying_families=frozenset(), polarity_filter=None,
    )


def test_multi_view_merge_recompresses_companions() -> None:
    """병합 전 4건·대표 중복 1·키 중복 1쌍 → 표시 2건, 감사에는 전부 보존."""
    rep_a = _Cand("2027-02", "career_change", 90, life_fit=9.0)
    rep_b = _Cand("2027-02", "contract_document", 80, life_fit=8.0)
    # companion 4건: 대표와 같은 키 1건 + 서로 같은 키 1쌍 + 고유 2건
    dup_of_rep = _Cand("2027-02", "career_change", 70, life_fit=7.0)
    pair_1 = _Cand("2027-02", "promotion", 69, life_fit=6.9)
    pair_2 = _Cand("2027-02", "promotion", 68, life_fit=6.8)
    unique = _Cand("2027-02", "job_gain", 60, life_fit=6.0)
    ga = R.PeriodGroup("2027-02", rep_a, (rep_a, dup_of_rep, pair_1),
                       (dup_of_rep, pair_1))
    gb = R.PeriodGroup("2027-02", rep_b, (rep_b, pair_2, unique),
                       (pair_2, unique))
    clusters = R._section_period_clusters((_view("career_transition", [ga]),
                                           _view("contract_document", [gb])))
    assert len(clusters) == 1                      # 같은 기간 1회 표시
    cl = clusters[0]
    assert cl.source_view_ids == ("career_transition", "contract_document")
    assert len(cl.representatives) == 2            # 각 view 대표 보존
    # 표시 companion — 상한 2, 대표 키 중복 없음, companion 키 중복 없음
    assert len(cl.companions) == R._PROMPT_COMPANIONS_PER_PERIOD
    keys = [str(c.event_key) for c in cl.companions]
    assert keys == ["promotion", "job_gain"]       # rank 오름차순(음수 키) 유지
    assert "career_change" not in keys             # 대표와 같은 키는 제외
    assert len(keys) == len(set(keys))
    # 감사에는 병합 전 전체가 남는다(압축이 감사 목록을 줄이지 않는다).
    assert len(cl.audit_companions) == 4
    assert cl.companions is not cl.audit_companions
    assert set(map(id, cl.companions)) < set(map(id, cl.audit_companions))


def test_rank_key_is_ascending_because_it_returns_negated_values() -> None:
    """`_CANDIDATE_RANK_KEY` 는 음수를 반환한다 — `reverse=True` 를 쓰면 최하위가 앞에 온다."""
    strong = _Cand("2027-02", "a", 99, life_fit=9.0)
    weak = _Cand("2027-02", "b", 10, life_fit=0.0)
    assert R._CANDIDATE_RANK_KEY(strong) < R._CANDIDATE_RANK_KEY(weak)
    assert sorted([weak, strong], key=R._CANDIDATE_RANK_KEY)[0] is strong
    picked = R._compress_cluster_companions((), (weak, strong))
    assert picked[0] is strong                     # 상위가 먼저 선택된다
