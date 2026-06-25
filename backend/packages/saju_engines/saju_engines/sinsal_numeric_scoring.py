"""Phase B-1 v2 — 신살 채널 shadow sidecar(관측 전용·운영 불변).

신살은 발생 가능성(occurrence_score)을 바꾸지 않는다(occurrence_score_delta=0 고정). 이미 생성된
사건 후보의 길흉(favorability)·리스크(risk)·완충(mitigation)·질감(texture) 채널만 관측 보정한다
(SINSAL_MODIFIER_SPEC §10-1b, 2026-06-25 확정). 초기 score 채널 모델은 길흉 방향 역행으로 폐기.

용신 operational sidecar와 동일 패턴: 후보별 채널 delta 를 candidate_index 기반 별도 dict list 로
산출. EventCandidate 미변경(.score/favorability 원본/polarity/final 불변)·event_engine·reduce·LLM
미투입. 게이트 off면 미산출. 길성=완충·도움 / 흉살=리스크·마찰 / 중립=질감 태그.
"""

from __future__ import annotations

from saju_manse_analysis.sinsal.sinsal_catalog import CATALOG_META

from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result

from . import sinsal_modifier_config as cfg

_PILLARS = ("year", "month", "day", "hour")


def _polarity_of(name: str) -> str:
    meta = CATALOG_META.get(name)
    return str(meta.get("polarity", "neutral")) if meta else "neutral"


def _pos_weight(domain: str, position: str) -> float:
    override = cfg.DOMAIN_OVERRIDE.get(domain)
    if override is not None:
        return override.get(position, cfg.PILLAR_DEFAULT_WEIGHT[position])
    return cfg.PILLAR_DEFAULT_WEIGHT[position]


def _natal_sinsal_pillars(
    result: ManseV2Result,
) -> list[tuple[str, str, str, str, str]]:
    """원국 신살 → (이름, 극성, 위치, 그 자리 지지글자, 천간글자)."""
    extras = result.traditional_extras
    if extras is None or extras.sinsal is None or result.pillars is None:
        return []
    out: list[tuple[str, str, str, str, str]] = []
    for item in extras.sinsal.full_list:
        if item.position not in _PILLARS:
            continue
        pillar = getattr(result.pillars, item.position, None)
        if pillar is None:
            continue
        out.append((item.name, _polarity_of(item.name), item.position, pillar.branch, pillar.stem))
    return out


def _reactivated(ganji: str, branch_char: str, stem_char: str) -> bool:
    """기간 운간지가 그 자리 글자를 재출현(복음 — 동일 지지/천간)으로 건드리는가.

    보수적 proxy(동일 글자 재출현만 — 충·합 재활성화는 미포함). 결정론·간지만으로 계산.
    """
    if len(ganji) < 2:
        return False
    return ganji[1] == branch_char or ganji[0] == stem_char


