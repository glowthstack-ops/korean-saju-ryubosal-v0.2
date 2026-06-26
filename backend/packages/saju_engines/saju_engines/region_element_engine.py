"""지역 오행 추천 엔진 (v2.2 P1, docs/12).

지역 자체의 **고유 오행(고정·사전계산)** 과 사용자 기준 **추천 오행(가변·요청 시점)** 을 분리한다
(docs/12 §0). 본 모듈은 두 축을 모두 구현한다.

고정 프로필(build_profiles, §4·§5):
- 한자 레이어: 시군구 한자명을 region_hanja_tokens.json으로 토큰화(§4-2). 미매칭은
  region_elements.json의 큐레이션 오행으로 낮은 신뢰도 폴백(D2). `alt.when`(GIS 신호)은 P3 전까지
  미발동 — default_element만 쓴다.
- 음운 레이어: 한글명 초성 오행 평균(§4-3). 유효가중은 weight_cap(0.03) 절대 상한(D1) — GIS
  레이어가 없는 P1에서 단순 재정규화로 음운이 과대해지는 것을 막는다.
- 부모 상속: 한자가 없는 단위(읍면동 전부, 일부 시군구)는 상위 프로필을 상속하되 신뢰도를 낮춘다.
- 미공급 레이어(지형·수계·풍수)는 confidence=0으로 제외하고 부분집합으로 재정규화(절대원칙 11).

가변 추천(recommend, §6·§7):
- 사용자 용/희/기/구신 + 보완 오행과 프로필 벡터의 매칭 점수(0~100). GIS 미반영 P1은 신뢰도
  상한으로 과한 점수를 막는다.
- 방위는 프로필에 저장하지 않고(§4-4) 추천 시점에 base_location → 후보 anchor bearing으로
  계산한다. 명리형 혼합 방위 모델은 region_direction.py를 재사용한다(§12).

LLM은 계산하지 않고 결과를 자연어로 설명만 한다(절대원칙 1·2). 모든 산식 파라미터는 사전
(region/*.json)에서 읽는다(절대원칙 9).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.constants import GENERATES
from saju_shared_types.enums import Element
from saju_shared_types.region_element import (
    DominanceType,
    ElementVector,
    IntentMode,
    RegionAdminSnapshot,
    RegionAdminUnit,
    RegionElementProfile,
    RegionFitItem,
    RegionLevel,
    RegionProfilesSnapshot,
    RegionRecommendationQuery,
    RegionRecommendationResult,
    RegionResolution,
    RegionUnitInput,
    TargetElements,
)

from .region_direction import _DIRECTION_ELEMENTS, RegionDirection, _bearing_to_compass

_ELEMENT_KEYS: tuple[str, ...] = tuple(e.value for e in Element)

# 레이어 신뢰도(자체 기준 초안 — 사전 검수와 함께 조정).
_PHONETIC_CONFIDENCE = 0.30  # 음운 레이어 신뢰도(보조)
_PHONETIC_ONLY_CONFIDENCE = 0.20  # 음운만 남은 단위(상위·한자 모두 없음) → unknown 유도
_HANJA_FALLBACK_CONFIDENCE = 0.35  # region_elements 큐레이션 폴백(D2)
_HANJA_TOKEN_BASE_CONF = 0.50  # 한자 토큰 매칭 1자 기준
_HANJA_TOKEN_PER_MATCH = 0.08  # 매칭 1자당 가산
_HANJA_TOKEN_MAX_CONF = 0.80
_INHERIT_DECAY = 0.70  # 부모 프로필 상속 시 신뢰도 감쇠

# 음운 입력에서 떼어내는 행정 접미(초성 노이즈 완화). 1글자만 제거한다.
_ADMIN_SUFFIX = set("동리읍면가구시군도")

# RegionResolution(질의) → RegionLevel(프로필) 매핑.
_RESOLUTION_TO_LEVEL: dict[RegionResolution, RegionLevel] = {
    RegionResolution.SIDO: RegionLevel.CTPRVN,
    RegionResolution.SIGUNGU: RegionLevel.SIG,
    RegionResolution.EUP_MYEON_DONG: RegionLevel.EMD,
    RegionResolution.RI: RegionLevel.EMD,
}

# 역할(한글) — region_direction.direction_fit favorability 입력용.
_ROLE_KO = {"yongsin": "용신", "huisin": "희신", "gisin": "기신", "gusin": "구신"}

# 약식/별칭 시도명 → 정식 시도명(지명 해소·scope용). doc/gis 정식명 기준.
_SIDO_ALIASES: dict[str, str] = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "세종시": "세종특별자치시", "경기": "경기도", "강원": "강원특별자치도",
    "강원도": "강원특별자치도", "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
}
# 수도권 = 서울·경기·인천(scope 별칭).
_CAPITAL_AREA_SIDO = ("서울특별시", "경기도", "인천광역시")
_CAPITAL_AREA_ALIASES = {"수도권", "수도권지역"}


class RegionNameResolver:
    """지명 → region_code 해소 + scope(시도/수도권/하위) 후보 열거(P2, docs/12 §2).

    읍면동명은 전국 590종이 중복(효자동·사직동 등)이라 단순명 해소는 모호하다. full_name 완전
    일치(유일) → 토큰 포함(시도 별칭 확장) → leaf 명 동률 시 leaf 정확일치로 좁힌다. 끝까지 모호하면
    추측하지 않고 후보 목록을 반환한다(절대원칙 7 — 대상/지역 혼동 방지).
    """

    def __init__(self, units: list[RegionAdminUnit]) -> None:
        self._units = units
        self._by_code: dict[str, RegionAdminUnit] = {u.region_id: u for u in units}
        self._by_full_name: dict[str, RegionAdminUnit] = {u.full_name: u for u in units}
        self._sido_names: set[str] = {u.sido_name for u in units if u.sido_name}
        self._children: dict[str, list[str]] = {}
        for u in units:
            if u.parent_code:
                self._children.setdefault(u.parent_code, []).append(u.region_id)

    def resolve(
        self, name: str, level: RegionLevel | None = None
    ) -> tuple[str | None, list[str]]:
        """지명 → (region_code, 모호 시 후보 full_name 목록). 해소 실패=(None, [])."""
        name = name.strip()
        if not name:
            return None, []
        if name in self._by_full_name:
            return self._by_full_name[name].region_id, []
        tokens = name.split()
        norm = [_SIDO_ALIASES.get(t, t) for t in tokens]
        cands = [u for u in self._units if all(t in u.full_name for t in norm)]
        if level is not None:
            leveled = [u for u in cands if u.region_level is level]
            if leveled:
                cands = leveled
        if len(cands) > 1:
            leaf_exact = [u for u in cands if u.full_name.split()[-1] == tokens[-1]]
            if leaf_exact:
                cands = leaf_exact
        if len(cands) == 1:
            return cands[0].region_id, []
        if not cands:
            return None, []
        return None, sorted(u.full_name for u in cands)[:10]

    def resolve_scope(self, scope: str, level: RegionLevel) -> list[str]:
        """scope(수도권/시도명/상위지역) → 해당 레벨 하위 region_code 목록."""
        scope = scope.strip()
        if scope in _CAPITAL_AREA_ALIASES:
            sidos: tuple[str, ...] = _CAPITAL_AREA_SIDO
        else:
            full = _SIDO_ALIASES.get(scope, scope)
            if full in self._sido_names:
                sidos = (full,)
            else:
                code, _ = self.resolve(scope)
                if code is not None:
                    return self._descendants(code, level)
                return []
        return [
            u.region_id
            for u in self._units
            if u.region_level is level and u.sido_name in sidos
        ]

    def _descendants(self, code: str, level: RegionLevel) -> list[str]:
        """code 하위에서 target level에 해당하는 region_code(BFS)."""
        out: list[str] = []
        queue = list(self._children.get(code, []))
        while queue:
            cur = queue.pop()
            unit = self._by_code.get(cur)
            if unit is None:
                continue
            if unit.region_level is level:
                out.append(cur)
            queue.extend(self._children.get(cur, []))
        return out


def _normalize_map(vec: dict[str, float]) -> dict[str, float]:
    """오행 dict를 합=1로 정규화. 합이 0이면 그대로(보정 없음, 절대원칙 11)."""
    total = sum(vec.values())
    if total <= 0.0:
        return dict(vec)
    return {k: v / total for k, v in vec.items()}


def _chosung(ch: str) -> int | None:
    """한글 음절의 초성 인덱스(0~18). 음절이 아니면 None."""
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) // 588
    return None


# 초성 인덱스(0~18) → 대표 초성(쌍자음은 평음으로 접기).
_CHOSUNG_CHARS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_TENSE_FOLD = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}


class _LayerContribution:
    """단일 레이어 기여(벡터·원가중·신뢰도·라벨)."""

    __slots__ = ("vector", "raw_weight", "confidence", "label")

    def __init__(
        self, vector: dict[str, float], raw_weight: float, confidence: float, label: str
    ) -> None:
        self.vector = vector
        self.raw_weight = raw_weight
        self.confidence = confidence
        self.label = label


class RegionElementEngine:
    """지역 오행 프로필 빌드(고정) + 사용자 매칭 추천(가변). 순수·결정론."""

    def __init__(
        self,
        dictionaries_dir: Path,
        profiles_path: Path | None = None,
        admin_path: Path | None = None,
    ) -> None:
        """사전 로드. profiles_path/admin_path 지정 시 compiled 스냅샷도 로드(추천·조회용).

        Args:
            dictionaries_dir: backend/dictionaries 경로.
            profiles_path: compiled/region_element_profiles_vX.json(추천 시 필요).
            admin_path: compiled/region_admin_units_vX.json(지명 해소·scope, 선택 — P2).
        """
        region_dir = dictionaries_dir / "region"
        tokens_raw = json.loads(
            (region_dir / "region_hanja_tokens.json").read_text("utf-8")
        )
        self._token_element: dict[str, tuple[str, float]] = {
            t["char"]: (t["element"], float(t["weight"])) for t in tokens_raw["tokens"]
        }
        # 문맥 규칙은 P1에선 default_element만 사용(alt.when은 P3 GIS 신호).
        self._context_element: dict[str, tuple[str, float]] = {
            r["char"]: (r["default_element"], float(r["default_weight"]))
            for r in tokens_raw.get("context_rules", [])
        }

        phon_raw = json.loads((region_dir / "region_phonetic.json").read_text("utf-8"))
        self._phonetic_cap = float(phon_raw["weight_cap"])
        self._initial_element: dict[str, str] = {}
        for item in phon_raw["initials"]:
            for ini in item["initials"]:
                self._initial_element[ini] = item["element"]

        weights_raw = json.loads(
            (region_dir / "region_layer_weights.json").read_text("utf-8")
        )
        self._base_weights: dict[str, float] = weights_raw["base"]
        self._intent_weights: dict[str, dict[str, float]] = weights_raw["intents"]

        rules_raw = json.loads(
            (region_dir / "region_dominance_rules.json").read_text("utf-8")
        )
        self._bands = rules_raw["confidence_bands"]
        self._single = rules_raw["single"]
        self._composite = rules_raw["composite"]
        self._user_match = rules_raw["user_match"]

        # 한자 소스(흡수, §12): region_elements.json — '{시도} {시군구}' → hanja·elements·대표.
        regions_raw = json.loads(
            (dictionaries_dir / "region_elements.json").read_text("utf-8")
        )
        self._region_element_repr: dict[str, str] = {
            i["region"]: i["element"] for i in regions_raw["items"]
        }

        # 방위 레이어 재사용(§4-4·§12) — direction_fit(혼합 모델)만 호출.
        self._region_dir = RegionDirection(dictionaries_dir)

        # 추천·조회용 스냅샷(선택).
        self._profiles: dict[str, RegionElementProfile] = {}
        self._by_full_name: dict[str, RegionElementProfile] = {}
        if profiles_path is not None:
            snap = RegionProfilesSnapshot.model_validate_json(
                profiles_path.read_text("utf-8")
            )
            for p in snap.items:
                self._profiles[p.region_code] = p
                self._by_full_name[p.full_name] = p

        # 지명 해소기(선택, P2). 없으면 legacy full_name 매칭으로 폴백.
        self._resolver: RegionNameResolver | None = None
        if admin_path is not None:
            admin = RegionAdminSnapshot.model_validate_json(admin_path.read_text("utf-8"))
            self._resolver = RegionNameResolver(admin.items)

    # ── 고정 프로필 빌드 ─────────────────────────────────────────

    def build_profiles(
        self, units: list[RegionUnitInput], model_version: str
    ) -> list[RegionElementProfile]:
        """단위 목록 → 프로필 목록(상위→하위 순으로 빌드해 부모 상속을 가능케 함)."""
        order = {RegionLevel.CTPRVN: 0, RegionLevel.SIG: 1, RegionLevel.EMD: 2}
        ordered = sorted(units, key=lambda u: order[u.region_level])
        built: dict[str, RegionElementProfile] = {}
        out: list[RegionElementProfile] = []
        for unit in ordered:
            parent = built.get(unit.parent_code) if unit.parent_code else None
            profile = self.build_profile(unit, parent, model_version)
            built[profile.region_code] = profile
            out.append(profile)
        return out

    def build_profile(
        self,
        unit: RegionUnitInput,
        parent: RegionElementProfile | None,
        model_version: str,
    ) -> RegionElementProfile:
        """단위 1건 + (선택) 부모 프로필 → 고정 오행 프로필(방위 미포함, §4-4)."""
        contribs: list[_LayerContribution] = []

        hanja = self._hanja_layer(unit.hanja, unit.fallback_elements)
        if hanja is not None:
            contribs.append(hanja)
        phonetic = self._phonetic_layer(unit.region_name_ko or unit.full_name_ko)
        if phonetic is not None:
            contribs.append(phonetic)
        # 자체 한자가 없으면 부모 프로필을 상속 레이어로 추가(신뢰도 감쇠).
        if hanja is None and parent is not None:
            contribs.append(
                _LayerContribution(
                    vector=parent.element_vector.normalized().as_map(),
                    raw_weight=1.0,
                    confidence=parent.confidence * _INHERIT_DECAY,
                    label="parent_inheritance",
                )
            )

        vector_map, confidence, source_layers = self._combine(contribs)
        dom_type, dom_elements = self._dominance(vector_map, confidence)
        return RegionElementProfile(
            region_id=unit.region_code,
            region_code=unit.region_code,
            region_level=unit.region_level,
            parent_code=unit.parent_code,
            legal_dong_code=unit.region_code if unit.region_level is RegionLevel.EMD else "",
            full_name=unit.full_name_ko,
            model_version=model_version,
            element_vector=ElementVector.from_map(vector_map),
            dominant_type=dom_type,
            dominant_elements=dom_elements,
            confidence=round(confidence, 4),
            source_layers=source_layers,
            centroid_lat=unit.centroid_lat,
            centroid_lon=unit.centroid_lon,
            anchor_lat=unit.anchor_lat,
            anchor_lon=unit.anchor_lon,
        )

    def _hanja_layer(
        self, hanja: str | None, fallback_elements: list[str]
    ) -> _LayerContribution | None:
        """한자명 토큰화(§4-2). 미매칭은 region_elements 큐레이션 오행으로 폴백(D2)."""
        weight = self._base_weights.get("hanja_place_name", 0.0)
        if hanja:
            acc: dict[str, float] = {}
            matched = 0
            for ch in hanja:
                hit = self._token_element.get(ch) or self._context_element.get(ch)
                if hit is None:
                    continue
                el, w = hit
                acc[el] = acc.get(el, 0.0) + w
                matched += 1
            if matched > 0:
                conf = min(
                    _HANJA_TOKEN_MAX_CONF,
                    _HANJA_TOKEN_BASE_CONF + _HANJA_TOKEN_PER_MATCH * matched,
                )
                return _LayerContribution(
                    _normalize_map(acc), weight, conf, "hanja_token"
                )
        if fallback_elements:
            acc = {el: 1.0 for el in fallback_elements if el in _ELEMENT_KEYS}
            if acc:
                return _LayerContribution(
                    _normalize_map(acc),
                    weight,
                    _HANJA_FALLBACK_CONFIDENCE,
                    "hanja_fallback_legacy",
                )
        return None

    def _phonetic_layer(self, name: str) -> _LayerContribution | None:
        """한글명 초성 오행 평균(§4-3). 행정 접미 1자는 노이즈로 제거."""
        core = name.strip().split()[-1] if name.strip() else ""
        if len(core) >= 2 and core[-1] in _ADMIN_SUFFIX:
            core = core[:-1]
        acc: dict[str, float] = {}
        count = 0
        for ch in core:
            idx = _chosung(ch)
            if idx is None:
                continue
            initial = _CHOSUNG_CHARS[idx]
            initial = _TENSE_FOLD.get(initial, initial)
            el = self._initial_element.get(initial)
            if el is None:
                continue
            acc[el] = acc.get(el, 0.0) + 1.0
            count += 1
        if count == 0:
            return None
        weight = self._base_weights.get("phonetic_reading", 0.0)
        return _LayerContribution(
            _normalize_map(acc), weight, _PHONETIC_CONFIDENCE, "phonetic_layer"
        )

    def _combine(
        self, contribs: list[_LayerContribution]
    ) -> tuple[dict[str, float], float, list[str]]:
        """레이어 가중합 + 스텁 재정규화 + 음운 cap(D1). → (벡터, 신뢰도, source_layers)."""
        if not contribs:
            return {}, 0.0, []
        phonetic = next((c for c in contribs if c.label == "phonetic_layer"), None)
        others = [c for c in contribs if c.label != "phonetic_layer"]

        # 음운만 남은 단위(상위·한자 모두 없음) — 단정 금지(신뢰도 매우 낮게).
        if not others and phonetic is not None:
            return (
                dict(phonetic.vector),
                _PHONETIC_ONLY_CONFIDENCE,
                [phonetic.label],
            )

        eff: list[tuple[_LayerContribution, float]] = []
        phon_eff = 0.0
        if phonetic is not None:
            phon_eff = min(phonetic.raw_weight, self._phonetic_cap)
        remaining = 1.0 - phon_eff
        others_total = sum(c.raw_weight for c in others)
        if others_total <= 0.0:
            # 가중이 0인 비정상 입력 — 균등 배분(보정 최소화).
            for c in others:
                eff.append((c, remaining / len(others)))
        else:
            for c in others:
                eff.append((c, remaining * c.raw_weight / others_total))
        if phonetic is not None and phon_eff > 0.0:
            eff.append((phonetic, phon_eff))

        acc: dict[str, float] = {}
        labels: list[str] = []
        # 신뢰도는 비-음운 레이어로만 산정한다 — 음운은 cap(0.03)의 벡터 보조 신호일 뿐,
        # 우세 판정의 근거가 되어선 안 된다(D1·과확정 방지).
        conf_num = 0.0
        conf_den = 0.0
        for c, w in eff:
            for el, val in c.vector.items():
                acc[el] = acc.get(el, 0.0) + val * w
            labels.append(c.label)
            if c.label != "phonetic_layer":
                conf_num += c.confidence * w
                conf_den += w
        confidence = conf_num / conf_den if conf_den > 0.0 else _PHONETIC_ONLY_CONFIDENCE
        return _normalize_map(acc), confidence, labels

    def _dominance(
        self, vector_map: dict[str, float], confidence: float
    ) -> tuple[DominanceType, list[str]]:
        """정규화 벡터 + 신뢰도 → 우세 등급·우세 오행(docs/12 §5, P1 밴드)."""
        if not vector_map:
            return DominanceType.UNKNOWN, []
        ordered = sorted(vector_map.items(), key=lambda kv: kv[1], reverse=True)
        top1_el, top1 = ordered[0]
        top2_el, top2 = ordered[1] if len(ordered) > 1 else ("", 0.0)
        gap = top1 - top2

        if confidence < self._bands["unknown_below"]:
            return DominanceType.UNKNOWN, []
        if confidence < self._bands["weak_below"]:
            return DominanceType.WEAK, [top1_el]
        if (
            top1 >= self._single["max_element_min"]
            and gap >= self._single["gap_min"]
        ):
            return DominanceType.SINGLE, [top1_el]
        if (
            (top1 + top2) >= self._composite["top2_sum_min"]
            and gap < self._composite["gap_max"]
        ):
            return DominanceType.COMPOSITE, [top1_el, top2_el]
        return DominanceType.CONTESTED, [top1_el]

    # ── 가변 추천 ────────────────────────────────────────────────

    def get_profile(self, region_code: str) -> RegionElementProfile | None:
        """region_code로 프로필 조회(스냅샷 로드 필요)."""
        return self._profiles.get(region_code)

    def recommend(self, query: RegionRecommendationQuery) -> RegionRecommendationResult:
        """사용자 용/희/기/구신·의도·거주지로 후보 지역을 매칭·랭킹(docs/12 §6·§7)."""
        notes: list[str] = []
        candidates = self._select_candidates(query, notes)
        base_anchor = (
            self._resolve_anchor(query.base_location) if query.base_location else None
        )
        if query.base_location and base_anchor is None:
            notes.append("현재 거주지를 좌표로 확인하지 못해 방위는 산출하지 않음")

        items: list[RegionFitItem] = []
        for profile in candidates:
            item = self._score_profile(profile, query.target_elements, base_anchor)
            items.append(item)
        items.sort(key=lambda it: (-it.match_score, -it.confidence))
        if any(it.confidence < self._bands["weak_below"] for it in items[: query.top_n]):
            notes.append("지형 GIS 레이어 반영 전 1차 추정 — 확정도가 낮은 지역이 있음")
        return RegionRecommendationResult(
            recommended_regions=items[: query.top_n],
            intent_mode=query.intent_mode,
            notes=notes,
        )

    def _select_candidates(
        self, query: RegionRecommendationQuery, notes: list[str]
    ) -> list[RegionElementProfile]:
        """후보 프로필 선별: 명시 후보 > scope(시도/수도권) > 전국 시군구 폴백(P2 해소기 사용)."""
        level = _RESOLUTION_TO_LEVEL[query.resolution]
        if query.candidate_regions:
            out: list[RegionElementProfile] = []
            for name in query.candidate_regions:
                p = self._lookup_profile(name, notes)
                if p is not None:
                    out.append(p)
            return out
        if query.candidate_scope:
            codes = (
                self._resolver.resolve_scope(query.candidate_scope, level)
                if self._resolver is not None
                else []
            )
            matched = [self._profiles[c] for c in codes if c in self._profiles]
            if matched:
                return matched
            # 폴백: 해소기 없거나 scope 미확인 → full_name 부분일치.
            legacy = [
                p
                for p in self._profiles.values()
                if p.region_level is level and query.candidate_scope in p.full_name
            ]
            if legacy:
                return legacy
            notes.append(f"후보 범위 미확인 — {query.candidate_scope}, 전국 시군구로 대체")
        # 폴백: 전국 시군구(과대 후보 방지).
        return [p for p in self._profiles.values() if p.region_level is RegionLevel.SIG]

    def _lookup_profile(
        self, name: str, notes: list[str], level: RegionLevel | None = None
    ) -> RegionElementProfile | None:
        """지명 → 프로필(해소기 우선, 모호 시 후보 노트). 폴백=legacy full_name 매칭."""
        if self._resolver is not None:
            code, ambiguous = self._resolver.resolve(name, level)
            if code is not None:
                return self._profiles.get(code)
            if ambiguous:
                notes.append(f"지역이 모호함 — {name} (후보: {', '.join(ambiguous)})")
                return None
            notes.append(f"후보 지역 미확인 — {name}")
            return None
        p = self._resolve_profile(name)
        if p is None:
            notes.append(f"후보 지역 미확인 — {name}")
        return p

    def _score_profile(
        self,
        profile: RegionElementProfile,
        target: TargetElements,
        base_anchor: tuple[float, float] | None,
    ) -> RegionFitItem:
        """프로필 × 사용자 역할 → match/avoid 점수 + 방위(가변, §6)."""
        vector = profile.element_vector.normalized().as_map()
        roles = self._user_match["role_scores"]
        role_of = self._role_lookup(target)

        raw_fit = sum(vector[el] * roles.get(role_of.get(el, "한신"), 0.0) for el in vector)
        gisin_ratio = sum(vector[el] for el in target.gisin)
        gusin_ratio = sum(vector[el] for el in target.gusin)
        pen = self._user_match["penalty"]
        penalty = gisin_ratio * pen["gisin_factor"] + gusin_ratio * pen["gusin_factor"]
        adj = self._user_match["confidence_adjust"]
        conf_adj = raw_fit * (adj["base"] + profile.confidence * adj["scale"])
        score = 50.0 + conf_adj * 50.0 - penalty * pen["score_penalty_scale"]
        score = max(0.0, min(100.0, score))
        for cap in self._user_match["score_caps"]:
            if profile.confidence < cap["confidence_below"]:
                score = min(score, float(cap["max_score"]))
        avoid = max(0, min(100, round(penalty * 100)))

        risk_flags: list[str] = []
        if gisin_ratio >= pen["gisin_strong_threshold"]:
            risk_flags.append("gisin_strong")
        if gusin_ratio >= pen["gusin_strong_threshold"]:
            risk_flags.append("gusin_present")

        direction, direction_fit = self._direction(profile, target, base_anchor)
        return RegionFitItem(
            region_name=profile.full_name,
            legal_dong_code=profile.legal_dong_code,
            dominant_elements=profile.dominant_elements,
            element_vector=profile.element_vector,
            match_score=round(score),
            avoid_score=avoid,
            confidence=profile.confidence,
            reason_summary=self._reason(profile, role_of),
            evidence=[],
            direction=direction,
            direction_fit=direction_fit,
            risk_flags=risk_flags,
        )

    def _role_lookup(self, target: TargetElements) -> dict[str, str]:
        """오행(한자) → 역할(한글). 우선순위: 용>희>보완>기>구(중복 시 앞이 우선)."""
        out: dict[str, str] = {}
        for el in target.gusin:
            out[el] = "구신"
        for el in target.gisin:
            out[el] = "기신"
        for el in target.boost:
            out[el] = "보완"
        for el in target.huisin:
            out[el] = "희신"
        for el in target.yongsin:
            out[el] = "용신"
        return out

    def _direction(
        self,
        profile: RegionElementProfile,
        target: TargetElements,
        base_anchor: tuple[float, float] | None,
    ) -> tuple[str, str]:
        """base_location → 후보 anchor bearing → 혼합 방위 적합(region_direction 재사용, §4-4)."""
        if base_anchor is None:
            return "", ""
        if profile.anchor_lat is None or profile.anchor_lon is None:
            return "", ""
        compass = _bearing_to_compass(
            base_anchor, (profile.anchor_lat, profile.anchor_lon)
        )
        if compass not in _DIRECTION_ELEMENTS:
            return "", ""
        fav: dict[str, str] = {}
        for field, role_ko in _ROLE_KO.items():
            for el in getattr(target, field):
                fav.setdefault(el, role_ko)
        _, label, _ = self._region_dir.direction_fit(compass, fav)
        return compass, label

    def _reason(self, profile: RegionElementProfile, role_of: dict[str, str]) -> str:
        """사용자 노출용 근거 요약(단정 금지 — '유리/보완성/기류', 절대원칙 3)."""
        if not profile.dominant_elements:
            return "지명·음운 기반 1차 추정이며 지형 GIS 반영 전이라 확정도는 낮음"
        doms = profile.dominant_elements
        roles = [f"{el}({role_of[el]})" for el in doms if el in role_of]
        if roles:
            return f"우세 오행 {'·'.join(doms)} 중 {'·'.join(roles)} — 보완성 기류"
        return f"우세 오행 {'·'.join(doms)} 추정(현재 데이터 기준)"

    def _resolve_profile(self, name: str) -> RegionElementProfile | None:
        """지명 → 프로필(완전일치 → 접미 유일일치). 모호하면 None(추측 금지)."""
        if name in self._by_full_name:
            return self._by_full_name[name]
        suffix = [p for n, p in self._by_full_name.items() if n.endswith(" " + name)]
        if len(suffix) == 1:
            return suffix[0]
        return None

    def _resolve_anchor(self, base_location: str) -> tuple[float, float] | None:
        """거주지 지명 → 대표 anchor 좌표(해소기→프로필, 없으면 region_coords 폴백)."""
        p: RegionElementProfile | None = None
        if self._resolver is not None:
            code, _ = self._resolver.resolve(base_location)
            if code is not None:
                p = self._profiles.get(code)
        if p is None:
            p = self._resolve_profile(base_location)
        if p is not None and p.anchor_lat is not None and p.anchor_lon is not None:
            return (p.anchor_lat, p.anchor_lon)
        return self._region_dir.coords(base_location)

    # ── region_fit 승격(D3) — 기존 relocation 호환 ─────────────────

    def region_fit_scores(
        self, regions: list[str], yongsin_by_subject: dict[str, str]
    ) -> dict[str, float]:
        """후보 지역 대표 오행 × 구성원 용신 적합(동일 1.0 / 용신을 생 0.8 / 그 외 0.5).

        relocation.region_fit()의 승격본(D3). 동일 입출력 계약을 보장한다 — 미등재 지역은
        보정 없음(0.5 중립). region_elements는 전 항목 검수 전 출시 금지.
        """
        return region_fit_scores(self._region_element_repr, regions, yongsin_by_subject)

    def intent_weights(self, intent_mode: IntentMode) -> dict[str, float]:
        """의도별 레이어 가중(없으면 base) — §7. P1 추천은 벡터에 직접 적용하지 않으나
        의도 라벨링·향후 GIS 활성용으로 노출한다."""
        return self._intent_weights.get(intent_mode.value, self._base_weights)


def region_fit_scores(
    region_element_map: dict[str, str],
    regions: list[str],
    yongsin_by_subject: dict[str, str],
) -> dict[str, float]:
    """대표 오행 맵 × 구성원 용신 적합(모듈 함수, relocation·engine 공용 승격본, D3)."""
    out: dict[str, float] = {}
    for region in regions:
        element = region_element_map.get(region)
        if element is None:
            out[region] = 0.5
            continue
        scores: list[float] = []
        for yongsin in yongsin_by_subject.values():
            if element == yongsin:
                scores.append(1.0)
            elif yongsin and GENERATES[Element(element)] == Element(yongsin):
                scores.append(0.8)
            else:
                scores.append(0.5)
        out[region] = round(sum(scores) / len(scores), 3) if scores else 0.5
    return out
