"""신살 default 계산 테이블 (config 교체 가능).

유파에 따라 일부 차이가 있어 v2 default 표를 명시한다. 신살은 표시·해석 보조용이며
용신/신강약/격국 결정에 직접 쓰지 않는다.
"""

from __future__ import annotations

from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S

# 카테고리 + 길흉 성향 + 해석 태그.
CATALOG_META: dict[str, dict] = {
    # 12신살
    "지살": {"category": "movement_change", "polarity": "neutral", "tags": ["이동", "시작"]},
    "년살": {"category": "relationship_social", "polarity": "neutral", "tags": ["도화", "매력"]},
    "월살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["고갈", "정체"]},
    "망신살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["노출", "구설"]},
    "장성살": {"category": "wealth_status", "polarity": "positive", "tags": ["권위", "리더십"]},
    "반안살": {"category": "wealth_status", "polarity": "positive", "tags": ["안정", "출세"]},
    "역마살": {"category": "movement_change", "polarity": "neutral", "tags": ["이동", "변동"]},
    "육해살": {"category": "health_risk", "polarity": "caution", "tags": ["지체", "질병"]},
    "화개살": {"category": "spiritual_intuition", "polarity": "neutral", "tags": ["예술", "고독"]},
    "겁살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["손실", "강탈"]},
    "재살": {"category": "health_risk", "polarity": "caution", "tags": ["관재", "수옥"]},
    "천살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["천재", "불가항력"]},
    # 길신
    "천을귀인": {"category": "noble_stars", "polarity": "positive", "tags": ["귀인", "보호"]},
    "천덕귀인": {"category": "noble_stars", "polarity": "positive", "tags": ["덕", "보호"]},
    "월덕귀인": {"category": "noble_stars", "polarity": "positive", "tags": ["덕", "보호"]},
    "태극귀인": {"category": "noble_stars", "polarity": "positive", "tags": ["귀인", "복록"]},
    "문창귀인": {"category": "academic_document", "polarity": "positive", "tags": ["학문", "총명"]},
    "학당귀인": {"category": "academic_document", "polarity": "positive", "tags": ["학문", "교육"]},
    "금여": {"category": "wealth_status", "polarity": "positive", "tags": ["복록", "배우자복"]},
    "암록": {"category": "wealth_status", "polarity": "positive", "tags": ["숨은 복록", "조력"]},
    "도화": {"category": "relationship_social", "polarity": "neutral", "tags": ["매력", "인기"]},
    "홍염": {"category": "relationship_social", "polarity": "neutral", "tags": ["매력", "끼"]},
    # 흉신/주의
    "양인": {"category": "health_risk", "polarity": "caution", "tags": ["과강", "사고", "수술"]},
    "괴강": {"category": "health_risk", "polarity": "caution", "tags": ["극단", "강건", "리더"]},
    "백호": {"category": "health_risk", "polarity": "caution", "tags": ["혈광", "사고"]},
    "현침": {"category": "health_risk", "polarity": "caution", "tags": ["바늘", "수술", "예리"]},
    "귀문관살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["예민", "직관"]},
    "원진": {"category": "isolation_conflict", "polarity": "caution", "tags": ["반목", "원망"]},
    # 공망은 신살과 별개 레이어(StructureAnalysis.gongmang)로 표시한다.
}

ALL_CATEGORIES = [
    "twelve_sinsal", "noble_stars", "academic_document", "movement_change",
    "relationship_social", "isolation_conflict", "health_risk", "wealth_status",
    "spiritual_intuition", "miscellaneous",
]

TWELVE_SINSAL_ORDER = [
    "겁살", "재살", "천살", "지살", "년살", "월살",
    "망신살", "장성살", "반안살", "역마살", "육해살", "화개살",
]

# 삼합 생지(生支)
TRINE_SAENGJI: dict[B, B] = {}
for _members, _gen in [
    ((B.SIN, B.JA, B.JIN), B.SIN),   # 申子辰 水
    ((B.IN, B.O, B.SUL), B.IN),       # 寅午戌 火
    ((B.SA, B.YU, B.CHUK), B.SA),     # 巳酉丑 金
    ((B.HAE, B.MYO, B.MI), B.HAE),    # 亥卯未 木
]:
    for _b in _members:
        TRINE_SAENGJI[_b] = _gen

# trine 기반 단일 신살 (생지별 target)
YEOKMA: dict[B, B] = {B.SIN: B.IN, B.IN: B.SIN, B.SA: B.HAE, B.HAE: B.SA}
DOHWA: dict[B, B] = {B.SIN: B.YU, B.IN: B.MYO, B.SA: B.O, B.HAE: B.JA}
HWAGAE: dict[B, B] = {B.SIN: B.JIN, B.IN: B.SUL, B.SA: B.CHUK, B.HAE: B.MI}

# 천을귀인 (일간 → 지지 2개)
CHEONEUL: dict[S, list[B]] = {
    S.GAP: [B.CHUK, B.MI], S.MU: [B.CHUK, B.MI], S.GYEONG: [B.CHUK, B.MI],
    S.EUL: [B.JA, B.SIN], S.GI: [B.JA, B.SIN],
    S.BYEONG: [B.HAE, B.YU], S.JEONG: [B.HAE, B.YU],
    S.SIN: [B.IN, B.O], S.IM: [B.MYO, B.SA], S.GYE: [B.MYO, B.SA],
}

