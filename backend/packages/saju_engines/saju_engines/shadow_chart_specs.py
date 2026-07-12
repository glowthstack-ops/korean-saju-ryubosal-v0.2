"""Shadow 차트 구조 사양 24개 — 그룹 1~7 coverage(도메인 4개는 별도 chat snapshot, 제외).

각 ChartSpec 은 required(전부 만족=FOUND)·critical(best_match 라도 필수)·preferred(가점)·
expected_shadow(사후검증)·invariants(불변)·best_match_allowed(희귀 구조만)로 구성한다.
find_shadow_charts.py 가 합성 birth 후보를 이 사양으로 검증해 채택한다.

규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §13-5
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import shadow_chart_predicates as P
from .shadow_chart_predicates import Pred

_WEAK = ["극신약", "태신약", "신약", "중화신약"]


@dataclass
class ChartSpec:
    chart_id: str
    target: str
    required: list[Pred]
    critical: list[Pred] = field(default_factory=list)   # best_match 라도 필수
    preferred: list[Pred] = field(default_factory=list)
    expected_shadow: Pred | None = None
    invariants: list[Pred] = field(default_factory=list)
    best_match_allowed: bool = False
    notes: str = ""


SPECS: list[ChartSpec] = [
    # ── 그룹 1: 관살/살인상생/조건부 병 ──
    # 희신 과다 교정(2026-07-12) 후 관살태왕의 官殺은 final 한신 강등 → '조건부 한신/병'.
    ChartSpec(
        "kansal_taewang_01", "관살태왕 신약 — 官殺 조건부 한신/병",
        required=[P.strength_in(_WEAK), P.dominant_group("officer"),
                  P.has_operational_role("조건부 한신/병")],
        expected_shadow=P.expect_role_shadow_down("조건부 한신/병"),
        notes="官殺 과발동 방지 핵심",
    ),
    ChartSpec(
        "sarin_sangsaeng_01", "살인상생 — 印 용신·官殺 조건부",
        required=[P.dominant_group("officer"), P.has_operational_role("조건부 한신/병")],
        preferred=[P.strength_in(_WEAK)],
        expected_shadow=P.expect_role_shadow_down("조건부 한신/병"),
        notes="살인상생형 일반화",
    ),
    ChartSpec(
        "conditional_byeong_water_01", "水 과다 조건부 희신/병",
        required=[P.element_pct_ge("水", 40), P.has_operational_role("조건부 희신/병")],
        expected_shadow=P.expect_role_shadow_down("조건부 희신/병"),
        notes="비겁 희신이 한습 조후 역행으로 강등되는 류(예: 己酉/丁丑/癸巳) 재현",
    ),
    # ── 그룹 2: 조후보조신 ──
    ChartSpec(
        "johu_cold_01", "한습(子/丑/亥월) 신약 — 火 조후보조신",
        required=[P.month_branch_in(["子", "丑", "亥"]),
                  P.has_operational_role("조후보조신")],
        preferred=[P.strength_in(_WEAK)],
        notes="한신→조후 격상 검증",
    ),
    ChartSpec(
        "johu_hot_01", "조열(午/未/巳월) — 조후보조신",
        required=[P.month_branch_in(["午", "未", "巳"]),
                  P.has_operational_role("조후보조신")],
        notes="반대 방향 조후",
    ),
    # ── 그룹 3: 용신 작동성 저하(factor별) ──
    ChartSpec("yongsin_no_transmit_01", "용신 투간無",
              required=[P.yongsin_factor("no_transmit")],
              expected_shadow=P.expect_yongsin_shadow_down(), notes="작동성 미발동"),
    ChartSpec("yongsin_no_root_01", "용신 통근無",
              required=[P.yongsin_factor("no_root")],
              expected_shadow=P.expect_yongsin_shadow_down()),
    ChartSpec("yongsin_gongmang_01", "용신 공망",
              required=[P.yongsin_factor("yongsin_void")],
              expected_shadow=P.expect_yongsin_shadow_down()),
    ChartSpec("yongsin_clash_01", "용신 충",
              required=[P.yongsin_factor("yongsin_clash")],
              expected_shadow=P.expect_yongsin_shadow_down()),
    ChartSpec("yongsin_gyeokgak_zimao_01", "子卯 격각 통관손상",
              required=[P.yongsin_factor("gyeokgak_zimao")],
              expected_shadow=P.expect_yongsin_shadow_down()),
    ChartSpec("yongsin_isolation_01", "용신 고립",
              required=[P.yongsin_factor("yongsin_isolation")],
              expected_shadow=P.expect_yongsin_shadow_down()),
    ChartSpec("yongsin_bound_01", "용신 합반(operability factor)",
              required=[P.yongsin_factor("yongsin_bound")],
              expected_shadow=P.expect_yongsin_shadow_down(),
              notes="용신 천간 bind/contend → operability 하향(일반 합맥락과 분리)"),
    # ── 그룹 4: 조건부 제살보조 ──
    ChartSpec(
        "jesal_assist_earth_01", "水 과다의 土 — 조건부 제살보조",
        required=[P.element_pct_ge("水", 40), P.has_operational_role("조건부 제살보조")],
        expected_shadow=P.expect_role_shadow_down("조건부 제살보조"),
        notes="구신→완화, 과한 길신 승격 금지",
    ),
    # ── 그룹 5: 과다/신약 구조 ──
    ChartSpec("jaeda_sinyak_01", "재다신약",
              required=[P.strength_in(_WEAK), P.dominant_group("wealth")],
              notes="신약 재성 위험"),
    ChartSpec("inseong_gwada_01", "인성과다",
              required=[P.dominant_group("resource")],
              preferred=[P.strength_in(["중화신강", "신강", "태신강", "극신강"])],
              notes="인성 과다 병"),
    ChartSpec("siksang_gwada_01", "식상과다",
              required=[P.dominant_group("output")], notes="설기 과다"),
    ChartSpec("bigyeop_gwada_01", "비겁과다",
              required=[P.dominant_group("peer")], notes="군겁쟁재"),
    # ── 그룹 6: 합 맥락 ──
    ChartSpec(
        "hap_confirmed_01", "합화 confirmed — transform note only·불변",
        required=[P.confirmed_transform()],
        critical=[P.confirmed_transform()],
        invariants=[P.invariant_additive()],
        best_match_allowed=True,
        notes="role 전환·세력 재산정 아님 — transform note only, final/groups/분포/scoring 불변",
    ),
    ChartSpec(
        "hap_bind_01", "일반 합반(bind) 맥락 — ten_god/officer note enrich",
        required=[P.bind_transform(), P.hap_note_enriched()],
        critical=[P.bind_transform()],
        best_match_allowed=True,
        notes="일반 십성 element bind(용신 operability factor 와 분리)",
    ),
    ChartSpec(
        "hap_contend_01", "쟁합(contend)",
        required=[P.contend_transform()],
        critical=[P.contend_transform()],
        best_match_allowed=True, notes="동일 천간 2개 같은 합 파트너 다툼",
    ),
    ChartSpec(
        "hap_away_01", "합거(away) 근사 — 化 미성립 합이 기신/구신 묶음",
        required=[P.away_transform()],
        critical=[P.away_transform()],
        best_match_allowed=True, notes="제외 처리 오작동 방지(희귀·미확보 가능)",
    ),
    # ── 그룹 7: 특수격 후보(희귀·best_match 허용) ──
    ChartSpec(
        "jonggyeok_01", "종격 후보(종재/종살/종아 — follow)",
        required=[P.special_pattern_type("follow")],
        critical=[P.special_pattern_type("follow")],
        best_match_allowed=True, notes="극신약+무근 순응(종격)",
    ),
    ChartSpec(
        "jeonwang_01", "전왕격/일행득기(곡직/염상/가색/종혁/윤하 — dominant)",
        required=[P.special_pattern_type("dominant")],
        critical=[P.special_pattern_type("dominant")],
        best_match_allowed=True, notes="단일 오행 60%+ 지배",
    ),
    ChartSpec(
        "special_gyeok_01", "특수격(양인/건록 등)",
        required=[P.geokguk_special(["양인", "건록", "월겁", "록"])],
        critical=[P.geokguk_special(["양인", "건록", "월겁", "록"])],
        best_match_allowed=True, notes="격국 다양성",
    ),
]

SCHEMA_VERSION = "shadow_charts_v1"
