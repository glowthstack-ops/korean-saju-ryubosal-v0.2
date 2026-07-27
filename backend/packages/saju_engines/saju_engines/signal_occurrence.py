"""참여 글자의 결정론적 위치 식별자 (P3 — 2026-07-27 데굴님 확정).

메모리 주소나 배열 인덱스가 아니라 **재생성 가능한 위치**로 신호를 식별한다.
이것이 없으면 원국 월지 亥와 일지 亥가 각각 만드는 두 寅亥合이 하나로 합쳐진다.

범위 계약(2026-07-27 데굴님 확정):
    운 간지 표기('year:丙午.stem:丙', 'daewoon:壬辰.branch:辰')는 **요청 스택 내부의
    위치 식별자**이지 영속 전역 ID가 아니다. 같은 간지는 60년 주기로 반복되므로,
    계산 정체성은 반드시 `source_period`와 결합해 사용해야 한다.

    향후 PrecomputeStore에 영속 저장할 때는 참여 ID에도 실제 연·월·일 또는 대운 시작
    기간을 포함하도록 버전을 올린다(현재 총운 요청 범위에서는 문제 없음).
"""

from __future__ import annotations

from saju_shared_types.enums import Stem

_STEM_CHARS = frozenset(s.value for s in Stem)
_NATAL_POSITION = {
    "natal_year": "year", "natal_month": "month",
    "natal_day": "day", "natal_hour": "hour",
}


def occurrence_id(
    source: str, char: str, period_by_source: dict[str, str] | None = None
) -> str:
    """참여 글자 1개의 위치 식별자.

    Args:
        source: composite InteractionParticipant.source 값.
        char: 참여 글자(한자 1자).
        period_by_source: 운 층위별 기간 라벨(없으면 층위명만 사용).

    Returns:
        'natal.month.branch:亥' / 'daily:2026-07-27.branch:寅' 형식의 식별자.
    """
    kind = "stem" if char in _STEM_CHARS else "branch"
    natal = _NATAL_POSITION.get(source)
    if natal is not None:
        return f"natal.{natal}.{kind}:{char}"
    label = (period_by_source or {}).get(source, "")
    scope = f"{source}:{label}" if label else source
    return f"{scope}.{kind}:{char}"


def canonical_identity_key(occurrence_ids: tuple[str, ...] | None) -> tuple[str, ...]:
    """dedupe용 정규 키 — 참여 순서가 의미 없는 관계를 위해 정렬한다.

    보존용 목록은 엔진 원래 순서를 유지하고, 정렬본은 비교에만 쓴다.
    """
    return tuple(sorted(occurrence_ids or ()))