# 태극귀인 (일간 → 지지)
TAEGEUK: dict[S, list[B]] = {
    S.GAP: [B.JA, B.O], S.EUL: [B.JA, B.O],
    S.BYEONG: [B.MYO, B.YU], S.JEONG: [B.MYO, B.YU],
    S.MU: [B.JIN, B.SUL, B.CHUK, B.MI], S.GI: [B.JIN, B.SUL, B.CHUK, B.MI],
    S.GYEONG: [B.IN, B.HAE], S.SIN: [B.IN, B.HAE],
    S.IM: [B.SA, B.SIN], S.GYE: [B.SA, B.SIN],
}

# 문창귀인 (일간 → 지지)
MUNCHANG: dict[S, B] = {
    S.GAP: B.SA, S.EUL: B.O, S.BYEONG: B.SIN, S.JEONG: B.YU, S.MU: B.SIN,
    S.GI: B.YU, S.GYEONG: B.HAE, S.SIN: B.JA, S.IM: B.IN, S.GYE: B.MYO,
}

# 양인 (양간 → 지지)
YANGIN: dict[S, B] = {S.GAP: B.MYO, S.BYEONG: B.O, S.MU: B.O, S.GYEONG: B.YU, S.IM: B.JA}

# 홍염 (일간 → 지지)
HONGYEOM: dict[S, B] = {
    S.GAP: B.O, S.EUL: B.O, S.BYEONG: B.IN, S.JEONG: B.MI, S.MU: B.JIN,
    S.GI: B.JIN, S.GYEONG: B.SUL, S.SIN: B.YU, S.IM: B.JA, S.GYE: B.SIN,
}

# 금여 (일간 → 지지)
GEUMYEO: dict[S, B] = {
    S.GAP: B.JIN, S.EUL: B.SA, S.BYEONG: B.MI, S.JEONG: B.SIN, S.MU: B.MI,
    S.GI: B.SIN, S.GYEONG: B.SUL, S.SIN: B.HAE, S.IM: B.CHUK, S.GYE: B.IN,
}

# 암록 (일간 → 지지, 건록의 육합)
AMROK: dict[S, B] = {
    S.GAP: B.HAE, S.EUL: B.SUL, S.BYEONG: B.SIN, S.JEONG: B.MI, S.MU: B.SIN,
    S.GI: B.MI, S.GYEONG: B.SA, S.SIN: B.JIN, S.IM: B.IN, S.GYE: B.CHUK,
}

# 월덕귀인 (월지 삼합국 → 천간)
WOLDEOK: dict[B, S] = {
    B.IN: S.BYEONG, B.O: S.BYEONG, B.SUL: S.BYEONG,
    B.SIN: S.IM, B.JA: S.IM, B.JIN: S.IM,
    B.HAE: S.GAP, B.MYO: S.GAP, B.MI: S.GAP,
    B.SA: S.GYEONG, B.YU: S.GYEONG, B.CHUK: S.GYEONG,
}

# 천덕귀인 (월지 → 천간 또는 지지)
CHEONDEOK: dict[B, object] = {
    B.IN: S.JEONG, B.MYO: B.SIN, B.JIN: S.IM, B.SA: S.SIN, B.O: B.HAE, B.MI: S.GAP,
    B.SIN: S.GYE, B.YU: B.IN, B.SUL: S.BYEONG, B.HAE: S.EUL, B.JA: B.SA, B.CHUK: S.GYEONG,
}

# 괴강 / 백호 (일주/주 간지)
GOEGANG: set[tuple[S, B]] = {
    (S.GYEONG, B.JIN), (S.GYEONG, B.SUL), (S.IM, B.JIN), (S.MU, B.SUL),
}
BAEKHO: set[tuple[S, B]] = {
    (S.GAP, B.JIN), (S.EUL, B.MI), (S.BYEONG, B.SUL), (S.JEONG, B.CHUK),
    (S.MU, B.JIN), (S.IM, B.SUL), (S.GYE, B.CHUK),
}

# 귀문관살 / 원진 (지지 쌍)
GWIMUN: set[frozenset[B]] = {
    frozenset({B.JA, B.YU}), frozenset({B.CHUK, B.O}), frozenset({B.IN, B.MI}),
    frozenset({B.MYO, B.SIN}), frozenset({B.JIN, B.HAE}), frozenset({B.SA, B.SUL}),
}
WONJIN: set[frozenset[B]] = {
    frozenset({B.JA, B.MI}), frozenset({B.CHUK, B.O}), frozenset({B.IN, B.YU}),
    frozenset({B.MYO, B.SIN}), frozenset({B.JIN, B.HAE}), frozenset({B.SA, B.SUL}),
}

# 현침 (글자)
HYEONCHIM_STEMS: set[S] = {S.GAP, S.SIN}
HYEONCHIM_BRANCHES: set[B] = {B.MYO, B.O, B.SIN}
