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
    # 추가 길성 (표준 명리표)
    "천록귀인": {"category": "wealth_status", "polarity": "positive", "tags": ["건록", "복록"]},
    "천주귀인": {"category": "noble_stars", "polarity": "positive", "tags": ["식록", "의식주"]},
    "관귀학관": {"category": "academic_document", "polarity": "positive", "tags": ["관운", "승진"]},
    "문곡귀인": {"category": "academic_document", "polarity": "positive", "tags": ["학문", "예술"]},
    "일덕": {"category": "noble_stars", "polarity": "positive", "tags": ["덕", "자비"]},
    "일귀": {"category": "noble_stars", "polarity": "positive", "tags": ["귀인", "품격"]},
    "천의성": {"category": "spiritual_intuition", "polarity": "positive", "tags": ["의약", "치유"]},
    "천문성": {"category": "spiritual_intuition", "polarity": "positive", "tags": ["종교", "직관"]},
    # 추가 흉살 (표준 명리표)
    "낙정관살": {"category": "health_risk", "polarity": "caution", "tags": ["함정", "수액"]},
    "비인살": {"category": "health_risk", "polarity": "caution", "tags": ["충동", "칼날"]},
    "격각살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["단절", "이별"]},
    "천라지망살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["속박"]},
    "고신살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["고독", "고립"]},
    "과숙살": {"category": "isolation_conflict", "polarity": "caution", "tags": ["고독", "이별"]},
    "단교관살": {"category": "health_risk", "polarity": "caution", "tags": ["낙상", "수족"]},
    "협록": {"category": "wealth_status", "polarity": "positive", "tags": ["록", "협조"]},
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

# 역마·도화·화개 — 지지 글자(글자살) 기준. 사생지=역마 / 사정지=도화 / 사고지=화개.
# (위치별 12신살 전체는 펼치지 않고 이 셋만 글자로 본다.)
SASAENG: frozenset[B] = frozenset({B.IN, B.SIN, B.SA, B.HAE})   # 寅申巳亥 역마
SAJEONG: frozenset[B] = frozenset({B.JA, B.O, B.MYO, B.YU})      # 子午卯酉 도화
SAGO: frozenset[B] = frozenset({B.JIN, B.SUL, B.CHUK, B.MI})     # 辰戌丑未 화개

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

# ---------------------------------------------------------------------------
# 추가 신살 표준표 (myeongli 참고 — 파일 인코딩 손상으로 표준 명리표로 재작성).
# 각 표의 근거를 주석으로 명시한다.
# ---------------------------------------------------------------------------

# 자(子)~해(亥) 순서(인덱스 0~11). BRANCH_INDEX와 동일 순서.
_BRANCH_SEQ = [B.JA, B.CHUK, B.IN, B.MYO, B.JIN, B.SA, B.O, B.MI, B.SIN, B.YU, B.SUL, B.HAE]


def branch_at(idx: int) -> B:
    """순환 인덱스로 지지 반환(자=0…해=11)."""
    return _BRANCH_SEQ[idx % 12]


# 천록귀인 = 일간의 건록(정록)지. 甲寅 乙卯 丙戊巳 丁己午 庚申 辛酉 壬亥 癸子.
CHEONROK: dict[S, B] = {
    S.GAP: B.IN, S.EUL: B.MYO, S.BYEONG: B.SA, S.JEONG: B.O, S.MU: B.SA,
    S.GI: B.O, S.GYEONG: B.SIN, S.SIN: B.YU, S.IM: B.HAE, S.GYE: B.JA,
}

# 천주귀인 = 일간 식신의 건록지. 甲巳 乙午 丙巳 丁午 戊申 己酉 庚亥 辛子 壬寅 癸卯.
CHEONJU: dict[S, B] = {
    S.GAP: B.SA, S.EUL: B.O, S.BYEONG: B.SA, S.JEONG: B.O, S.MU: B.SIN,
    S.GI: B.YU, S.GYEONG: B.HAE, S.SIN: B.JA, S.IM: B.IN, S.GYE: B.MYO,
}

# 관귀학관 = 일간 관성(정관)의 장생지. 木巳 火申 土亥 金寅 水申.
GWANGWI: dict[S, B] = {
    S.GAP: B.SA, S.EUL: B.SA, S.BYEONG: B.SIN, S.JEONG: B.SIN, S.MU: B.HAE,
    S.GI: B.HAE, S.GYEONG: B.IN, S.SIN: B.IN, S.IM: B.SIN, S.GYE: B.SIN,
}

