"""만세력 엔진 출력 → 정규화 ManseChart 어댑터 (v2.2 Phase 0 T0.3).

만세력 엔진(`ManseV2Result`)은 표시·분석에 충분한 풍부한 출력을 내보낸다. 신규 엔진군은
그중 안정적인 최소 계약(`ManseChart`, docs/02 E0)만 소비한다. 본 어댑터는 만세력 엔진을
일절 수정하지 않고 결과를 1:1로 투영한다(절대 원칙: 기존 엔진 수정 금지).
"""

from __future__ import annotations

from saju_shared_types.engine_io import (
    BirthMeta,
    ChartPillar,
    DaewoonPeriod,
    FourPillarsChart,
    ManseChart,
)
from saju_shared_types.luck import DaewoonItem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.pillars import Pillar
from saju_shared_types.sinsal import SinsalAnalysis

_GENDER_MAP = {"male": "M", "female": "F", "unknown": "U"}


def _shinsal_by_position(sinsal: SinsalAnalysis | None) -> dict[str, list[str]]:
    """신살 full_list를 자리(year/month/day/hour)별 이름 목록으로 묶는다."""
    out: dict[str, list[str]] = {"year": [], "month": [], "day": [], "hour": []}
    if sinsal is None:
        return out
    for item in sinsal.full_list:
        bucket = out.setdefault(item.position, [])
        if item.name not in bucket:
            bucket.append(item.name)
    return out


def _to_chart_pillar(pillar: Pillar, shinsal_names: list[str]) -> ChartPillar:
    """엔진 Pillar → 정규화 ChartPillar (신규 엔진 소비용 최소형)."""
    return ChartPillar(
        stem=pillar.stem,
        branch=pillar.branch,
        hidden_stems=[h.stem for h in pillar.hidden_stems],
        ten_god=pillar.stem_ten_god,
        twelve_stage=pillar.twelve_unseong,
        shinsal=shinsal_names,
    )


def _to_daewoon_period(item: DaewoonItem) -> DaewoonPeriod:
    """엔진 DaewoonItem → 정규화 DaewoonPeriod. period는 '시작연도~종료연도' 라벨."""
    start_year = item.approx_start_date.year
    end_year = item.approx_end_date.year
    return DaewoonPeriod(
        index=item.index,
        start_age=item.start_age,
        period=f"{start_year}~{end_year}",
        stem=item.stem,
        branch=item.branch,
        ganji=item.ganji,
        stem_ten_god=item.stem_ten_god,
        branch_ten_god=item.branch_ten_god,
    )


def _birth_datetime(result: ManseV2Result) -> str:
    """input_summary에서 출생 민간력 일시 ISO 문자열을 만든다(시각 미상이면 날짜만)."""
    summary = result.input_summary
    birth_date = str(summary.get("birth_date", ""))
    birth_time = summary.get("birth_time")
    if summary.get("birth_time_unknown") or not birth_time:
        return birth_date
    return f"{birth_date}T{birth_time}"


def adapt_manse_chart(result: ManseV2Result) -> ManseChart:
    """`ManseV2Result`를 신규 엔진 입력 계약 `ManseChart`로 변환한다.

    쌍둥이 시주 조정(docs/11 2-2)은 미구현이므로 chart_variant='original'/twin_shift=0
    고정으로 내보낸다(절대 원칙 11: 미구현 기능으로 차단·오류 금지).

    Args:
        result: 만세력 엔진의 전체 결과. pillars가 채워져 있어야 한다.

    Returns:
        신규 엔진이 소비하는 정규화 차트.

    Raises:
        ValueError: 원국(pillars)이 비어 있는 경우(계산 실패 결과).
    """
    if result.pillars is None:
        raise ValueError("ManseV2Result.pillars is required to adapt a ManseChart")

    pillars = result.pillars
    sinsal = result.traditional_extras.sinsal if result.traditional_extras else None
    shinsal_map = _shinsal_by_position(sinsal)

    chart = FourPillarsChart(
        year=_to_chart_pillar(pillars.year, shinsal_map["year"]),
        month=_to_chart_pillar(pillars.month, shinsal_map["month"]),
        day=_to_chart_pillar(pillars.day, shinsal_map["day"]),
        hour=(
            _to_chart_pillar(pillars.hour, shinsal_map["hour"])
            if pillars.hour is not None
            else None
        ),
    )

    gender_raw = result.input_summary.get("gender")
    gender = _GENDER_MAP.get(str(gender_raw), "U")

    daewoon_list = (
        [_to_daewoon_period(d) for d in result.luck_cycles.daewoon_table]
        if result.luck_cycles is not None
        else []
    )

    return ManseChart(
        chart_id=result.chart_id,
        birth_info=BirthMeta(
            datetime=_birth_datetime(result),
            calendar_type=str(result.input_summary.get("calendar_type", "solar")),
            gender=gender,
            birth_time_unknown=bool(result.input_summary.get("birth_time_unknown")),
        ),
        chart=chart,
        day_master=pillars.day_master,
        void_branches=list(pillars.gongmang_branches),
        daewoon_list=daewoon_list,
    )
