"""원국 품질 shadow 지표(사용자 비노출·평가 전용) — C4 결정 ④(2026-10-07 데굴님 승인).

사례집 68쌍 분석(doc/v2_2/CHART_QUALITY_INDEX_C4.md §3)에서 **구조 자체가 길흉을 품은 패턴**은
실제 사건과 같은 방향이었고, 용신 판정에 의존하는 패턴(용신 유력/무력·관인상생)은 신호가 없거나
거꾸로였다. 이 모듈은 전자의 짧은 목록만 부호 합산한다. 목록은 명리 통설의 방향(비겁탈재·충동·
합충병견·수화미제=불리, 상관제살·식신생재=유리)을 전제로 하되 **같은 68쌍에서 확인된 것**이라
가중치는 전부 ±1 로 두고, 사용자 출력·LLM 입력·점수·판정에 연결하지 않는다. Vol.3 사례가 쌓이면
재측정한다(`scripts/casebook_replay.py` 가 명식별로 기록).

절대원칙 1·10: 새 명리 규칙이 아니라 기존 패턴 감지 결과의 부호 집계이며, 점수 산식·사전 항목을
바꾸지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.manse_result import ManseV2Result

from .structure_patterns import detect_structure_patterns

#: 패턴 → 부호. 데이터 유래 후보 목록(shadow). 사용자 노출 금지.
SHADOW_PATTERN_SIGNS: dict[str, int] = {
    "BIGEOP_TALJAE": -1,                 # 비겁탈재 1:12
    "IDENTITY_AUTHORIZATION_STRESS": -1,  # 2:12
    "CHUNGDONG": -1,                      # 충동 7:12
    "HAPCHUNG_BYEONGGYEON": -1,           # 합충병견 7:12
    "SUHWA_MIJE": -1,                     # 수화미제 6:11
    "SANGGWAN_JESAL": +1,                 # 상관제살 11:3
    "SIKSIN_SAENGJAE": +1,                # 식신생재 8:4
}
SHADOW_VERSION = "0.1.0-data_derived_2026-10-07"


@dataclass(frozen=True)
class ChartQualityShadow:
    """부호 합과 근거. `score` 는 정수 합(−5~+2 범위), 비교·로그 전용."""

    score: int
    hits: tuple[str, ...] = field(default_factory=tuple)
    version: str = SHADOW_VERSION

    def as_dict(self) -> dict:
        return {"score": self.score, "hits": list(self.hits), "version": self.version}


def chart_quality_shadow(result: ManseV2Result) -> ChartQualityShadow:
    """감지된 구조 패턴 중 shadow 목록에 든 것만 부호 합산한다(길흉 판정이 아니다)."""
    try:
        detected = detect_structure_patterns(result)
    except Exception:  # noqa: BLE001 — 평가 전용: 감지 실패는 0점·근거 없음으로 둔다
        return ChartQualityShadow(score=0)
    hits = tuple(
        f"{p.pattern_id}:{SHADOW_PATTERN_SIGNS[p.pattern_id]:+d}"
        for p in detected if p.pattern_id in SHADOW_PATTERN_SIGNS
    )
    score = sum(
        SHADOW_PATTERN_SIGNS[p.pattern_id] for p in detected if p.pattern_id in SHADOW_PATTERN_SIGNS
    )
    return ChartQualityShadow(score=score, hits=hits)