# 문곡귀인 = 문창귀인의 대충(對沖). 甲亥 乙子 丙戊寅 丁己卯 庚巳 辛午 壬申 癸酉.
MUNGOK: dict[S, B] = {
    S.GAP: B.HAE, S.EUL: B.JA, S.BYEONG: B.IN, S.JEONG: B.MYO, S.MU: B.IN,
    S.GI: B.MYO, S.GYEONG: B.SA, S.SIN: B.O, S.IM: B.SIN, S.GYE: B.YU,
}

# 낙정관살(落井關殺) — 일간 기준. 甲己巳 乙庚子 丙辛申 丁壬戌 戊癸卯.
NAKJEONG: dict[S, B] = {
    S.GAP: B.SA, S.GI: B.SA, S.EUL: B.JA, S.GYEONG: B.JA, S.BYEONG: B.SIN,
    S.SIN: B.SIN, S.JEONG: B.SUL, S.IM: B.SUL, S.MU: B.MYO, S.GYE: B.MYO,
}

# 비인살(飛刃殺) = 양인의 대충(양간만). 甲酉 丙子 戊子 庚卯 壬午.
BIIN: dict[S, B] = {
    S.GAP: B.YU, S.BYEONG: B.JA, S.MU: B.JA, S.GYEONG: B.MYO, S.IM: B.O,
}

# 단교관살(斷橋關殺) — 월지 기준(고전표).
# 寅寅 卯卯 辰申 巳丑 午戌 未酉 申辰 酉巳 戌午 亥未 子亥 丑子.
DANGYO: dict[B, B] = {
    B.IN: B.IN, B.MYO: B.MYO, B.JIN: B.SIN, B.SA: B.CHUK, B.O: B.SUL,
    B.MI: B.YU, B.SIN: B.JIN, B.YU: B.SA, B.SUL: B.O, B.HAE: B.MI,
    B.JA: B.HAE, B.CHUK: B.JA,
}

# 고신살(孤神殺) — 년지 삼방 기준. 亥子丑→寅 / 寅卯辰→巳 / 巳午未→申 / 申酉戌→亥.
GOSHIN: dict[B, B] = {
    B.HAE: B.IN, B.JA: B.IN, B.CHUK: B.IN,
    B.IN: B.SA, B.MYO: B.SA, B.JIN: B.SA,
    B.SA: B.SIN, B.O: B.SIN, B.MI: B.SIN,
    B.SIN: B.HAE, B.YU: B.HAE, B.SUL: B.HAE,
}

# 과숙살(寡宿殺) — 년지 삼방 기준. 亥子丑→戌 / 寅卯辰→丑 / 巳午未→辰 / 申酉戌→未.
GWASUK: dict[B, B] = {
    B.HAE: B.SUL, B.JA: B.SUL, B.CHUK: B.SUL,
    B.IN: B.CHUK, B.MYO: B.CHUK, B.JIN: B.CHUK,
    B.SA: B.JIN, B.O: B.JIN, B.MI: B.JIN,
    B.SIN: B.MI, B.YU: B.MI, B.SUL: B.MI,
}

# 일덕(日德) — 특정 일주. 甲寅 丙辰 戊辰 庚辰 壬戌.
ILDEOK: set[tuple[S, B]] = {
    (S.GAP, B.IN), (S.BYEONG, B.JIN), (S.MU, B.JIN), (S.GYEONG, B.JIN), (S.IM, B.SUL),
}

# 일귀(日貴) — 특정 일주. 丁酉 丁亥 癸巳 癸卯.
ILGWI: set[tuple[S, B]] = {
    (S.JEONG, B.YU), (S.JEONG, B.HAE), (S.GYE, B.SA), (S.GYE, B.MYO),
}

# 천문성(天門星) — 일지 戌·亥. 천라지망: 戌亥(천라)·辰巳(지망) 모두 존재 시.
CHEONMUN_BRANCHES: set[B] = {B.SUL, B.HAE}
CHEONRA = (B.SUL, B.HAE)   # 천라
JIMANG = (B.JIN, B.SA)     # 지망
