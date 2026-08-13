"""전 생애(연 단위) 이벤트 스캔 — 채팅·리포트 공용 엔진 (docs/10 3-1).

채팅 lifetime scan(2026-08-07 P0 승인)의 조립·선별 로직을 엔진으로 승격해
총운 리포트 F-14(생애 변곡점 연표, 2026-08-13 생애 개편)와 공유한다.

원칙:
- 세운 간지·운품질은 이미 계산된 대운표의 sewoon(전 생애치)을 재사용한다
  (절대원칙 9 — 즉석 재계산 금지). 첫 대운 시작 전 유년만 호출자가 보충한다
  (`luck_years`는 API 계층 소유 — 엔진은 순수 함수를 유지한다).
- 선별은 연도 최고점순 + 10년 구간당 상한(균등 배분 아님 — 상한 안에서는 점수순
  그대로, 무신호 연도 강제 충원 금지). 리포트는 의미 클러스터 상한을 추가해 같은
  사건×방향×지배신호가 연표를 도배하지 않게 한다(총운 다변화와 동일 축).
"""

from __future__ import annotations

from saju_shared_types.events import EventCandidate
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

from .context_reducer import overview_cluster_key

# 채팅 표 상한(2026-08-07 승인안 — 동작 불변 이관).
CHAT_TABLE_MAX_YEARS = 12
# 리포트 생애 연표 상한(docs/10 3-1) — 출생~90세 창은 채팅(단계 창)보다 넓어 총 20.
REPORT_TABLE_MAX_YEARS = 20
# 10년 구간당 상한 — 특정 대운 구간 쏠림 방지(채팅·리포트 공통).
PER_DECADE_CAP = 3
# 같은 의미 클러스터(사건×방향×지배신호)의 연표 점유 상한(리포트 전용, docs/10 3-1).
PER_CLUSTER_CAP = 2


def lifetime_pillars(
    result: ManseV2Result, lo_year: int, hi_year: int
) -> tuple[list[LuckPillar], list[int]]:
    """창 내 세운 기둥을 대운표 sewoon에서 수집하고, 표에 없는 연도를 함께 반환한다.

    이미 `yearly_luck`에 있는 연도는 제외한다(중복 병합 방지). 반환된 부족 연도
    (첫 대운 시작 전 유년 등)는 호출자가 `luck_years`로 보충한다.

    Args:
        result: 만세력 결과(luck_cycles.daewoon_table 존재 전제 — 없으면 빈 결과).
        lo_year: 창 시작 연도. hi_year: 창 끝 연도.

    Returns:
        (대운표에서 수집한 세운 기둥, 아직 없는 연도 목록) — 둘 다 창 내 한정.
    """
    lc = result.luck_cycles
    if lc is None or not lc.daewoon_table:
        return [], list(range(lo_year, hi_year + 1))
    sewoon_by_year = {pl.label: pl for dw in lc.daewoon_table for pl in dw.sewoon}
    have = {pl.label for pl in lc.yearly_luck}
    from_dw = [
        sewoon_by_year[str(y)]
        for y in range(lo_year, hi_year + 1)
        if str(y) in sewoon_by_year and str(y) not in have
    ]
    missing = [
        y
        for y in range(lo_year, hi_year + 1)
        if str(y) not in sewoon_by_year and str(y) not in have
    ]
    return from_dw, missing


def merge_yearly_luck(result: ManseV2Result, extra: list[LuckPillar]) -> ManseV2Result:
    """yearly_luck에 extra 기둥을 병합한 깊은 복사본을 만든다(원본 불변, 라벨 정렬).

    Args:
        result: 만세력 결과. extra: 추가할 세운 기둥(창 밖·중복 없음 전제).

    Returns:
        병합된 복사본. luck_cycles가 없으면 복사본 그대로.
    """
    merged = result.model_copy(deep=True)
    if merged.luck_cycles is None:
        return merged
    merged.luck_cycles.yearly_luck = sorted(
        [*merged.luck_cycles.yearly_luck, *extra], key=lambda pl: pl.label
    )
    return merged


def select_lifetime_years(
    candidates: list[EventCandidate],
    lo_year: int,
    hi_year: int,
    max_rows: int = CHAT_TABLE_MAX_YEARS,
    per_decade_cap: int = PER_DECADE_CAP,
    per_cluster_cap: int | None = None,
) -> list[int]:
    """전 생애/단계 창의 연 후보에서 표에 올릴 연도를 선별한다.

    연도별 최고 후보 점수 순으로 고르되 10년 구간당 상한을 둬 한 대운 구간이 표를
    독점하지 않게 한다. 후보가 존재하는 연도만 오른다(품질 게이트 — 표 밖 연도를
    '신호 없음'으로 단정하는 서술은 디렉티브에서 별도 차단).

    Args:
        candidates: 창 내 연 단위 이벤트 후보(의도 필터 통과분).
        lo_year: 창 시작 연도. hi_year: 창 끝 연도.
        max_rows: 표 연도 수 상한. per_decade_cap: 10년 구간당 상한.
        per_cluster_cap: 같은 의미 클러스터(사건×방향×지배신호)의 상한.
            None이면 미적용(채팅 기존 동작 불변 — 리포트만 PER_CLUSTER_CAP 사용).

    Returns:
        선별된 연도 목록(오름차순).
    """
    best: dict[int, EventCandidate] = {}
    for c in candidates:
        if len(c.period) == 4:
            y = int(c.period)
            if lo_year <= y <= hi_year and (y not in best or c.score > best[y].score):
                best[y] = c
    picked: list[int] = []
    per_dec: dict[int, int] = {}
    per_cluster: dict[tuple[str, str, str], int] = {}
    for y, cand in sorted(best.items(), key=lambda kv: (-kv[1].score, kv[0])):
        dec = (y - lo_year) // 10
        if per_dec.get(dec, 0) >= per_decade_cap:
            continue
        if per_cluster_cap is not None:
            key = overview_cluster_key(cand)
            if per_cluster.get(key, 0) >= per_cluster_cap:
                continue
            per_cluster[key] = per_cluster.get(key, 0) + 1
        picked.append(y)
        per_dec[dec] = per_dec.get(dec, 0) + 1
        if len(picked) >= max_rows:
            break
    return sorted(picked)