def apply_sinsal_channel_shadow(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    domain: str = "general",
    coef_override: dict[str, float] | None = None,
) -> list[dict]:
    """후보별 신살 채널 shadow sidecar(index 기반 list — period/event_key 충돌 무관).

    각 항목: candidate_index·period·event_key·legacy_score·occurrence_score_delta(항상 0)·
    favorability_delta·risk_delta·mitigation_delta·texture_tags·contributions. 재활성(복음) 신살만
    채널에 기여(배경 제외). 발생 가능성 미접촉(occurrence 채널 0). coef_override 는 캡 주입만.
    """
    sinsals = _natal_sinsal_pillars(result)
    caps = {**cfg.SINSAL_CHANNEL_CAPS, **(coef_override or {})}
    boost = cfg.SINSAL_NUMERIC_REACT_BOOST
    out: list[dict] = []
    for i, c in enumerate(candidates):
        legacy = int(c.score)
        ganji = ganji_by_period.get(c.period, "")
        base = {
            "candidate_index": i, "period": c.period,
            "event_key": str(getattr(c, "event_key", "")), "legacy_score": legacy,
            "occurrence_score_delta": 0,  # 발생 가능성 절대 불변(§10-1b).
        }
        if len(ganji) < 2:  # 임의 계산 금지 — skip 명시.
            out.append({**base, "favorability_delta": 0.0, "risk_delta": 0.0,
                        "mitigation_delta": 0.0, "texture_tags": [], "contributions": {},
                        "missing_ganji": True})
            continue
        fav = 0.0
        risk = 0.0
        mit = 0.0
        texture: list[str] = []
        contributions: dict[str, float] = {}
        for name, polarity, position, branch_char, stem_char in sinsals:
            # 그 기간 재활성(복음)된 신살만 채널 신호 — 비재활성은 배경(미반영).
            if not _reactivated(ganji, branch_char, stem_char):
                continue
            weight = _pos_weight(domain, position)
            if polarity == "positive":
                coef = cfg.SINSAL_CHANNEL_AUSPICIOUS.get(
                    name, cfg.SINSAL_CHANNEL_AUSPICIOUS_DEFAULT)
                mit += coef["mitigation"] * weight * boost
                fav += coef["favorability"] * weight * boost
                contributions[f"{name}@{position}"] = round(coef["mitigation"] * weight * boost, 3)
            elif polarity == "caution":
                coef = cfg.SINSAL_CHANNEL_INAUSPICIOUS.get(
                    name, cfg.SINSAL_CHANNEL_INAUSPICIOUS_DEFAULT)
                risk += coef["risk"] * weight * boost
                fav += coef["favorability"] * weight * boost  # 음수
                contributions[f"{name}@{position}"] = round(-coef["risk"] * weight * boost, 3)
            else:  # 중립 → 질감 태그(숫자 0).
                tag = cfg.SINSAL_CHANNEL_TEXTURE.get(name)
                if tag and tag not in texture:
                    texture.append(tag)
        # 채널 클램프(0~1 분수, 보조 보장).
        fav = round(max(-caps["favorability"], min(caps["favorability"], fav)), 3)
        risk = round(min(caps["risk"], risk), 3)
        mit = round(min(caps["mitigation"], mit), 3)
        out.append({**base, "favorability_delta": fav, "risk_delta": risk,
                    "mitigation_delta": mit, "texture_tags": texture,
                    "contributions": contributions})
    return out


def sinsal_channel_sidecar(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    domain: str = "general",
) -> list[dict] | None:
    """마스터 게이트 wrapper — SINSAL_NUMERIC_SHADOW_ENABLED off면 None(미산출).

    B-1 에서는 하네스/디버그/테스트만 호출(서비스 응답·LLM·reduce_candidates 미투입).
    """
    if not cfg.SINSAL_NUMERIC_SHADOW_ENABLED:
        return None
    return apply_sinsal_channel_shadow(result, candidates, ganji_by_period, domain=domain)


def _band(value: float, bands: list[tuple[float, str]]) -> str:
    for threshold, label in bands:
        if value >= threshold:
            return label
    return ""


def channel_note_ko(
    favorability_delta: float, risk_delta: float, mitigation_delta: float,
    texture_tags: list[str],
) -> str:
    """채널 delta → 숫자 없는 한글 시기색채 노트(§9·§10-2). 전부 미미하면 빈 문자열.

    예: '신살 시기색채: 완충 큼·유리한 색채 (이동·변동성)'. 발생 가능성은 다루지 않는다.
    """
    parts: list[str] = []
    mit = _band(mitigation_delta, cfg.SINSAL_CHANNEL_MIT_BANDS)
    if mit:
        parts.append(mit)
    risk = _band(risk_delta, cfg.SINSAL_CHANNEL_RISK_BANDS)
    if risk:
        parts.append(risk)
    if favorability_delta > 0:
        fav = _band(favorability_delta, cfg.SINSAL_CHANNEL_FAV_POS_BANDS)
    else:
        fav = _band(-favorability_delta, cfg.SINSAL_CHANNEL_FAV_NEG_BANDS)
    if fav:
        parts.append(fav)
    texture = "·".join(texture_tags)
    if not parts and not texture:
        return ""
    note = "신살 시기색채: " + "·".join(parts) if parts else "신살 시기색채:"
    if texture:
        note += f" ({texture})"
    return note


def sinsal_invariance_snapshot(
    result: ManseV2Result, candidates: list[EventCandidate],
) -> dict:
    """불변 검증용 스냅샷 — sidecar 산출 전후 동일해야 한다(운영 score/polarity 무변경)."""
    return {
        "scores": [(c.period, str(c.event_key), c.score) for c in candidates],
        "polarity": [(c.period, str(c.event_key), str(c.polarity)) for c in candidates],
    }
