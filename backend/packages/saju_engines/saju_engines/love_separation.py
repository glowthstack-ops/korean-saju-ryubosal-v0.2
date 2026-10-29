"""남녀 이별운 강의 번역층 — 원국 글자 × 운 글자 관계 변동 시드·서술(2026-10-29 데굴님 결정).

대조 문서: doc/v2_2/EXTERNAL_TEXT_GAP_LOVE_SEPARATION.md. 강의의 네 축:
  ① 여성 — 원국 관성(배우자성)이 매우 약한데 운에서 식신·상관이 와 관성을 극한다.
  ② 남성 — 일지(배우자궁) 본기가 정재인데 운에서 겁재가 와 정재를 극한다(배우자궁 쟁재).
  ③ 여성 — 원국에 정인이 없거나(무인성) 지장간에만 있는데 운에서 정인이 온다(애정 욕구 각성).
  ④ 공통 — 원국에 정재가 있는데 운에서 비견·겁재가 온다(쟁재 — 겁재 > 비견).

점수층은 연애 실험 플래그(`love_timing.LOVE_EXPERIMENT_KEYS`, 기본 OFF)이며 85사례·원장
적중률로 ON/OFF 를 정한다. 겁재 유입의 천간/지지 가중은 강의끼리도 다르므로(이별 강의: 지지가
더 강함, 이직 강의: 천간 기준) **케이스로 판단**한다(데굴님 결정 ①) —
`separation_peer_branch_weight` 가 켜지면 ②④ 의 지지 유입이 천간보다 높은 기준점을 받는다.

서술층(관계 질문 전용 — 데굴님 결정 ③)은 문구 사전
`interpretations/love_separation_lecture_text.json` 에서 고르기만 한다. 무인성은 원국 분류
해설이지 단정 판정 대상이 아니다(데굴님 결정 ②) — 다만
시주 미상 명식은 시주에 정인이 있을 수 있어 분류하지 않는다(데이터 불완전, HOUR_UNKNOWN 규칙 3).
규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGod,
)
from saju_shared_types.manse_result import ManseV2Result

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

#: 실험 키(love_timing.LOVE_EXPERIMENT_KEYS 에 등재) — 규칙별 개별 측정.
SEP_OFFICER_OUTPUT = "separation_officer_output"
SEP_PALACE_JIECAI = "separation_palace_jiecai"
SEP_RESOURCE_INFLOW = "separation_resource_inflow"
SEP_ZHENGCAI_PEER = "separation_zhengcai_peer"
SEP_PEER_BRANCH_WEIGHT = "separation_peer_branch_weight"  # ②④ 지지 가중 변형(케이스 판단용)
SEPARATION_KEYS: tuple[str, ...] = (
    SEP_OFFICER_OUTPUT, SEP_PALACE_JIECAI, SEP_RESOURCE_INFLOW, SEP_ZHENGCAI_PEER,
    SEP_PEER_BRANCH_WEIGHT,
)

#: 관성 '매우 약함' — 십성군 분포 임계(%). 구조 패턴 '존재' 임계
#: (pattern_transit._MIN_PRESENCE)와 같다.
OFFICER_WEAK_PCT = 10.0

#: 기준점(relationship_change) — 기존 관계 조합 규칙(SPEC_JIECAI_ZHENGCAI 49·
#: SPEC_BIJIAN_ZHENGCAI 41)과 같은 급. 천간/지지는 (천간, 지지) 순. 초기 설계값 — 측정으로 ON/OFF.
OFFICER_OUTPUT_BASE = (44, 40)
RESOURCE_INFLOW_BASE = (36, 32)
PALACE_JIECAI_BASE = {"stem": (52, 46), "branch": (46, 52)}
ZHENGCAI_PEER_BASE = {
    "stem": {TenGod.JIECAI: (49, 44), TenGod.BIJIAN: (41, 37)},
    "branch": {TenGod.JIECAI: (44, 49), TenGod.BIJIAN: (37, 41)},
}
_OUTPUT = (TenGod.SHISHEN, TenGod.SHANGGUAN)


@dataclass(frozen=True)
class SeparationNatal:
    """원국 쪽 조건(엔진 산출값만)."""

    gender: str
    hour_known: bool
    officer_pct: float
    zhengyin_state: str  # 'present' | 'missing' | 'hidden_only' | 'unknown'(시주 미상)
    day_palace_zhengcai: bool
    natal_zhengcai: bool  # 천간(연·월·시) 또는 지지 본기에 정재

    @property
    def officer_weak(self) -> bool:
        return self.officer_pct < OFFICER_WEAK_PCT

    @property
    def resource_lacking(self) -> bool:
        return self.zhengyin_state in ("missing", "hidden_only")


def separation_natal(result: ManseV2Result) -> SeparationNatal | None:
    """원국 조건 묶음 — 기둥·세력 분석이 없으면 None."""
    p = result.pillars
    fa = result.force_analysis
    if p is None or fa is None:
        return None
    gender = str(result.input_summary.get("gender") or "unknown")
    hour_known = p.hour is not None
    tg = fa.ten_gods
    if not hour_known:
        zy = "unknown"
    elif "정인" in tg.missing_ten_gods:
        zy = "missing"
    elif "정인" in tg.hidden_only_ten_gods:
        zy = "hidden_only"
    else:
        zy = "present"
    stems = [x.stem_ten_god for x in (p.year, p.month, p.hour) if x is not None]
    mains = [x.branch_main_ten_god for x in (p.year, p.month, p.day, p.hour) if x is not None]
    return SeparationNatal(
        gender=gender,
        hour_known=hour_known,
        officer_pct=float(tg.groups.get("officer", 0.0)),
        zhengyin_state=zy,
        day_palace_zhengcai=p.day.branch_main_ten_god == "정재",
        natal_zhengcai="정재" in stems or "정재" in mains,
    )


def _inflow(signals: list, target_layer: LuckLayer, gods: tuple[TenGod, ...]) -> str | None:
    """채점 대상 층의 해당 십성 유입 — 'stem'(천간 포함) / 'branch'(지지만) / None."""
    hits = [s for s in signals if s.layer is target_layer and s.ten_god in gods]
    if not hits:
        return None
    return "stem" if any(s.source == "stem" for s in hits) else "branch"


def _seed(
    period: str, layer: LuckLayer, score: int, god: TenGod, codes: list[str],
) -> EventCandidateV2:
    """relationship_change 시드 1건 — 단독 시드라 점수가 곧 base(기여 합 불변식)."""
    return EventCandidateV2(
        event_key=EventKeyV2.RELATIONSHIP_CHANGE,
        period=period,
        score=score,
        confidence_level=(
            ConfidenceLevel.EVENT_CANDIDATE if score >= 55
            else ConfidenceLevel.WEAK_EVENT_CANDIDATE if score >= 45
            else ConfidenceLevel.THEME_ONLY
        ),
        polarity_role=PolarityRole.NEUTRAL,
        source_layers=[layer],
        candidate_source_layers=[layer.value],
        source_ten_gods=[god],
        reason_codes=codes,
        contributions={"base": float(score)},
    )


def produce_love_separation_seeds(
    signals: list,
    target_layer: LuckLayer,
    result: ManseV2Result,
    period: str,
    enabled: Mapping[str, bool],
) -> list[EventCandidateV2]:
    """이별운 강의 시드 — 켜진 규칙마다 0 또는 1건(relationship_change).

    Args:
        signals: 거버닝 스택 운 십성 신호(층위·출처 포함).
        target_layer: 채점 대상 층 — 세운·월운만.
        result: 만세 결과.
        period: 시점 라벨.
        enabled: 실험 키 → ON 여부(`resolve_love_experiments` 결과).
    """
    if target_layer not in (LuckLayer.SEWOON, LuckLayer.WOLWOON):
        return []
    if not any(enabled.get(k) for k in SEPARATION_KEYS[:4]):
        return []
    nat = separation_natal(result)
    if nat is None:
        return []
    weight = "branch" if enabled.get(SEP_PEER_BRANCH_WEIGHT) else "stem"
    idx = {"stem": 0, "branch": 1}
    out: list[EventCandidateV2] = []
    if enabled.get(SEP_OFFICER_OUTPUT) and nat.gender == "female" and nat.officer_weak:
        src = _inflow(signals, target_layer, _OUTPUT)
        if src is not None:
            god = next(
                s.ten_god for s in signals
                if s.layer is target_layer and s.ten_god in _OUTPUT
            )
            out.append(_seed(period, target_layer, OFFICER_OUTPUT_BASE[idx[src]], god, [
                "LOVE_SEP_OFFICER_OUTPUT", f"LOVE_SEP_INFLOW_{src.upper()}",
            ]))
    if enabled.get(SEP_PALACE_JIECAI) and nat.gender == "male" and nat.day_palace_zhengcai:
        src = _inflow(signals, target_layer, (TenGod.JIECAI,))
        if src is not None:
            out.append(_seed(period, target_layer, PALACE_JIECAI_BASE[weight][idx[src]],
                             TenGod.JIECAI, [
                                 "LOVE_SEP_PALACE_JIECAI", f"LOVE_SEP_INFLOW_{src.upper()}",
                                 f"LOVE_SEP_WEIGHT_{weight.upper()}",
                             ]))
    if enabled.get(SEP_RESOURCE_INFLOW) and nat.gender == "female" and nat.resource_lacking:
        src = _inflow(signals, target_layer, (TenGod.ZHENGYIN,))
        if src is not None:
            out.append(_seed(period, target_layer, RESOURCE_INFLOW_BASE[idx[src]],
                             TenGod.ZHENGYIN, [
                                 "LOVE_SEP_RESOURCE_INFLOW", f"LOVE_SEP_INFLOW_{src.upper()}",
                                 f"LOVE_SEP_ZHENGYIN_{nat.zhengyin_state.upper()}",
                             ]))
    if enabled.get(SEP_ZHENGCAI_PEER) and nat.natal_zhengcai:
        best: tuple[int, TenGod, str] | None = None
        for god in (TenGod.JIECAI, TenGod.BIJIAN):
            src = _inflow(signals, target_layer, (god,))
            if src is None:
                continue
            score = ZHENGCAI_PEER_BASE[weight][god][idx[src]]
            if best is None or score > best[0]:
                best = (score, god, src)
        if best is not None:
            score, god, src = best
            out.append(_seed(period, target_layer, score, god, [
                "LOVE_SEP_ZHENGCAI_PEER", f"LOVE_SEP_PEER_{god.value}",
                f"LOVE_SEP_INFLOW_{src.upper()}", f"LOVE_SEP_WEIGHT_{weight.upper()}",
            ]))
    # 같은 사건 키 — 최고점 1건으로 합치고 근거 코드는 합집합(시드끼리 중복 후보 방지).
    if len(out) > 1:
        top = max(out, key=lambda c: c.score)
        for c in out:
            for code in c.reason_codes:
                if code not in top.reason_codes:
                    top.reason_codes.append(code)
        out = [top]
    return out


# ── 서술층(관계 질문 전용) ──────────────────────────────────────────────────


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    path = dictionaries_dir / "interpretations" / "love_separation_lecture_text.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["id"]: it["text"] for it in data["items"]}


def love_separation_natal_lines(result: ManseV2Result) -> list[str]:
    """원국 분류 해설 줄 — 무인성(정인 없음)·정인 약함. 시주 미상이면 분류하지 않는다."""
    nat = separation_natal(result)
    if nat is None or not nat.resource_lacking:
        return []
    t = _texts()
    key = (
        "no_resource_classification" if nat.zhengyin_state == "missing"
        else "weak_resource_classification"
    )
    return [f"원국 분류(해설 — 판정 아님): {t[key]}"]


def love_separation_texts(ganji: str, result: ManseV2Result) -> list[str]:
    """운 간지 1개에 붙는 이별운 강의 문구(조건 성립분만)."""
    nat = separation_natal(result)
    p = result.pillars
    if nat is None or p is None or len(ganji) < 2:
        return []
    try:
        dm = Stem(p.day_master)
        stem_tg = str(ten_god(dm, Stem(ganji[0])))
        branch_tg = str(ten_god(dm, Stem(main_hidden_stem(Branch(ganji[1])).value)))
    except ValueError:
        return []
    gods = (stem_tg, branch_tg)
    t = _texts()
    out: list[str] = []
    if nat.gender == "female" and nat.officer_weak and ("식신" in gods or "상관" in gods):
        out.append(t["officer_output"])
    if nat.gender == "male" and nat.day_palace_zhengcai and "겁재" in gods:
        out.append(t["palace_jiecai"])
    if nat.gender == "female" and nat.resource_lacking and "정인" in gods:
        out.append(t["resource_inflow"])
    if nat.natal_zhengcai and ("겁재" in gods or "비견" in gods):
        out.append(t["zhengcai_peer"])
    return out


def love_separation_block(result: ManseV2Result, periods: list[tuple[str, str]]) -> list[str]:
    """관계 질문용 블록 — 후보 기간 운 간지마다 문구를 간지당 1회 묶는다(없으면 빈 목록)."""
    seen: set[str] = set()
    lines: list[str] = []
    for period, ganji in periods:
        if not ganji or ganji in seen:
            continue
        seen.add(ganji)
        texts = love_separation_texts(ganji, result)
        if texts:
            lines.append(f"- {period} {ganji}: " + " ".join(texts))
    if not lines:
        return []
    return [
        "[연애·관계 운 결 — 이별운 강의 번역층(원국 글자 × 운 글자)] 운이 온다는 것은 그런 환경이 "
        "조성된다는 뜻이다. 이별·관계 변동은 가능성형으로만 쓰고, 상대의 명식·마음에 따라 "
        "달라질 수 있음을 전제할 것.",
        *lines,
    ]
