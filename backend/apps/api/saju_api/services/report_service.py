"""보고서 생성 서비스 (v2.2.1 PR-E — Phase 9 파이프라인 운영 배선, docs/10).

ReportBuilder(테스트 전용이던 골격)에 **실데이터 컨텍스트 빌더**와 LLM 호출을
주입한다. 섹션 프롬프트 = 고정 prefix(원국·명식 구조+해석 자료 — 대화와 동일,
캐시 적중) + 섹션 과제 + 섹션별 데이터 블록(대운표·이벤트 후보·근거 경로).

분석은 엔진(만세 계산·스코어링)이, 본 서비스는 직렬화와 호출만 한다.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from saju_manse_analysis.luck.luck_calendar import luck_month_label

from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.compatibility_engine import analyze_compatibility, compatibility_lines
from saju_engines.context_reducer import (
    _DOMAIN_EVENT_KEYS,
    _PROFILE_FACTS_INSTRUCTION,
    _STRUCTURE_PATTERN_INSTRUCTION,
    build_birth_summary,
    first_sentence,
    serialize_chart_prefix,
)
from saju_engines.daewoon_progression import resolve_all_daewoon_progressions
from saju_engines.direction_suggestion import (
    DIRECTION_SUGGESTION_INSTRUCTION,
    detect_direction_suggestions,
    format_direction_suggestion_lines,
    select_direction_suggestions,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import confirmed_yongsin_note, favorability_map
from saju_engines.hap_lines import luck_hap_mode_lines
from saju_engines.health_vulnerability import analyze_health_vulnerability
from saju_engines.llm_guard import TokenBudgetExceeded
from saju_engines.manifestation_branch import branch_summary
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_engines.palace_relationship_network import (
    analyze_palace_network,
    palace_network_lines,
)
from saju_engines.preparation_context import build_preparation_context
from saju_engines.profile_engine import profile_event_signals, profile_facts_lines
from saju_engines.relationship_hints import relation_context_lines
from saju_engines.report_builder import ReportBuilder
from saju_engines.report_event_input import (
    month_overview_lines,
    precise_candidate_clusters,
    score_table_lines,
    year_spectrum_lines,
)
from saju_engines.report_plan import YONGSIN_SECTIONS, build_section_plans
from saju_engines.structural_context import (
    AVOID_DATE_CERTAINTY_DIRECTIVE,
    DECISION_ATTITUDE_DIRECTIVE,
    GONGMANG_ACTIVATION_DIRECTIVE,
    KEYWORD_COMBO_TRANSLATION_DIRECTIVE,
    MANAGE_NOT_OVERCOME_DIRECTIVE,
    NON_NORMATIVE_REASSURANCE_DIRECTIVE,
    RELATIONSHIP_SELF_AWARENESS_DIRECTIVE,
    TENDENCY_SHIFT_DIRECTIVE,
    UNCERTAINTY_TRANSLATION_DIRECTIVE,
    activity_keyword_lines,
    era_energy_lines,
    external_impression_lines,
    health_lines,
    marriage_age_prior_lines,
    marriage_resource_lines,
    preparation_context_lines,
    remedy_action_lines,
    spouse_star_directive,
    wealth_capacity_lines,
    wealth_status_lines,
)
from saju_engines.structural_context import (
    DAEWOON_FRAMING_DIRECTIVE as _DAEWOON_FRAMING_DIRECTIVE,
)
from saju_engines.structural_context import (
    DAEWOON_TRANSITION_SIGNALS_DIRECTIVE as _DAEWOON_TRANSITION_SIGNALS_DIRECTIVE,
)
from saju_engines.structural_context import (
    PROGRESSION_MODE_KO as _PROGRESSION_MODE_KO,
)
from saju_engines.structural_context import (
    daewoon_progression_lines as _daewoon_progression_lines,
)
from saju_engines.structure_patterns import (
    detect_structure_patterns,
    select_llm_patterns,
)
from saju_engines.task_procedures import TASK_PACKS, procedure_reference_block
from saju_engines.topic_builder import MODULES as _TOPIC_MODULES
from saju_engines.topic_builder import build_topic_context
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_engines.wealth_status_lean import analyze_wealth_status_lean
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.constants import BRANCH_KO, STEM_KO
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN as _EVENT_DOMAIN_V2
from saju_shared_types.events import EventCandidate, EventPolarity
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectKind
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.report import ReportResult, ReportSpec, SectionContext, SectionPlan
from saju_shared_types.topic_context import PeriodSpec as _TopicPeriodSpec

from . import llm_client
from .manse_service import calculate, luck_months
from .personalization import (
    fetch_calibration_expression_hints,
    fetch_confirmed_yongsin_override,
    fetch_personal_inputs,
)

_logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_SCORE_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}
_TOP_CANDIDATES = 8
# Context Reduction(report 경로, docs/09 L333) 최대 단계 — 1=다년 월별 흐름 ★주목 축소,
# 2=연도별 흐름도 ★주목 축소. 섹션 입력이 토큰 상한을 넘을 때만 단계가 올라간다(상한 내=0단계).
_MAX_REPORT_REDUCTION = 2

# [월별 흐름] 헤더 공통 꼬리 — 전체/축소(★주목) 양쪽 동일 서술 가이드(길흉=운 품질 1차 기준).
_MONTH_FLOW_GUIDE_TAIL = (
    "좋은 달과 주의할 달의 1차 기준은 사건 밀도가 아니라 각 달의 운 품질 등급〈…〉"
    "('강한 용신운'>'용신운(부분)'>'혼합'>'기신운')이며, 사건(이직·이사 등)은 그 위에 십성으로 "
    "얹어 '무슨 일'을 설명한다. '강한 용신운' 달은 두드러진 사건이 없어도 기반이 가장 좋은"
    "(가장 도움되는) 달로 짚고, 각 달 기운의 활용·대비 방향도 곁들일 것."
)
# 지역 추천(거주지 평가 + 추천) — compiled 미빌드 시 None(graceful).
_COMPILED = _BACKEND / "compiled"
_region_orch: object | None = None
_region_orch_init = False


def _get_region_orchestrator() -> object | None:
    """지역 추천 오케스트레이터 lazy 싱글턴. compiled 프로필·행정 registry 필요(미빌드면 None)."""
    global _region_orch, _region_orch_init
    if _region_orch_init:
        return _region_orch
    _region_orch_init = True
    profiles = _COMPILED / "region_element_profiles_v1.json"
    admin = _COMPILED / "region_admin_units_v1.json"
    if not (profiles.exists() and admin.exists()):
        return None
    from saju_engines.region_element_engine import RegionElementEngine
    from saju_engines.region_geo_stubs import DirectionalFeatureAdapter
    from saju_engines.region_recommendation_orchestrator import (
        RegionRecommendationOrchestrator,
    )

    directional = _COMPILED / "region_directional_summary_v1.json"
    engine = RegionElementEngine(_DICTS, profiles, admin)
    _region_orch = RegionRecommendationOrchestrator(
        engine,
        DirectionalFeatureAdapter(directional if directional.exists() else None),
    )
    return _region_orch


def _residence_region(owner_id: str | None) -> str | None:
    """소유자 프로필의 거주 지역(없으면 None, 무DB/미설정 graceful)."""
    if owner_id is None:
        return None
    try:
        from .personalization import _get_profile_store

        store = _get_profile_store()
        if store is None:
            return None
        profile = store.load(owner_id)
        if profile is None or profile.extended is None or profile.extended.residence is None:
            return None
        return profile.extended.residence.region or None
    except Exception:  # noqa: BLE001 — 프로필 조회 실패가 리포트를 막지 않도록
        return None


def _load_extended_profile(subject_id: str | None):
    """subject 확장 프로필(물상 사실 맥락 주입용). 무DB/미설정/부재는 graceful None."""
    if subject_id is None:
        return None
    try:
        from .personalization import _get_profile_store

        store = _get_profile_store()
        if store is None:
            return None
        profile = store.load(subject_id)
        return profile.extended if profile is not None else None
    except Exception:  # noqa: BLE001 — 프로필 조회 실패가 리포트를 막지 않도록
        return None


# 이벤트 종류 → 도메인(21키 EventKeyV2 기준, Phase 7). FOCUS 주제 스코핑에 쓴다.
_EVENT_DOMAIN: dict[str, str] = {str(k): v for k, v in _EVENT_DOMAIN_V2.items()}
_TOPIC_DOMAINS = set(_EVENT_DOMAIN.values())
# 예측(향후 N년) 테마 — 과거가 아닌 오늘 이후를 앵커링할 주제(총운/궁합 비교는 제외).
_FORECAST_TOPICS = {"career", "wealth", "relationship"}


_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")  # 연속 빈 줄(2줄 초과)
_TRAIL_WS = re.compile(r"[ \t]+\n")  # 줄 끝 공백
# 본문 끝에 누출된 '근거 경로: …' 줄(내부 근거) — 결정적 제거(2026-06-16, 순화).
_EVIDENCE_LINE = re.compile(r"(?m)^[ \t]*근거 경로\s*[:：].*$")


def _tighten(text: str) -> str:
    """LLM 출력의 지면 낭비 정규화 — 연속 빈 줄을 1개로, 줄 끝 공백 제거(공백수정 안전망).

    프롬프트 지시(지면 절약)를 LLM이 어겨도 렌더 페이지가 부풀지 않도록 후처리한다.
    마크다운 표·문단 구분에 필요한 빈 줄 1개는 보존한다. 아울러 내부 근거인 '근거 경로:'
    줄이 본문에 그대로 노출된 경우(전문용어 누출) 결정적으로 제거한다.
    """
    text = _EVIDENCE_LINE.sub("", text)
    text = _TRAIL_WS.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


# 서두 반복 금지 재료로 보관하는 직전 섹션 첫 문장 개수 — 너무 많으면 프롬프트만 길어진다.
_MAX_RECENT_OPENINGS = 3


def _period_end_month(period: str) -> str:
    """기간의 끝 달(YYYY-MM) — 연('2026')=그 해 12월, 월('2026-02')=그대로, 일=그 달."""
    if len(period) == 4:
        return f"{period}-12"
    if len(period) == 7:
        return period
    return period[:7]


# 다년 월운·세운 스펙트럼이 다룰 예측 연도 폭(향후 N년). 월운은 비용·토큰을 감안해 +5년까지만
# 생성한다(그 이상은 세운 단위로 충분 — docs/10 FOCUS 스코프 '현재월~+5년'과 정합).
_FORECAST_FORWARD_YEARS = 5


def _forecast_years(spec: ReportSpec, today: date) -> list[int]:
    """월운 생성·세운 스펙트럼이 다룰 연도 목록(오늘 연도 ~ min(기간 끝, 오늘+5년)).

    RPT_YEAR는 단일 대상 연도(미래 연도 가능)만 생성한다. 그 외(FOCUS·FULL)는 향후 창으로
    한정해 과거 달까지 대량 생성하지 않는다(과거 월 디테일은 세운/검증 섹션이 담당).
    """
    start_raw, end_raw = spec.period.start[:4], spec.period.end[:4]
    if spec.product_code == "RPT_YEAR" and start_raw.isdigit():
        return [int(start_raw)]
    lo = today.year
    hi = lo + _FORECAST_FORWARD_YEARS
    if end_raw.isdigit():
        hi = min(hi, max(int(end_raw), lo))
    return list(range(lo, hi + 1))


# 섹션별 작성 지침(docs/10 3·4장 데이터소스 요약 — 목차 규격은 report_plan이 강제).
_SECTION_GUIDES: dict[str, str] = {
    "F-01": "사주 원국의 전체 그림을 소개할 것 — 4주 구성과 각 주의 십성·운성을 쉬운 비유로.",
    "F-02": "일간 글자의 물상과 일주 서사를 중심으로 타고난 기질을 풀어낼 것.",
    "F-03": "원국 십성 구성([명식 해석 자료]의 십성 발췌)을 엮어 사회적 성향을 서술할 것.",
    "F-04": "강약·격국·용신 판정과 그 근거를 설명할 것 — 용신 오행을 명시적으로 표기할 것.",
    "F-05": "신살·공망·특수 구조를 양면(빛/그림자)으로 설명할 것 — 신살은 보조 자료임을 전제. "
    "각 신살(길성·흉살)은 그 주의 정점 시기(년=초년·배경 / 월=청년·사회 / 일=중년·본인 / "
    "시=말년·결실)에 직접 작동하되, 정점 이전엔 잠재(늦게 발현)·정점 이후엔 배경·누적/잔존으로 "
    "평생 이어진다(초년 길성이 중년에 사라진다고 보지 말 것). 운이 그 자리를 합·충·형으로 "
    "건드리면 재활성되며, 그래도 단독 사건 단정은 금지(길성=완충·도움, 흉살=리스크·주의).",
    "F-06": "앞 섹션들의 재료를 종합해 성격·취향·행동 패턴의 이야기로 묶을 것.",
    # 2부 과거(F-07~F-09) — 시간범위를 '출생~현재'로 한정. 미래 연·월 사건 디테일은 3·4부
    # (현재 대운 정밀·향후 로드맵·고점 연도)의 몫이므로 여기서 끌어오지 말 것(데이터-목적 정합).
    "F-07": "출생부터 현재까지 거쳐 온 각 대운(10년)의 색깔과 전환점을 순서대로 짚어 인생 궤적을 "
    "그릴 것. 대운표의 '발현' 모드(계기 선인식→현실화 누적 경향과 그 예외)로 시기감을 주되, "
    "전반·후반 연차로 나눠 단정하지 말고, 특정 미래 연도·월의 사건 디테일(예: 몇 년 몇 월 "
    "이직)은 다루지 말 것 — 그건 뒤의 '현재 대운 정밀'·'향후 대운 로드맵' 섹션 몫이다. "
    "여기서는 대운 단위의 큰 흐름만.",
    "F-08": "과거 검증 신호(M14)를 토대로 지나온 시기의 주요 사건 가능성을 연도대별로 복원해 "
    "서술할 것. 대운표는 그 사건이 어느 대운기였는지 맥락으로만 쓰고, 미래 시점은 다루지 "
    "말 것.",
    "F-09": "사용자가 스스로 대조할 수 있도록 과거 검증 신호(M14)를 확인 포인트 체크리스트로 "
    "정리할 것 — 단정 말고 '이 무렵 이런 일이 있었는지' 묻는 형태. 미래 시점은 다루지 "
    "말 것.",
    "F-22": "이 섹션 끝에는 대운(생애)·세운·월운 간지 달력표가 엔진 계산값으로 자동 첨부된다. "
    "본문에서 간지 표를 직접 만들지 말 것(간지를 지어내면 안 됨) — 그 표를 어떻게 읽는지 "
    "(대운의 천간=계기·지지=현실 기반 역할, 세운·월운의 의미) 안내하고, 본문에 등장한 "
    "용어를 아래 [용어 사전] 기준으로 짧게 풀이하는 데 집중할 것.",
    "C-01": "주제와 기간의 핵심 신호를 3~5줄로 요약할 것.",
    "C-02": "주제와 관련된 원국 글자(십성·궁위·관계)만 골라 구조를 설명할 것.",
    "C-04": "이벤트 후보 표의 시기·점수·동반 신호를 타임라인으로 서술할 것.",
    "C-08": "점수표를 그대로 정리하고, 근거는 분류 용어 없이 일상어로 풀어 부록으로 제시할 것.",
    # ── 재물운 테마 전용(W-01~W-09) ──
    "W-01": "핵심만 5줄 이내로 요약할 것 — 어느 시점에 무엇이, 확장/변동/주의 중 무엇인지.",
    "W-02": "명식에서 드러나는 재물에 대한 성향·태도(정재/편재·안정/확장 지향)를 짧게 서술할 것.",
    "W-03": "재성(정재·편재)·재성궁(일지·월지)·식상생재 경로·재고 등 재물 '구조'만 설명할 것.",
    "W-04": "운에서 재물을 어떻게 모으고 키우는지(축재) 발현 형태를 서술할 것 — 발생≠결과.",
    "W-05": "횡재(편재)·상속(인성·재고)은 가능성으로만. 당첨·복권 단정 금지(로또 번호 거부).",
    "W-06": "향후 5년 재물 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "W-07": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "W-08": "행동 전략을 시기별로 구체화 — 확장/소액 검증/계약 보류/현금 확보/레버리지 금지 단위.",
    "W-09": "아래 점수표를 마크다운 표 형식(| ... |)과 구분선(|---|)까지 그대로 본문에 포함하라"
    "(이 부록 섹션은 평문 규칙의 예외 — 표 기호 유지). 표 안 수치·간지·방향은 한 글자도 바꾸지"
    " 말고, 표 밖에서 새 수치를 만들지 말 것. 표 위아래에 짧은 안내문만 덧붙여라.",
    # ── 직업·사업운 테마 전용(J-01~J-08) ──
    "J-01": "핵심만 5줄 이내로 요약할 것 — 어느 시점에 무엇이, 변동/안정/도전 중 무엇인지.",
    "J-02": "명식에 드러나는 일에 대한 태도(관성/식상·조직형/자유형, 안정/도전)를 짧게 서술할 것.",
    "J-03": "격국·관성(직장)·재성(사업·보상)·식상(표현·기술) 등 직업 '구조'만 설명할 것.",
    "J-04": "운에서 직업이 어떻게 움직이는지(이직·승진·창업·확장) 발현 형태만 — 발생≠결과.",
    "J-05": "향후 5년 직업 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "J-06": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것. 특정 달을 "
    "취업·합격 등 결과와 묶어 단정하지 말고 '움직임이 강해지는 창'으로 표현할 것.",
    "J-07": "행동 전략을 시기별로 — 이동/유지/준비/네트워킹/도전 보류 단위. 승진·합격 단정 금지.",
    "J-08": "아래 점수표를 마크다운 표 형식(| ... |)과 구분선(|---|)까지 그대로 본문에 포함하라"
    "(이 부록 섹션은 평문 규칙의 예외 — 표 기호 유지). 표 안 수치·간지·방향은 한 글자도 바꾸지"
    " 말고, 표 밖에서 새 수치를 만들지 말 것. 표 위아래에 짧은 안내문만 덧붙여라.",
    # ── 관계·애정운 테마 전용(R-01~R-08, 단독 모드 베이스) ──
    "R-01": "핵심만 5줄 이내로 — 어느 시점에 어떤 인연 에너지(만남/안정/갈등)가 활성인지.",
    "R-02": "명식에 드러나는 애정 성향(재성/관성·도화·표현 방식, 거리감/몰입)을 짧게 서술할 것.",
    "R-03": "일지(배우자궁)·재성/관성·도화/홍염 등 배우자·인연 '구조'만. 단정·낙인 표현 금지.",
    "R-04": "운에서 인연이 어떻게 움직이는지(만남·결혼 신호·갈등·정리) 발현 형태만 — 발생≠결과.",
    "R-05": "향후 5년 애정 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "R-06": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "R-07": "행동 전략을 — 다가서기/거리두기/대화/정리 준비 단위. 상대 강요·운명론 표현 금지. "
    "정리(이별·이혼)를 다룰 땐, 운이 저점인 시기엔 큰 결정을 서두르지 말고 보류·시간 "
    "견디기를 권하고(조급함 자체가 신호), 사유가 외도·폭력처럼 신뢰·안전이 깨지는 문제면 "
    "회복이 어려운 영역, 성격 차이·건강이면 노력·시간으로 달라질 수 있는 영역으로 결을 "
    "나눠 안내할 것.",
    "R-08": "아래 점수표를 마크다운 표 형식(| ... |)과 구분선(|---|)까지 그대로 본문에 포함하라"
    "(이 부록 섹션은 평문 규칙의 예외 — 표 기호 유지). 표 안 수치·간지·방향은 한 글자도 바꾸지"
    " 말고, 표 밖에서 새 수치를 만들지 말 것. 표 위아래에 짧은 안내문만 덧붙여라.",
    # ── 관계·애정운 궁합(상대 선택) 모드 전용(RP-01~RP-10) ──
    "RP-01": "두 사람 관계를 5줄 이내로 — 어떤 결의 조합이고 어디에 강점/마찰이 있는지.",
    "RP-02": "본인의 애정 성향(재성/관성·도화·표현 방식)을 짧게 서술할 것.",
    "RP-03": "아래 상대 명식 블록만 근거로 상대가 어떤 사람인지 솔직하게 서술할 것 — "
    "좋은 점·부담스러운 점을 균형 있게. 단정·낙인·외모/소득 추측 금지.",
    "RP-04": "아래 궁합 신호(일주·십성·용신)를 근거로 두 사람의 구조적 결합을 설명할 것. "
    "신호의 방향(보완/마찰)을 그대로 반영하되 점수를 지어내지 말 것.",
    "RP-05": "궁합 신호를 강점과 마찰점으로 나눠 솔직하게 정리할 것 — 좋게 포장하지 말 것. "
    "마찰점도 '관계가 끝난다' 류 단정 금지, 관리 가능한 영역으로 제시.",
    "RP-06": "운에서 두 사람이 함께 겪을 흐름을 시점 클러스터로 타임라인화할 것(향후 5년).",
    "RP-07": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "RP-08": "마찰 신호가 있다면 그것을 극복하기 위한 마음가짐과 구체적 행동을 제시할 것 — "
    "상대 탓·운명론·강요 금지. 본인이 바꿀 수 있는 태도와 대화법 중심.",
    "RP-09": "관계 운영 전략을 — 다가서기/거리두기/대화/기대 조정 단위. 강요·확정 표현 금지. "
    "관계 정리를 고민하는 맥락이면, 운이 저점인 시기엔 큰 결정을 보류·시간 견디기를 "
    "권하고(조급함이 신호), 사유가 외도·폭력이면 회복이 어려운 영역, 성격·건강이면 "
    "노력·시간으로 달라질 수 있는 영역으로 결을 나눠 안내할 것.",
    "RP-10": "아래 점수표를 마크다운 표 형식(| ... |)과 구분선(|---|)까지 그대로 본문에 포함하라"
    "(이 부록 섹션은 평문 규칙의 예외 — 표 기호 유지). 표 안 수치·간지·방향은 한 글자도 바꾸지"
    " 말고, 표 밖에서 새 수치를 만들지 말 것. 표 위아래에 짧은 안내문만 덧붙여라.",
    # ── 한해풀이 전용(Y-01~Y-12, 단일 년도 — 짧은 기간 전제) ──
    "Y-01": "선택한 해의 핵심을 5줄 이내로 — 무엇이(확장/변동/주의) 어느 분기에 활성인지.",
    "Y-02": "강약·격국·용신을 짧게 짚고 용신 오행을 명시할 것 — 이 해 해석의 기준이 됨. "
    "원국 전체 재설명은 생략하고 핵심만.",
    "Y-03": "올해가 속한 대운의 성격과 그 안에서 이 해의 위치를 설명할 것 — 대운 전체사는 생략.",
    "Y-04": "이 해 세운 간지와 활성 신호(원국과의 합·충·십성 작용)를 풀 것 — 발생≠결과.",
    "Y-05": "아래 [12개월 흐름]의 12개 달을 하나도 빠뜨리지 말고 각 달을 1~2문장으로 조밀하게 "
    "짚을 것 — 한두 강신호만 반복 금지. ★주목 달은 더 자세히, 좋은 달과 주의할 달을 함께, "
    "각 달 기운의 활용·대비 방향도 곁들일 것.",
    "Y-06": "이 해 직업·사업 흐름(이동·승진·확장·도전)을 발현 형태로 — 합격·승진 단정 금지.",
    "Y-07": "이 해 재물 흐름(수입·지출·투자·계약)을 발현 형태로 — 당첨·복권 단정 금지(로또 거부).",
    "Y-08": "이 해 관계·가정 흐름(만남·안정·갈등·정리)을 발현 형태로 — 단정·낙인 금지.",
    "Y-09": "이 해 건강·주의 시기를 — 과로/사고/컨디션 저하 등 관리 관점으로. 질병 단정 금지.",
    "Y-10": "이 해 행동 전략을 분기·시기 단위로 구체화 — 시도/대기/준비/보류 단위.",
    "Y-11": "이 해 개운·보완 가이드를 용신 오행 기준으로 — 색·방위·생활 습관 등 실천 항목 중심.",
    "Y-12": "이 섹션 끝에는 이 해 12개월 간지 달력표가 엔진 계산값으로 자동 첨부된다. 본문에서 "
    "간지 표를 직접 만들지 말 것(간지를 지어내면 안 됨) — 표 읽는 법을 안내하고, 본문에 "
    "등장한 용어를 아래 [용어 사전] 기준으로 짧게 풀이하는 데 집중할 것.",
}
_DEFAULT_GUIDE = "아래 데이터 블록의 사실만 사용해 섹션 제목에 맞는 이야기로 서술할 것."
# 명식 구조 섹션(운 데이터 블록 미부착) — 인사·원국 재설명 1회 원칙.
_NATAL_SECTIONS = {
    "F-01",
    "F-02",
    "F-03",
    "F-04",
    "F-05",
    "F-06",
    "C-02",
    "W-02",
    "W-03",
    "J-02",
    "J-03",
    "R-02",
    "R-03",
    "RP-02",
    "RL-02",  # 이사 테마 — 이동·정착 성향(원국 기초)
    "Y-02",  # 한해풀이 — 원국+용신 기초(운 데이터 블록 미부착)
}
# 부록 점수표 섹션(실제 표 부착).
_SCORE_TABLE_SECTIONS = {"C-08", "W-09", "J-08", "R-08", "RP-10", "RL-08"}
# 이사 테마 — 십성 이유분류(reason_profiles) surface 섹션(이사 고도화 R2).
_RELOCATION_REASON_SECTIONS = {"RL-03"}
# 선발·배치 보조 부착 섹션(2026-07-14 방안 2, 데굴님 확정 — 목차 불변): 운 신호 섹션에
# 조건부(notable) 부착. education topic의 C-04는 build_section_context에서 동적 판정.
_SELECTION_AUX_SECTIONS: dict[str, str] = {
    "RL-04": "housing_subscription",  # 이사 테마 — 청약·공공주택
    "J-04": "workplace_assignment",  # 직업 테마 — 근무지·부서 배치
}
_RELOCATION_RISK_SECTIONS = {"RL-05"}
# 현실 과업 절차 참고(2026-07-22 데굴님 승인) — 행동 전략·체크리스트 섹션에 L1/L2 절차
# 지식(task_procedures 팩)을 부착해 운 신호를 실제 단계·의존관계에 연결한다. 목차 불변
# (절대원칙 10 — 컨텍스트 재료만 추가). 선발·배치는 전용 보조(_SELECTION_AUX_SECTIONS) 담당.
_PROCEDURE_PACK_SECTIONS: dict[str, str] = {
    "RL-05": "housing",  # 이사 — 리스크와 계약 전 체크리스트
    "RL-07": "housing",  # 이사 — 행동 전략
    "J-07": "employment",  # 직업 — 행동 전략
}
# 연간 총운(RPT_YEAR) — 세운 천간 십성 이사 유형을 '세운과 활성 신호'(Y-04)에 간결 부착
# (2026-06-18 사용자 확정: 인생 총운 RPT_FULL 미부착, 연간 총운에만 노출).
_RELOCATION_YEAR_SECTIONS = {"Y-04"}
# 이사 테마 — M10 방위 적합(RL-04) / 월별 이동운 흐름·충돌(RL-06) surface.
_RELOCATION_DIRECTION_SECTIONS = {"RL-04"}
_RELOCATION_FLOW_SECTIONS = {"RL-06"}
# 궁합 모드 — 상대 명식 블록 부착 섹션(RP-03).
_PARTNER_NATAL_SECTIONS = {"RP-03"}
# 궁합 모드 — 궁합 신호 블록 부착 섹션(RP-04·RP-05·RP-08).
_COMPAT_SECTIONS = {"RP-04", "RP-05", "RP-08"}
# 섹션 → 도메인(섹션별 도메인 스코프 후보 사용 — 강신호 반복·intent 편향 차단, 2026-06-16).
# 한해풀이 Y-06~Y-09 + 총운 F-15~F-18에 적용(RPT_YEAR·RPT_FULL 동일 강화 — 사용자 확정).
_SECTION_DOMAIN: dict[str, str] = {
    "Y-06": "career",
    "Y-07": "wealth",
    "Y-08": "relationship",
    "Y-09": "health",
    "F-15": "career",
    "F-16": "wealth",
    "F-17": "relationship",
    "F-18": "health",
    "RL-04": "relocation",
    "RL-06": "relocation",  # 이사 테마 — 이동 신호·향후 흐름
    # 테마 FOCUS 종합·주목달 섹션 — 자기 도메인 후보(길·흉 포함)로 반복·편향 차단(2026-06-23).
    "W-06": "wealth",
    "W-07": "wealth",
    "J-05": "career",
    "J-06": "career",
    "R-05": "relationship",
    "R-06": "relationship",
    "RP-06": "relationship",
    "RP-07": "relationship",
}
# 월별 흐름 표(예측 창 각 해 12개월 전체, 연도별 그룹)를 부착하는 섹션 — 좋은·주의·평범 달
# 누락 없이. 한해풀이 Y-05 + 테마 FOCUS '주목할 달' + generic FOCUS 타임라인(2026-06-23 보강).
_MONTH_OVERVIEW_SECTIONS = {"Y-05", "W-07", "J-06", "R-06", "RP-07", "RL-06", "C-04"}
# 세운 연도별 전체 흐름 표(예측 창 전 연도)를 부착하는 섹션 — '향후 N년 종합'·고점 연도 스캔.
# 테마 FOCUS 5년 종합 + generic FOCUS 기간 흐름 + 총운 고점 연도(F-14)(2026-06-23 보강).
_YEAR_SPECTRUM_SECTIONS = {"W-06", "J-05", "R-05", "RP-06", "RL-06", "C-03", "F-14"}

# 대운 풀이 framing·교체기 신호 디렉티브는 채팅과 공용(structural_context) — 위에서 import.
# 평운/기신 대운 조언(2026-06-23, 강의 참고) — 안 맞는 구간은 포기가 아니라 유지·내실.
_OFF_PEAK_DAEWOON_ADVICE_DIRECTIVE = (
    "[안 맞는 대운 구간 조언] 대운이 용신에 맞지 않는(평운·기신) 구간이라면 '포기'가 아니라, "
    "새 확장보다 지금 하던 것을 지키며 내실을 다지고 다음 맞는 대운을 준비하는 전략으로 안내할 것."
)
# 운 블록에서 [대운표]만 받고 미래(+5년) 이벤트 후보 4블록(이벤트 후보·합작용·발현분기·내부근거)은
# 빼는 섹션(2026-06-27 데굴님 지적 — 데이터-목적 시간범위 불일치 교정). 2부 과거(F-07 출생~현재
# 대운별 테마 / F-08 과거 이벤트 복원 / F-09 과거 검증)는 미래 후보가 섞이면 안 되고, 메타 섹션
# (F-21 요약카드 / F-22 부록=간지달력·용어)도 원시 미래 클러스터가 부적절하다. 과거 데이터는 각
# 섹션의 M14(과거 검증) 모듈이, 시간 backbone은 [대운표](과거 포함)가 담당한다. docs/10 2부·5부.
_DAEWOON_ONLY_SECTIONS = {"F-07", "F-08", "F-09", "F-21", "F-22"}
# 간지 달력표(엔진 결정론적 표)를 본문 끝에 자동 첨부하고 terminology.json을 주입하는 섹션
# (docs/10 F-22 부록 / Y-12 간지 달력표). 표는 LLM이 만들지 않고(절대원칙 1) 분량 캡도 면제한다.
_GANJI_CALENDAR_SECTIONS = {"F-22", "Y-12"}
# 간지 한자→한글 음(병기용) — '庚寅'→'경인'. 표는 _sanitize_output을 거치지 않으므로 직접 병기한다.
_STEM_KO_BY_HANJA = {s.value: ko for s, ko in STEM_KO.items()}
_BRANCH_KO_BY_HANJA = {b.value: ko for b, ko in BRANCH_KO.items()}


def _ganji_ko(ganji: str) -> str:
    """간지 한자 2글자를 '한자(한글)'로 — 예 '庚寅'→'庚寅(경인)'. 매핑 실패 시 원문."""
    if len(ganji) != 2:
        return ganji
    ko = _STEM_KO_BY_HANJA.get(ganji[0], "") + _BRANCH_KO_BY_HANJA.get(ganji[1], "")
    return f"{ganji}({ko})" if len(ko) == 2 else ganji


# 대운 framing 관점을 붙일 섹션(대운 개관·정밀·로드맵·한해 대운 맥락).
_DAEWOON_FRAMING_SECTIONS = {"F-07", "F-10", "F-13", "Y-03"}
# 교체기 체감 신호를 붙일 섹션(대운 흐름 개관 + 과거 검증 체크리스트).
_DAEWOON_TRANSITION_SIGNAL_SECTIONS = {"F-07", "F-09"}
# 안 맞는 대운 조언을 붙일 섹션(도메인·연·테마 행동 전략).
_OFF_PEAK_ADVICE_SECTIONS = {
    "F-19",
    "Y-10",
    "W-08",
    "J-07",
    "R-07",
    "RP-09",
    "RL-07",
    "C-07",
}
# 상담 사례 파생(P1·P2) — 활동 키워드·개운 행동 블록을 붙일 행동 전략 섹션. 감수 전 초안이라
# 직업 테마 J-07만 배선하고, 감수 통과 후 타 테마 확장을 검토한다(2026-07-03 데굴님 확정).
_ACTIVITY_REMEDY_SECTIONS = {"J-07"}
# 탈규범 안심 디렉티브를 붙일 관계 행동 전략 섹션(결혼 필수 강요 차단 — 사례 §5 P0-3).
_NON_NORMATIVE_SECTIONS = {"R-07", "RP-09"}
# 시기 단정 금지 디렉티브를 붙일 주목할 달 섹션 — 우선 직업 테마 J-06만(사례 §6 모방 금지,
# 감수·실측 후 타 테마 '주목할 달' 확장 검토).
_DATE_CERTAINTY_SECTIONS = {"J-06"}


@lru_cache(maxsize=1)
def _activity_keyword_map() -> dict:
    """activity_keyword_map.json 로드(프로세스 캐시) — reviewed:false 초안, 서술 재료 전용."""
    return json.loads(
        (_DICTS / "interpretations" / "activity_keyword_map.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def _remedy_action_map() -> dict:
    """remedy_action_map.json 로드(프로세스 캐시) — reviewed:false 초안, 서술 재료 전용."""
    return json.loads(
        (_DICTS / "interpretations" / "remedy_action_map.json").read_text(encoding="utf-8")
    )


# 원국 횡재 그릇 블록을 부착하는 재물 섹션(Phase 1 — 횡재 잠재구조 표면화).
_WEALTH_CAPACITY_SECTIONS = {"W-04", "W-05", "Y-07", "F-16"}
# 결혼·자산 자원 구조 블록을 부착하는 관계·재물구조 섹션(중립 구조 신호 — 신규 키 없음).
# 직업 테마(J-*)에는 부적합이라 미부착(개별 intent는 주제 적합 섹션만 — 선택적).
_MARRIAGE_RESOURCE_SECTIONS = {
    "R-03",
    "R-05",
    "RP-03",
    "RP-04",
    "F-17",
    "Y-08",
    "W-03",
}
# 건강 취약 구조 블록을 부착하는 건강 섹션(Y-09·F-18은 건강 전용, C-02·C-06은 health 주제만).
_HEALTH_VULN_SECTIONS = {"Y-09", "F-18"}
_HEALTH_TOPIC_SECTIONS = {"C-02", "C-06"}
# 부/귀 지향 블록을 부착하는 명식 구조·직업 섹션.
_WEALTH_STATUS_SECTIONS = {"F-04", "J-02", "J-03", "W-02"}
# (블록 한글화 매핑은 structural_context 단일 소스로 이관됨 — 누출 방지 포맷 일원화.)


class _ReportData:
    """보고서 1건의 공유 데이터 — 섹션마다 재계산하지 않는다(사전계산 우선)."""

    def __init__(
        self,
        birth: BirthInput,
        spec: ReportSpec,
        today: date,
        *,
        owner_id: str | None = None,
        subject_id: str | None = None,
        partner_birth: BirthInput | None = None,
    ) -> None:
        self.today = today  # 시제 앵커(프롬프트 주입) — 모델이 과거/현재/미래를 추론하지 않도록.
        self._spec = spec  # 연도 스펙트럼 창 계산용(예측 연도 폭).
        chart_birth = birth.model_copy(update={"reference_date": today})
        self._chart_birth = chart_birth  # 월운 10년 온디맨드 생성용(간지 달력표)
        self.result: ManseV2Result = calculate(chart_birth)
        # 월운 다년 주입 — calculate()는 기준일 근방 12개월만 채운다. 예측 창(현재~+5년)의 각 해
        # 월운을 생성해 월 단위 후보·12개월 전체 표가 다년에 걸쳐 나오도록 한다(종전: 1년치만 존재해
        # '특정 달 반복'·다년 디테일 부재 — 2026-06-23 사용자 지적). 빈 결과는 무시(graceful).
        lc = self.result.luck_cycles
        if lc is not None:
            months: list = []
            for y in _forecast_years(spec, today):
                try:
                    months += luck_months(chart_birth, y)
                except (ValueError, RuntimeError):
                    continue
            if months:
                seen: set[str] = set()
                deduped = []
                for p in months:
                    if p.label not in seen:
                        seen.add(p.label)
                        deduped.append(p)
                lc.monthly_luck = deduped
        self.scorer = EventEngineV2(_DICTS, **marriage_engine_flags())
        # 개인화(저장된 subject 한정): 현실 신호 시그니처 + 활성 코호트 → LEI 정렬축.
        # 미설정·실패 시 무개인화 폴백(규칙11).
        sig, cohort = fetch_personal_inputs(owner_id, subject_id, self.result)
        # 사용자 확정 용신 — 있으면 용희기구한 5역할을 그 용신으로 재도출해 fav_override로 점수에
        # 반영(엔진 최초 도출값=확정 전 후보는 yongsin_analysis.final로 비파괴 보존, 되돌림 기준).
        fav_override, self._confirmed_yongsin = fetch_confirmed_yongsin_override(
            owner_id,
            subject_id,
        )
        # 직업/관계 상태 분기(공직자 등)·특수직군 충형 길화(자료 9-6) — 채팅과 동일 신호를
        # 테마사주(리포트)에도 반영. 프로필 미설정·무DB면 None(게이트 미적용 — 규칙11).
        _form, occ_status, rel_status, occ_category = profile_event_signals(subject_id)
        scored = self.scorer.score_legacy_personalized(
            self.result,
            levels=_SCORE_LEVELS,
            fav_override=fav_override,
            signature=sig,
            cohort=cohort,
            occupation_status=occ_status,
            relationship_status=rel_status,
            occupation_category=occ_category,
        )
        in_period = [
            c for c in scored if spec.period.start[:4] <= c.period[:4] <= spec.period.end[:4]
        ]
        # LEI 정렬축(현실적합>과거유사>점수) — 개인 시그니처 미배선 시 -c.score와 동치.
        pool = sorted(in_period or scored, key=lambda c: (-c.life_fit, -c.personal_match, -c.score))
        # 예측 테마(향후 N년: 직업·재물·관계)는 과거 고점이 아니라 '오늘 이후'를 앵커링한다.
        # 생애 전체에서 과거 고점(예: 2022·2025)이 top을 점유해 '향후 5년'이 지난 시점에
        # 머무는 결함 차단 — 오늘이 속한 달 이후 ~ +5년 창으로 한정(2026-06-14 실로그 결함).
        if spec.product_code == "RPT_FOCUS" and spec.topic in _FORECAST_TOPICS:
            # 절기 기준 당월 — 양력 today.month는 절기 경계 직전 한 달 앞서 과거 신호를
            # '향후'에 끌어들일 수 있다. 월운 라벨이 생성된 차트 타임존으로 정합.
            tc = self.result.time_correction
            tz = tc.timezone if tc else "Asia/Seoul"
            cur = luck_month_label(today, get_table(), tz)
            forward = [
                c
                for c in pool
                if _period_end_month(c.period) >= cur and int(c.period[:4]) <= today.year + 5
            ]
            pool = forward or pool
        # 주제 스코핑(FOCUS): 해당 도메인 신호를 가진 후보만 남겨 직장운·금전운 본문을
        # 차별화한다. 도메인 후보가 없으면 빈 리포트 방지를 위해 전체를 유지한다.
        if spec.product_code == "RPT_FOCUS" and spec.topic in _TOPIC_DOMAINS:
            domain_pool = [c for c in pool if _EVENT_DOMAIN.get(str(c.event_key)) == spec.topic]
            pool = domain_pool or pool
        self.candidates: list[EventCandidate] = pool[:_TOP_CANDIDATES]
        self.scored = scored  # 전체 점수화(필터 전) — 발현 분기·섹션별 도메인 후보 산출용.
        # 기간 연도 경계(섹션별 도메인 후보 스코핑용) — 후보 필터와 동일 기준.
        self._yr_lo = spec.period.start[:4]
        self._yr_hi = spec.period.end[:4]
        self.summary = build_birth_summary(self.result)
        self.detected_patterns = detect_structure_patterns(self.result)  # 구조 패턴(섹션별 선별)
        # 능동 제안(docs/15) — 재물·직업 도메인 섹션에 도메인 우선 top-2 주입.
        self.direction_suggestions = detect_direction_suggestions(self.result)
        self.wealth_capacity = analyze_wealth_capacity(self.result)  # 원국 횡재 그릇(운 분리)
        # 재물 준비기(P3) — 발현 후보년·선행 준비년 서술 전용 맥락(W-06/W-08 주입, inert).
        self.preparation_context = build_preparation_context(
            self.result.luck_cycles.yearly_luck if self.result.luck_cycles else [],
            today.year,
        )
        # 대운 발현 진행 모드(2026-07-21) — 하드 전/후반 분할 대체(서술 전용, 점수·판정 불변).
        self.daewoon_progression = (
            resolve_all_daewoon_progressions(
                self.result.luck_cycles.daewoon_table, self.result.pillars
            )
            if self.result.luck_cycles is not None and self.result.pillars is not None
            else []
        )
        # 결혼·자산 자원(성별 인지) — 용희신을 넘겨 '배우자성=용신(배우자 덕)'까지 판정(G).
        self.marriage_resource = analyze_marriage_resource(
            self.result,
            self.summary.useful_gods,
        )
        self.health_vulnerability = analyze_health_vulnerability(
            self.result,
            favorability_map(self.result),
        )  # 원국 건강 취약 구조(운 미반영 — 의료 진단·수명 예측 아님)
        self.wealth_status_lean = analyze_wealth_status_lean(self.result)  # 부/귀 지향(원국 구조)
        self.prefix_lines = serialize_chart_prefix(
            self.summary,
            build_chart_interpretation(self.result),
        )
        # 공망 해석 규칙(전 섹션 공통) — 원국 공망은 배경값·운 자극 시만 발동(미발동 시 언급 금지).
        # 불확실성 번역 규칙(전 섹션 공통, 2026-07-22) — '가능성이 열리는 달' 류 추상 문구
        # 단독 금지, 구체 사건·미확정 결과·실제 변수·행동으로 번역(chat과 공용 상수).
        self.prefix_lines = [
            *self.prefix_lines,
            GONGMANG_ACTIVATION_DIRECTIVE,
            UNCERTAINTY_TRANSLATION_DIRECTIVE,
        ]
        # 확정 용신 적용 안내를 원국 prefix 뒤에 부착(전 섹션 공통) — 확정 5역할을 길흉 기준으로,
        # 엔진 최초 도출(확정 전 후보)은 기본값으로 병기. 확정=도출 일치 시 빈 문자열(미부착).
        if self._confirmed_yongsin is not None:
            note = confirmed_yongsin_note(self.result, self._confirmed_yongsin)
            if note:
                self.prefix_lines = [*self.prefix_lines, note]
        # 캘리브레이션 표현 조정 힌트(CAL-P0 trait 반박 + CAL-P1 pair 매트릭스, 전 섹션 공통)
        # — 저장된 검증 응답 기반 서술 조정 전용(판정·점수 불변, 처방 금지 조항 내장).
        _calib_hints = fetch_calibration_expression_hints(subject_id)
        if _calib_hints:
            self.prefix_lines = [*self.prefix_lines, *_calib_hints]
        self.evidence_paths = self._evidence_paths_for(self.candidates)
        self.allowed_ganji = self._collect_ganji()
        self.allowed_years = self._collect_years(spec)
        # 섹션별 도메인 후보·12개월 표가 surface하는 점수를 모두 허용(검사3 — 미제공 점수 차단은
        # '엔진이 산출하지 않은' 점수만 막으면 됨). 전 scored 점수는 모두 실제 엔진 산출값이다.
        self.allowed_scores = sorted({c.score for c in scored})
        # 직전 생성 섹션들의 첫 문장(최근 _MAX_RECENT_OPENINGS개) — 섹션은 순차 생성되므로
        # 다음 섹션 프롬프트에 '서두 반복 금지' 재료로 주입한다(2026-07-06 테스터 지적:
        # 매 페이지가 비슷한 '나' 공통 묘사로 시작). 서술 전용 — 점수·판정 불변.
        self.recent_openings: list[str] = []

        # Topic Builder(M01~M15) extras — 섹션 module_calls 실행용(옵션1 배선, 지연 빌드).
        self.owner_id = owner_id
        self.subject_id = subject_id
        self.extended_profile = _load_extended_profile(subject_id)  # 물상(사실 맥락) 주입용
        self.birth = chart_birth  # M14 과거검증 extras
        self._composites: list | None = None
        _tg = getattr(self.result.force_analysis, "ten_gods", None)
        self.natal_ten_god_dist: dict[str, float] = (
            dict(_tg.distribution) if _tg and _tg.distribution else {}
        )

        # 관계운 상대(궁합) 모드 — 상대 명식 + 원국A↔원국B 궁합 신호(엔진 계산).
        self.partner_summary = None
        self.partner_result: ManseV2Result | None = None
        self.partner_prefix_lines: list[str] = []
        self.compatibility = None
        # 사용자가 지정한 '상대와의 관계'(RP 풀이 방향 — 2026-07-03). 미지정 None.
        self.partner_relation_type: str | None = next(
            (
                s.relation_type
                for s in spec.subjects
                if s.kind != SubjectKind.SELF and s.relation_type
            ),
            None,
        )
        if partner_birth is not None:
            partner_chart = partner_birth.model_copy(update={"reference_date": today})
            partner_result = calculate(partner_chart)
            self.partner_result = partner_result
            self.partner_summary = build_birth_summary(partner_result)
            self.partner_prefix_lines = serialize_chart_prefix(
                self.partner_summary,
                build_chart_interpretation(partner_result),
            )
            self_label = spec.subjects[0].label if spec.subjects else "본인"
            partner_label = next(
                (s.label for s in spec.subjects if s.kind != SubjectKind.SELF),
                "상대",
            )
            self.compatibility = analyze_compatibility(
                self.result,
                partner_result,
                self.summary.useful_gods,
                self.partner_summary.useful_gods,
                self_label=self_label,
                partner_label=partner_label,
            )

    def record_opening(self, text: str) -> None:
        """생성된 섹션의 첫 문장을 기록 — 다음 섹션의 '서두 반복 금지' 프롬프트 재료.

        섹션은 순차 생성되므로, 여기 쌓인 최근 문장들이 곧 '직전 페이지들의 서두'다.
        최근 _MAX_RECENT_OPENINGS개만 유지한다(프롬프트 비대 방지).
        """
        first = first_sentence(text)
        if first:
            self.recent_openings.append(first)
            del self.recent_openings[:-_MAX_RECENT_OPENINGS]

    def partner_natal_block(self) -> list[str]:
        """상대 명식 구조 블록(RP-03 — 상대는 어떤 사람인가)."""
        if not self.partner_prefix_lines:
            return ["[상대 명식 없음 — 상대 출생정보가 등록되지 않았습니다.]"]
        return ["[상대 명식 — 엔진 확정값]", *self.partner_prefix_lines[1:]]

    def compatibility_block(self) -> list[str]:
        """궁합 신호 블록(RP-04·RP-05·RP-08 — 엔진 계산 사실)."""
        if self.compatibility is None:
            return ["[궁합 신호 없음 — 상대 명식이 없어 비교할 수 없습니다.]"]
        lines = compatibility_lines(self.compatibility)
        # 12신살 상대위치(P2) — 년지(사회)·일지(친밀) 상대 12신살 양방향(설명 레이어, 점수 미개입).
        partner = getattr(self, "partner_result", None)
        if partner is not None:
            from saju_engines.relationship_relative_sinsal import relative_sinsal_lines

            lines += relative_sinsal_lines(self.result, partner)
        return lines

    @property
    def composites(self) -> list:
        """Topic Builder용 LuckComposite(연·월, 지연 빌드·캐시)."""
        if self._composites is None:
            from saju_engines.precompute import CompositeBuilder
            from saju_shared_types.precompute import CompositeLevel

            try:
                self._composites = CompositeBuilder(_DICTS).build(
                    self.result,
                    "report",
                    "1.0.0",
                    f"{self.today.isoformat()}T00:00:00+00:00",
                    levels={CompositeLevel.YEAR, CompositeLevel.MONTH},
                )
            except (ValueError, RuntimeError):
                self._composites = []
        return self._composites

    def topic_module_block(self, module_id: str, spec: ReportSpec) -> list[str]:
        """섹션이 의존하는 Topic Builder 모듈(M01~M15) 실행 → 확정 신호·정책 톤 줄(옵션1).

        T0/T1/E* 등 비-토픽 ref는 무시. 모듈별 extras를 공급하고, 실패는 graceful(빈 줄).
        findings는 점수 확정값, style은 절대원칙 8 정책 톤(LLM 입력 일관 적용).
        """
        return _topic_module_block(module_id, self, spec)

    def _collect_ganji(self) -> list[str]:
        ganji = list(self.summary.pillars.values())
        lc = self.result.luck_cycles
        if lc is not None:
            ganji += [d.ganji for d in lc.daewoon_table]
            ganji += [p.ganji for p in [*lc.yearly_luck, *lc.monthly_luck]]
        return sorted(set(ganji))

    def _collect_years(self, spec: ReportSpec) -> list[int]:
        years = {int(c.period[:4]) for c in self.candidates if c.period[:4].isdigit()}
        years |= {int(spec.period.start[:4]), int(spec.period.end[:4])}
        lc = self.result.luck_cycles
        if lc is not None:
            for d in lc.daewoon_table:
                years.update(range(d.approx_start_date.year, d.approx_end_date.year + 1))
        return sorted(years)

    def tense_anchor_lines(self, spec: ReportSpec) -> list[str]:
        """[기준 시점] — '오늘'과 과거/현재/미래 시제를 사실로 못박는다(시제 추론 불요).

        thinking이 low라 모델이 오늘 날짜·시제를 스스로 못 잡는 결함을 차단한다. RPT_YEAR는
        대상 연도의 월별 과거/현재/미래까지 명시한다(예: 2026 풀이를 6월에 보면 1~5월=과거).
        """
        t = self.today
        lines = [
            "",
            "[기준 시점 — 시제 판단의 절대 기준. 이 사실로 시제를 정하고 추측하지 말 것]",
            f"오늘은 {t.year}년 {t.month}월 {t.day}일이며, 이 보고서를 작성하는 시점이다.",
            f"- {t.year}년 {t.month}월 이전(연·월)은 이미 지난 과거다 → 과거 시제로 서술한다.",
            f"- {t.year}년 {t.month}월은 현재(이번 달)다.",
            f"- {t.year}년 {t.month}월 이후(연·월)는 아직 오지 않은 미래다"
            " → 미래(예측) 시제로 서술한다.",
            "지난 시점을 다가올 일처럼, 다가올 시점을 이미 일어난 일처럼 쓰지 말 것.",
        ]
        # RPT_YEAR — 대상 연도의 월별 시제를 못박아 한 해 안의 과거/미래 혼동을 차단.
        if spec.product_code == "RPT_YEAR" and spec.period.start[:4].isdigit():
            y = int(spec.period.start[:4])
            if y < t.year:
                lines.append(f"이 보고서가 다루는 {y}년은 올해보다 이전이므로 전체가 과거다.")
            elif y > t.year:
                lines.append(f"이 보고서가 다루는 {y}년은 올해보다 이후이므로 전체가 미래다.")
            else:
                past = f"1~{t.month - 1}월은 이미 지난 과거" if t.month > 1 else "(지난 달 없음)"
                if t.month < 12:
                    future = f"{t.month + 1}~12월은 아직 오지 않은 미래"
                else:
                    future = "(남은 달 없음)"
                lines.append(f"{y}년은 올해다 — {past}, {t.month}월은 이번 달, {future}다.")
        return lines

    def _evidence_paths_for(self, candidates: list[EventCandidate]) -> list[str]:
        """후보 상위 3건의 사람용 근거 경로(내부 근거 — 본문엔 일상어로 풀어 녹임)."""
        return [
            " → ".join(self.scorer.readable_path(c))
            for c in candidates[:3]
            if self.scorer.readable_path(c)
        ]

    def domain_candidates(self, domain: str, n: int = 6) -> list[EventCandidate]:
        """섹션 도메인 후보 — 기간 내 같은 도메인 신호를 길·흉 모두 담아 시점순 top-n.

        전 섹션이 같은 전역 top-8을 공유해 한두 강신호가 모든 섹션에 반복되는 문제(2026-06-16
        사용자 확정)를 막는다. self.scored(필터 전 전체)에서 도메인·기간으로 좁히고, 같은 시점은
        최고 점수 1건으로 병합한다. 좋은 운에 편중되지 않도록 주의(흉)운을 최대 2건까지 보장한다.
        """
        merged: dict[str, EventCandidate] = {}
        for c in self.scored:
            if _EVENT_DOMAIN.get(str(c.event_key)) != domain:
                continue
            if not (self._yr_lo <= c.period[:4] <= self._yr_hi):
                continue
            cur = merged.get(c.period)
            if cur is None or c.score > cur.score:
                merged[c.period] = c
        pool = list(merged.values())
        salience = lambda c: (-c.life_fit, -c.personal_match, -c.score)  # noqa: E731
        cautions = sorted(
            (c for c in pool if str(c.polarity) == EventPolarity.NEGATIVE_OR_FORCED),
            key=salience,
        )
        others = sorted(
            (c for c in pool if str(c.polarity) != EventPolarity.NEGATIVE_OR_FORCED),
            key=salience,
        )
        reserve = min(2, len(cautions))
        picked = others[: max(0, n - reserve)] + cautions[:reserve]
        return sorted(picked, key=lambda c: c.period)

    def month_overview_block(
        self, domain: str | None = None, *, notable_only: bool = False
    ) -> list[str]:
        """[월별 흐름] — 예측 창 각 해의 12개월 전체를 빠짐없이(반복 방지 — 연도별 그룹).

        domain 지정(테마 섹션) 시 대표 사건을 그 주제로 한정한다(운 품질 등급은 항상 표기).
        notable_only=True(Context Reduction 1단계 — 섹션 토큰 상한 초과 시): 다년 창에서 ★주목
        달만 남기고 헤더도 그에 맞춰 바꾼다(단년은 전체 유지).
        """
        overview = month_overview_lines(self.result, self.scored, domain, notable_only=notable_only)
        if not overview:
            return []
        # 기반 최고 달을 이름 박아 지목 — 그 달에 두드러진 사건이 없어도 누락되지 않게(채팅과 동일).
        lc = self.result.luck_cycles
        best = [p.label for p in (lc.monthly_luck if lc else []) if p.luck_label == "강한 용신운"]
        n_years = len({p.label[:4] for p in (lc.monthly_luck if lc else [])})
        scope = f"향후 {n_years}개 해의 각 12개월" if n_years > 1 else "이 해 12개월"
        callout = (
            f" 특히 {', '.join(best[:3])}은(는) '강한 용신운'이라 두드러진 사건이 없어도 "
            "기반이 가장 좋은 달이니 반드시 그렇게 짚을 것."
            if best
            else ""
        )
        if notable_only and n_years > 1:
            # 축소 단계 — 데이터에 ★주목 달만 담기므로 '모든 달' 지시를 '주목 달 중심'으로 바꾼다.
            intro = (
                f"[월별 흐름 — 예측 창이 길어({scope}) 지면 관계상 각 해의 ★주목 달(가장 "
                "좋은 달·주의할 달)만 추렸다(〈연도〉별로 묶음). 추려진 달을 한두 문장으로 짚되, "
            )
        else:
            intro = (
                f"[월별 흐름 — {scope} 전체(〈연도〉별로 묶음). 한두 강신호만 반복하지 말고 "
                "각 달을 한두 문장으로 고르게 짚되, 좋은 달·주의할 달·평범한 달을 모두 다룰 것. "
                "★주목 표시된 달은 더 자세히. "
            )
        header = intro + _MONTH_FLOW_GUIDE_TAIL + callout + "]"
        return [header, *overview]

    def year_spectrum_block(
        self, domain: str | None = None, *, notable_only: bool = False
    ) -> list[str]:
        """[연도별 흐름] — 예측 창 세운 전 연도를 빠짐없이('향후 N년 종합' 섹션 반복·편향 방지).

        domain 지정(테마 섹션) 시 대표 사건을 그 주제로 한정한다(운 품질 등급은 항상 표기).
        notable_only=True(Context Reduction 2단계): ★주목 해로만 좁힌다(월별 축소로도 부족할 때).
        """
        years = _forecast_years(self._spec, self.today)
        spectrum = year_spectrum_lines(
            self.result, self.scored, years, domain, notable_only=notable_only
        )
        if not spectrum:
            return []
        return [
            "[연도별 흐름 — 예측 창의 세운을 해마다 빠짐없이. 상위 몇 해만 반복하지 말고 "
            "좋은 해·주의할 해·평범한 해를 모두 짚을 것. ★주목 표시된 해는 더 자세히. "
            "좋은 해·주의할 해의 1차 기준은 사건 밀도가 아니라 세운 운 품질 등급〈…〉"
            "(길흉=용신/기신)이며, 각 해 기운의 활용·대비 방향을 곁들일 것.]",
            *spectrum,
        ]

    # ── 구조 해석 블록(누출 안전) — 포맷은 structural_context 단일 소스에 위임. ──
    def wealth_capacity_block(self) -> list[str]:
        """[원국 횡재 그릇] — structural_context.wealth_capacity_lines 위임(재물 섹션 전용)."""
        return wealth_capacity_lines(self.wealth_capacity)

    def activity_remedy_block(self) -> list[str]:
        """[활동 키워드]+[개운 행동] — 용신·희신/기신·구신·원국 신살 기준 결정론 선별.

        상담 사례 파생 P1·P2(doc/v2_2/cases/1980_1122_job_report_case.md §5). 사전은
        reviewed:false 초안이라 서술 재료로만 쓰며 점수·판정에 개입하지 않는다(원칙 5).
        확정 용신 오버라이드는 self.summary에 이미 반영돼 있어 그대로 따른다.
        """
        ug = self.summary.useful_gods
        favorable = [(el, "용신") for el in ug.yongsin] + [(el, "희신") for el in ug.heesin]
        cautious = [(el, "기신") for el in ug.gisin] + [(el, "구신") for el in ug.gusin]
        natal_sinsal: set[str] = set()
        extras = self.result.traditional_extras
        if extras is not None and extras.sinsal is not None:
            for names in extras.sinsal.summary.model_dump().values():
                if isinstance(names, list):
                    natal_sinsal.update(str(n) for n in names)
        keyword_block = activity_keyword_lines(
            favorable, cautious, natal_sinsal, _activity_keyword_map()
        )
        remedy_block = remedy_action_lines([el for el, _ in favorable], _remedy_action_map())
        if not keyword_block and not remedy_block:
            return []
        out = [*keyword_block]
        if remedy_block:
            if out:
                out.append("")
            out += remedy_block
        return out

    def marriage_resource_block(self) -> list[str]:
        """[결혼·자산 자원 구조] — structural_context 위임(성별 인지·중립).

        MT6 혼기 static prior를 함께 첨부(활성 프로파일 off면 빈 줄 — 출력 불변).
        """
        return marriage_resource_lines(self.marriage_resource) + marriage_age_prior_lines(
            self.result
        )

    def selection_block(self, domain: str) -> list[str]:
        """[선발·배치 보조] — 추첨·선발형(청약·발령·학교 배정) 조건부 블록(방안 2).

        목차 불변(원칙 10) — 신규 섹션이 아니라 기존 운 신호 섹션에 부착한다.
        기관·자격 신호가 작동 수준(notable)일 때만 표면화하고, 미해당이면 빈 목록 —
        '해당될 때만 언급, 아니면 무언급'(외적 인상 신호 관행, 2026-07-14 데굴님 확정).
        """
        from saju_engines.selection_allocation import selection_report_lines

        return selection_report_lines(self.result, domain)

    def external_impression_block(self) -> list[str]:
        """[외적 인상·분위기 구조] — 인상·표현매력·관계적 끌림 보조(미모 단정 아님).

        리포트는 질문 intent가 없으므로 관계 챕터 배치 자체를 노출 근거로 보고 합성 RELATIONSHIP
        intent로 동일 게이트 함수를 호출한다(정책 단일 소스). band=none(미해당)이면 빈 목록 —
        '예쁜 경우에만 언급, 아니면 무언급' 보장. 성별 미상(confidence=low)은 strong일 때만 노출.
        """
        from saju_engines.external_impression import analyze_external_impression

        intent = IntentJson(
            intent_id="report_impression",
            query_type=QueryType.DOMAIN_ANALYSIS,
            domain=Domain.RELATIONSHIP,
        )
        return external_impression_lines(analyze_external_impression(self.result), intent)

    def health_vulnerability_block(self) -> list[str]:
        """[원국 건강 취약 구조 + 관리 권장 시기] — structural_context 위임(의료 면책)."""
        return health_lines(self.result, self.health_vulnerability, self.today.year)

    def wealth_status_block(self) -> list[str]:
        """[부/귀 지향] — structural_context 위임(영문·점수 비노출)."""
        return wealth_status_lines(self.wealth_status_lean)

    def _relocation_ctx(self, spec: ReportSpec) -> dict[str, Any]:
        """이사 M10 컨텍스트(이유분류 + 방위 적합 + 월별 이동운/충돌) — 리포트 1회 캐시.

        리포트는 EventEngineV2를 쓰지만 M10은 LuckComposite가 필요하므로 대상의 YEAR/MONTH
        컴포짓을 별도 산출해 RelocationResolver를 재사용한다(spec에 동반자 있으면 그룹 집계).
        일자 택일(DAY)은 리포트 미포함 — move_dates 대신 방위·월별 흐름을 surface한다.
        실패·신호 약함이면 빈 컨텍스트(이사 테마라도 리포트가 깨지지 않게 — 규칙11 폴백).
        """
        cache = getattr(self, "_reloc_cache", None)
        if cache is not None:
            return cache
        ctx: dict[str, Any] = {
            "profiles": [],
            "directions": {},
            "monthly": {},
            "conflicts": [],
        }
        try:
            from saju_engines.precompute import CompositeBuilder
            from saju_engines.relocation import RelocationResolver
            from saju_shared_types.precompute import CompositeLevel
            from saju_shared_types.relocation import RelocationPeriod, RelocationQuery

            comps = CompositeBuilder(_DICTS).build(
                self.result,
                "report",
                "1.0.0",
                f"{self.today.isoformat()}T00:00:00+00:00",
                levels={CompositeLevel.YEAR, CompositeLevel.MONTH},
            )
            anchor = spec.period.start[:4]
            subject = spec.subjects[0]
            yongsin = (
                self.summary.useful_gods.yongsin[0] if self.summary.useful_gods.yongsin else "土"
            )
            resolver = RelocationResolver(_DICTS)
            result = resolver.resolve(
                RelocationQuery(
                    group_subjects=[subject],
                    period=RelocationPeriod(start=f"{anchor}-01", end=f"{anchor}-12"),
                    current_location="미지정",
                ),
                {subject.label: comps},
                {subject.label: yongsin},
            )
            # 유형 분류(세운·대운 천간 십성)는 후보월 게이팅과 무관하게 항상 산출한다 —
            # 천간 십성은 '이사 유형'을, 지지 합충은 '실제 발생'을 판단(사용자 스펙 2·4장).
            # 연간/테마 리포트는 월 발동축 없이 세운+대운만으로 분류(month_key=None).
            ctx["profiles"] = resolver.classify_reasons(comps, anchor, None)
            ctx["monthly"] = result.group_summary.monthly_scores
            ctx["conflicts"] = result.group_summary.conflicts
            ctx["directions"] = resolver.direction_fit({subject.label: yongsin})
        except Exception:  # noqa: BLE001 — 이사 분석 실패가 리포트를 막지 않도록
            pass
        self._reloc_cache = ctx
        return ctx

    def relocation_reason_block(self, spec: ReportSpec) -> list[str]:
        """[이사의 이유·집 성격] — 십성 분류(천간=명분/지지=현장). 라벨을 일상어로 풀어 서술."""
        profiles = self._relocation_ctx(spec)["profiles"]
        if not profiles:
            return [
                "[이사 이유·집 성격 — 이번 기간 뚜렷한 이동 십성 신호가 약함. "
                "일반적 이동·정착 성향으로 서술하고 단정하지 말 것]"
            ]
        lines = [
            "[이사의 이유·집 성격 — 십성 분류. 천간=명분(이유)/지지=현장(집·지역). "
            "아래 라벨을 일상어로 풀어 서술하고 단정 표현은 금지]"
        ]
        for p in profiles:
            lines.append(
                f"- {p.source} {p.ten_god} → {p.type}: 이유 {'·'.join(p.move_reason)} / "
                f"집·지역 {'·'.join(p.property_tendency)}"
            )
        return lines

    def relocation_risk_block(self, spec: ReportSpec) -> list[str]:
        """[리스크·계약 전 체크리스트] — 십성별 리스크와 점검 항목. 공포 조장 없이 점검 안내."""
        profiles = self._relocation_ctx(spec)["profiles"]
        if not profiles:
            return [
                "[리스크·체크리스트 — 일반 이사 점검(등기부·계약 조건·실거주·하자 확인)으로 "
                "안내하고 공포를 조장하지 말 것]"
            ]
        lines = [
            "[리스크·계약 전 체크리스트 — 십성별. 겁주지 말고 "
            "'확인하면 안심되는' 점검 항목으로 안내]"
        ]
        for p in profiles:
            lines.append(
                f"- {p.ten_god}({p.type}, 리스크 {p.risk_level}): 주의 {'·'.join(p.risk)} / "
                f"확인 {'·'.join(p.required_checks)} / 핵심 질문 {p.main_question}"
            )
        return lines

    def relocation_year_block(self, spec: ReportSpec) -> list[str]:
        """[올해 이사·이동의 성격] — 연간 총운(Y-04)용 세운·대운 천간 십성 이사 유형 간결 surface.

        '올해 이사를 한다면 어떤 결의 이사인가'를 세운 천간(대표)·대운 천간(장기 배경) 십성으로
        분류한다(사용자 스펙 1·3장). 실제 이사 발생 여부는 별개이며 단정 표현 금지(절대원칙 3).
        신호 약하면 빈 줄(연간 리포트라 폴백 강제 안 함 — 이사 주제가 아닐 수 있음).
        """
        profiles = [
            p
            for p in self._relocation_ctx(spec)["profiles"]
            if p.source.startswith(("세운", "대운"))
        ]
        if not profiles:
            return []
        lines = [
            "[올해 이사·이동의 성격 — 세운 천간(올해 대표)·대운 천간(장기 배경) 십성. "
            "이사를 한다면 이런 결이라는 유형 분류일 뿐, 실제 이사 여부 단정은 금지]"
        ]
        for p in profiles:
            lines.append(
                f"- {p.source} {p.ten_god} → {p.type}: 이유 {'·'.join(p.move_reason[:3])} / "
                f"집·지역 {'·'.join(p.property_tendency[:2])}"
            )
        return lines

    def relocation_direction_block(self, spec: ReportSpec) -> list[str]:
        """[방위 적합] — 용신 기준 8방위 적합도(M10). 단정 말고 '유리/무난' 참고로 안내."""
        directions = self._relocation_ctx(spec)["directions"]
        if not directions:
            return []
        top = sorted(directions.items(), key=lambda x: -x[1])
        favorable = [d for d, f in top if f >= 1.0] or [d for d, _ in top[:2]]
        return [
            "[방위 적합 — 용신 기준(참고). 당위적 단정 금지, '유리한 방위' 참고로 녹일 것]",
            f"유리한 방위: {', '.join(favorable)}",
        ]

    def relocation_flow_block(self, spec: ReportSpec) -> list[str]:
        """[그룹 월별 이동운 흐름] — 월별 이동운 점수와 구성원 충돌 월(M10 group_summary)."""
        ctx = self._relocation_ctx(spec)
        monthly, conflicts = ctx["monthly"], ctx["conflicts"]
        if not monthly:
            return []
        ranked = sorted(monthly.items(), key=lambda x: -x[1])[:4]
        flow = ", ".join(f"{m}({'+' if s >= 0 else ''}{round(s, 2)})" for m, s in ranked)
        lines = [
            "[월별 이동운 흐름 — 점수 높을수록 이동 에너지가 강한 달(참고). 발생≠결과]",
            f"이동운이 두드러지는 달: {flow}",
        ]
        if conflicts:
            lines.append(f"구성원 이동운이 엇갈리는 달: {', '.join(conflicts)}")
        return lines

    def era_energy_block(self, year: int) -> list[str]:
        """[올해 시대 기운] — structural_context 위임 + 리포트 전용 연결 지시."""
        lines = era_energy_lines(self.result, year)
        if lines:
            lines.append(
                "이 시대 기운을 배경으로 깔고, 개인 사주가 그 안에서 어떻게 작동하는지 이어 풀 것."
            )
        return lines

    def _branch_lines(self, candidates: list[EventCandidate]) -> list[str]:
        """후보 기간별 발현 분기 — 같은 계열·같은 시점에 점수화된 형제 사건(강도순).

        후보(top) 사건의 같은 EVENT_CATEGORY 계열 형제를 전체 점수화(self.scored)에서
        같은 시점으로 스코프해 도출한다(같은 시점 점수화된 형제만 — 추측 배제).
        """
        out: list[str] = []
        by_period: dict[str, list[Any]] = {}
        for c in candidates:
            by_period.setdefault(c.period, []).append(c)
        for period in sorted(by_period):
            siblings = [s for s in self.scored if s.period == period]
            focal_keys = [c.event_key for c in by_period[period]]
            line = branch_summary(focal_keys, siblings)
            if line:
                out.append(f"{period}: {line}")
        return out

    def luck_hap_lines(self, candidates: list[EventCandidate]) -> list[str]:
        """후보 기간 운(세운·월운·대운) 천간이 원국과 맺는 천간합의 작용 모드 줄.

        원국 합은 prefix(serialize_chart_prefix)에 이미 있으므로, 여기서는 운 관여 합만.
        """
        lc = self.result.luck_cycles
        if lc is None:
            return []
        by_label = {p.label: p.ganji for p in [*lc.yearly_luck, *lc.monthly_luck]}
        cand_years = {int(c.period[:4]) for c in candidates if c.period[:4].isdigit()}
        stems: set[str] = set()
        branches: set[str] = set()
        for c in candidates:
            ganji = by_label.get(c.period) or by_label.get(c.period[:4])
            if ganji and len(ganji) >= 2:
                stems.add(ganji[0])
                branches.add(ganji[1])
        for d in lc.daewoon_table:  # 후보 연도를 커버하는 대운 간지
            if any(d.approx_start_date.year <= y <= d.approx_end_date.year for y in cand_years):
                if len(d.ganji) >= 2:
                    stems.add(d.ganji[0])
                    branches.add(d.ganji[1])
        return luck_hap_mode_lines(self.result, sorted(stems), sorted(branches))

    def luck_block(
        self, candidates: list[EventCandidate] | None = None, *, daewoon_only: bool = False
    ) -> list[str]:
        """[대운표]+[이벤트 후보] — 운 관련 섹션의 데이터 블록.

        candidates를 주면 그 후보만(섹션별 도메인 스코프), 없으면 전역 top 후보를 쓴다.
        daewoon_only=True면 [대운표](생애 전체 — 과거 포함 backbone)만 반환하고 미래(+5년)
        이벤트 후보·합작용·발현분기·내부근거는 생략한다 — 2부 과거·메타 섹션의 시간범위 정합용
        (_DAEWOON_ONLY_SECTIONS, 2026-06-27). 과거 사건은 해당 섹션의 M14 모듈이 담당한다.
        """
        cands = self.candidates if candidates is None else candidates
        lines = [
            "[대운표]",
            "(대운 풀이 시: 천간이 나타내는 계기·외부 변화가 상대적으로 먼저 인식되고, 지지가 "
            "나타내는 생활환경·관계·현실 조건은 시간이 지나며 누적·구체화되기 쉽다 — 고정된 "
            "전/후반 연차 분할이 아니며, 각 행의 '발현' 모드는 이 순서를 뒤집는 엔진 판정 예외다)",
        ]
        lc = self.result.luck_cycles
        if lc is not None:
            prog_by_idx = {p.daewoon_index: p for p in self.daewoon_progression}
            for d in lc.daewoon_table:
                prog = prog_by_idx.get(d.index)
                mode_ko = (
                    _PROGRESSION_MODE_KO.get(prog.mode, prog.mode)
                    if prog is not None
                    else _PROGRESSION_MODE_KO["default_gradient"]
                )
                lines.append(
                    f"대운 {d.ganji}(천간 {d.stem}={d.stem_ten_god}/지지 {d.branch}="
                    f"{d.branch_ten_god}) {d.approx_start_date.year}-{d.approx_end_date.year}, "
                    f"{d.start_age}-{d.start_age + 9}세: 발현 {mode_ko}"
                )
        if daewoon_only:
            return lines  # 미래 이벤트 후보 4블록 생략(과거·메타 섹션 — 시간범위 정합)
        lines.append("")
        lines.append(
            "[이벤트 후보 — 시점 클러스터·정밀 십성/관계. 점수는 확정값, 재계산 금지. "
            "아래 십성·관계 라벨만 사용하고 '재성 지지 충' 같은 임의 표현을 만들지 말 것]"
        )
        clusters = precise_candidate_clusters(self.result, cands)
        if clusters:
            lines += clusters
        else:
            lines.append("이 도메인의 두드러진 후보 신호는 약함 — 원국 구조 중심으로 서술.")
        hap_lines = self.luck_hap_lines(cands)
        if hap_lines:
            lines.append("")
            lines.append(
                "[합 작용(운) — 후보 기간 운 천간이 원국과 맺는 천간합의 모드·신뢰도(엔진 판정). "
                "단정 말고 신뢰도(확정/조건부/불성)대로, 합거된 십성은 그 시기 기능 "
                "약화/전환으로 서술]"
            )
            lines += hap_lines
        branch_lines = self._branch_lines(cands)
        if branch_lines:
            lines.append("")
            lines.append(
                "[발현 분기 — 같은 계열(이동·재물·학업 등)에서 같은 에너지가 갈릴 수 있는 형제 "
                "사건. 둘 다 나열만 하지 말고, 사용자의 상황(직업 유무 등)·맥락에서 성립 불가능한 "
                "형제는 배제해 가능한 쪽으로 좁혀 해석할 것 — 예: 직장이 없으면 '이직'은 성립하지 "
                "않아 같은 이동 에너지는 '이사'다.]"
            )
            lines += branch_lines
        paths = self._evidence_paths_for(cands)
        if paths:
            lines.append("")
            lines.append(
                "[내부 근거 — 신호가 왜 그렇게 판정됐는지의 인과(참고용). '관계 발동·용기신 품질·"
                "복수 가능성' 같은 분류 용어나 '근거 경로:' 표기를 본문에 그대로 쓰지 말 것. "
                "이 인과를 일상어로 풀어 설명에 자연스럽게 녹일 것]"
            )
            lines += paths
        return lines

    def terminology_block(self) -> list[str]:
        """[용어 사전] — terminology.json 정의를 주입(용어 해설을 사전 기준으로, 임의 정의 금지).

        간지 달력표 섹션(F-22·Y-12)의 '용어 해설'이 LLM 임의 설명이 아니라 검수 사전을 따르도록.
        파일 부재·파싱 실패는 graceful(빈 블록 — 섹션은 정상 생성).
        """
        try:
            items = json.loads((_DICTS / "terminology.json").read_text(encoding="utf-8")).get(
                "items", []
            )
        except (OSError, ValueError):
            return []
        rows = [
            f"- {it['term']}({it['hanja']}): {it['definition']}"
            if it.get("hanja")
            else f"- {it['term']}: {it['definition']}"
            for it in items
            if it.get("term") and it.get("definition")
        ]
        if not rows:
            return []
        return [
            "[용어 사전 — 본문에 등장한 용어만 골라 아래 정의를 기준으로 짧게 풀이할 것(임의 정의 "
            "생성 금지). 전부 나열하지 말 것]",
            *rows,
        ]

    def ganji_calendar_md(self) -> str:
        """[간지 달력표] — 엔진 결정론적 간지를 마크다운 표로(대운 생애·세운·월운).

        절대원칙 1(간지는 LLM이 계산·변형 금지)에 따라 이 표는 LLM이 만들지 않고 엔진 계산값을
        그대로 렌더링해 섹션 끝에 첨부한다(분량 캡 면제 — 참조 자료). 범위는 상품별: 인생총운
        (RPT_FULL)=세운·월운 향후 10년, 그 외(지정년 등)=해당 연도 1년. 대운은 항상 생애 전체.
        간지 데이터 부재 시 빈 문자열(graceful).
        """
        lc = self.result.luck_cycles
        if lc is None or not lc.daewoon_table:
            return ""
        is_full = self._spec.product_code == "RPT_FULL"
        base_year = self.today.year if is_full else int(self._spec.period.start[:4])
        span = 10 if is_full else 1
        out: list[str] = ["## 간지 달력표 (엔진 계산값 — 참고용)"]
        # 대운(생애) — 천간(계기)·지지(현실 기반) 십성까지.
        out += [
            "",
            "### 대운 (10년 주기 · 생애)",
            "| 나이 | 연도 | 간지 | 천간(십성) | 지지(십성) |",
            "|---|---|---|---|---|",
        ]
        for d in lc.daewoon_table:
            out.append(
                f"| {d.start_age}~{d.start_age + 9}세 | "
                f"{d.approx_start_date.year}~{d.approx_end_date.year} | {_ganji_ko(d.ganji)} | "
                f"{d.stem} {d.stem_ten_god} | {d.branch} {d.branch_ten_god} |"
            )
        # 세운(향후 span년) — 생애 세운(daewoon.sewoon)에서 창에 드는 해만.
        sew: dict[int, Any] = {}
        for d in lc.daewoon_table:
            for p in d.sewoon:
                try:
                    yr = int(p.label)
                except ValueError:
                    continue
                if base_year <= yr < base_year + span:
                    sew[yr] = p
        if sew:
            title = f"### 세운 (향후 {span}년)" if span > 1 else f"### 세운 ({base_year}년)"
            out += [
                "",
                title,
                "| 연도 | 간지 | 천간(십성) | 지지(십성) |",
                "|---|---|---|---|",
            ]
            for yr in sorted(sew):
                p = sew[yr]
                out.append(
                    f"| {yr} | {_ganji_ko(p.ganji)} | {p.stem} {p.stem_ten_god} | "
                    f"{p.branch} {p.branch_ten_god} |"
                )
        # 월운(향후 span년 · 절기 기준) — 연도별 그룹. luck_months는 결정론적 온디맨드 생성.
        out += ["", f"### 월운 (향후 {span}년 · 절기 기준)" if span > 1 else "### 월운 (절기 기준)"]
        for yr in range(base_year, base_year + span):
            try:
                months = luck_months(self._chart_birth, yr)
            except (ValueError, RuntimeError):
                continue
            if not months:
                continue
            out += [
                "",
                f"**{yr}년**",
                "| 월 | 간지 | 천간(십성) | 지지(십성) |",
                "|---|---|---|---|",
            ]
            for p in months:
                mm = int(p.label[5:7]) if len(p.label) >= 7 else 0
                out.append(
                    f"| {mm}월 | {_ganji_ko(p.ganji)} | {p.stem} {p.stem_ten_god} | "
                    f"{p.branch} {p.branch_ten_god} |"
                )
        return "\n".join(out)


# 주제 코드 → 한글 라벨(프레이밍 표기용). frontend themeLabel과 의미 정합.
_TOPIC_KO: dict[str, str] = {
    "career": "직업·사업운",
    "wealth": "재물운",
    "relationship": "애정·관계운",
    "health": "건강운",
    "education": "학업·시험운",
    "relocation": "이사·이동운",
    "compatibility": "궁합",
}


def _product_framing(spec: ReportSpec) -> str:
    """상품·기간 유형별 프롬프트 프레이밍 — 케이스마다 서술 태도를 명시(반복·편향 방지).

    인생총운(RPT_FULL)/지정년총운(RPT_YEAR)/지정기간 intent운(RPT_FOCUS)을 구분해, 강신호
    반복·단일 intent 편향을 프롬프트 차원에서 차단한다(2026-06-16 사용자 확정 이슈2·3).
    """
    if spec.product_code == "RPT_FULL":
        return (
            "[풀이 유형 — 인생총운] 생애 전체를 조망하는 풀이다. 대운 단위의 큰 흐름과 전환점을 "
            "우선하고, 특정 한 달·한 신호를 여러 섹션에 반복하지 말 것. 각 섹션은 자기 주제(원국·"
            "성격·대운·직업·재물·관계·건강 등)에 고유한 내용으로 채운다."
        )
    if spec.product_code == "RPT_YEAR":
        y = spec.period.start[:4]
        return (
            f"[풀이 유형 — {y}년 한해풀이] 단일 연도 풀이다. 한두 개의 강한 신호(예: 특정 달의 큰 "
            "이동수)를 모든 섹션에 반복하지 말 것. 12개월 전체를 고르게 다루고, 도메인(직업·재물·"
            "관계·건강)별로 내용을 분산한다. 좋은 운만이 아니라 주의(흉)운도 함께 짚고, 각 운을 "
            "어떻게 활용·대비할지 실천 방향을 곁들인다."
        )
    topic_ko = _TOPIC_KO.get(spec.topic or "", spec.topic or "주제")
    return (
        f"[풀이 유형 — {topic_ko} 집중({spec.period.start}~{spec.period.end})] 이 주제에 집중하는 "
        "풀이다. 주제와 무관한 일반론으로 분량을 채우지 말고, 이 도메인의 신호를 시점 클러스터로 "
        "묶어 해당 기간의 흐름 중심으로 서술한다. 좋은 시기와 주의 시기를 함께 짚는다."
    )


def _topic_period(spec: ReportSpec) -> _TopicPeriodSpec:
    """ReportSpec 기간 → Topic Builder PeriodSpec(연 단위 — 모듈은 연·월 신호 사용)."""
    return _TopicPeriodSpec(
        start=spec.period.start,
        end=spec.period.end,
        granularity="year",
    )


def _topic_module_block(module_id: str, data: _ReportData, spec: ReportSpec) -> list[str]:
    """섹션 의존 Topic Builder 모듈(M01~M15) 실행 → 확정 신호·정책 톤(옵션1 배선).

    T0/T1/E* 등 비-토픽 ref는 무시. 모듈별 extras 공급, 실패는 graceful(빈 줄). findings는 점수
    확정값(새 수치 금지), tone_notes의 모듈 특화분만 정책 지침으로 싣는다(절대원칙 8 일관 적용).
    """
    if module_id not in _TOPIC_MODULES:
        return []
    period = _topic_period(spec)
    try:
        if module_id in ("M01", "M02", "M07", "M08", "M09", "M11", "M12", "M15"):
            ctx = build_topic_context(module_id, spec.subjects, period, data.composites)
        elif module_id in ("M03", "M04", "M05", "M06"):
            if not data.natal_ten_god_dist:
                return []
            ctx = build_topic_context(
                module_id,
                spec.subjects,
                period,
                data.composites,
                natal_ten_god_dist=data.natal_ten_god_dist,
            )
        elif module_id == "M14":
            ctx = build_topic_context(
                module_id,
                spec.subjects,
                period,
                [],
                birth=data.birth,
                scorer=data.scorer,
                compute=calculate,
            )
        elif module_id == "M13":
            if data.partner_result is None or data.partner_summary is None:
                return []
            ctx = build_topic_context(
                module_id,
                spec.subjects,
                period,
                [],
                self_result=data.result,
                partner_result=data.partner_result,
                self_useful=data.summary.useful_gods,
                partner_useful=data.partner_summary.useful_gods,
            )
        else:  # M10 이사 복합은 별도 relocation_* 경로가 담당
            return []
    except Exception:  # noqa: BLE001 — 모듈 실패가 섹션·리포트를 막지 않도록(규칙11)
        return []
    if not ctx.findings:
        return []
    lines = [
        f"[{module_id}·{_TOPIC_MODULES[module_id]} 토픽 신호 — 엔진 확정(점수·근거 고정, "
        "표 밖 새 수치 생성 금지)]"
    ]
    lines += [f"- {f.summary} (점수 {f.score})" for f in ctx.findings[:4]]
    # 모듈 특화 정책 톤(base 톤 1줄 제외)만 표현 지침으로 — 절대원칙 8 가드 일관 적용.
    module_notes = ctx.style_rules.tone_notes[1:]
    if module_notes:
        lines.append("표현 지침(정책): " + " / ".join(module_notes))
    return lines


def _region_report_block(data: _ReportData, spec: ReportSpec) -> list[str]:
    """거주지 정보가 있으면 현 지역 평가 + 살면 좋은 지역 추천(사용자 확정). 없으면 빈 줄.

    내 용희기구신 × 지역 오행으로 현 거주지 적합을 평가하고, 읍면동 계산→시군구 surface로 추천한다.
    검수 전 초안·지형 GIS 미반영 1차 추정(단정 금지). compiled 미빌드·거주지 미설정 시 graceful.
    """
    residence = _residence_region(data.owner_id)
    if not residence:
        return []
    orch = _get_region_orchestrator()
    if orch is None:
        return []
    try:
        from saju_engines.region_recommendation_orchestrator import resolve_intent_mode
        from saju_shared_types.region_element import RegionResolution

        ug = data.summary.useful_gods
        roles = {
            "yongsin": ug.yongsin,
            "huisin": ug.heesin,
            "gisin": ug.gisin,
            "gusin": ug.gusin,
        }
        if not roles["yongsin"]:
            return []
        intent_mode = resolve_intent_mode("이사")
        eval_payload = orch.recommend_payload(  # type: ignore[attr-defined]
            orch.build_query(  # type: ignore[attr-defined]
                intent_mode=intent_mode,
                roles=roles,
                base_location=residence,
                candidate_regions=[residence],
                resolution=RegionResolution.SIGUNGU,
                top_n=1,
            )
        )
        sido = residence.split()[0] if residence.split() else None
        rec_payload = orch.recommend_payload(  # type: ignore[attr-defined]
            orch.build_query(  # type: ignore[attr-defined]
                intent_mode=intent_mode,
                roles=roles,
                base_location=residence,
                candidate_scope=sido,
                resolution=RegionResolution.EUP_MYEON_DONG,
                top_n=20,
            )
        )
    except Exception:  # noqa: BLE001 — 지역 평가 실패가 리포트를 막지 않도록
        return []
    lines = [
        "[거주 지역 평가·추천(참고) — 내 용희기구신 × 지역 오행. 검수 전 초안·지형 GIS 미반영 "
        "1차 추정, 단정 금지(실거주 만족은 생활 여건이 좌우)]"
    ]
    er = eval_payload.get("regions", [])
    if er:
        e = er[0]
        pos = "·".join(f"{f['element']}({f['role']})" for f in e["fit_summary"]["positive"])
        neg = "·".join(f"{f['element']}({f['role']})" for f in e["fit_summary"]["negative"])
        line = f"현 거주지 {residence}: 적합 {e['match_score']}"
        if pos:
            line += f" / 유리 {pos}"
        if neg:
            line += f" / 주의 {neg}"
        lines.append(line)
    surface = rec_payload.get("surface", [])
    if surface:
        recs = ", ".join(f"{g['sigungu_full_name']}(적합 {g['match_score']})" for g in surface[:5])
        lines.append(f"살면 좋은 지역(시군구 단위): {recs}")
    return lines if len(lines) > 1 else []


# 거주지 평가·추천을 싣는 섹션 — 개운·보완(F-20)·이사 방위(RL-04).
_REGION_REPORT_SECTIONS = {"F-20", "RL-04"}


def build_section_context(
    plan: SectionPlan, spec: ReportSpec, data: _ReportData, *, reduction_level: int = 0
) -> SectionContext:
    """섹션 1개의 실데이터 컨텍스트(docs/06 계약 + docs/10 검사 기준).

    reduction_level>0 — Context Reduction(report 경로, docs/09 L333). 섹션 입력이 토큰 상한을
    넘을 때만 generate_fn이 단계를 올려 재호출한다. 1단계=다년 월별 흐름을 ★주목 달로 축소,
    2단계=연도별 흐름도 ★주목 해로 축소. 상한 내 섹션은 reduction_level=0(전체 유지).
    """
    yongsin = (
        data.summary.useful_gods.yongsin[0]
        if plan.section_id in YONGSIN_SECTIONS and data.summary.useful_gods.yongsin
        else None
    )
    guide = _SECTION_GUIDES.get(plan.section_id, _DEFAULT_GUIDE)
    sid = plan.section_id
    is_natal_section = sid in _NATAL_SECTIONS
    lines = list(data.prefix_lines)
    lines += data.tense_anchor_lines(spec)  # '오늘'·시제 사실 주입(시제 추론 불요)
    lines += ["", _product_framing(spec)]  # 케이스별 프레이밍(반복·편향 방지)
    lines += [
        "",
        f"[섹션 과제 — {sid}. {plan.title}]",
        f"분량: {plan.target_chars.min}~{plan.target_chars.max}자(공백 포함).",
        guide,
        "입력에 없는 간지·점수·연도를 만들지 말 것. 단정 표현 금지.",
        "인사말·원국 전체 재설명은 생략하고(앞 섹션에서 1회면 충분) 이 섹션 과제에 바로 집중할 것.",
        "첫 문장을 '○○님은 ~한 사주/일간/성향' 류 명식 공통 묘사로 시작하지 말 것 — 독자는 "
        "앞 페이지에서 같은 소개를 이미 읽었다. 이 섹션 주제의 구체 내용으로 바로 시작하고, "
        "명식 근거는 본문 중간에 필요한 만큼만 인용한다.",
        "지면 절약: 문단은 빈 줄 하나로만 구분하고 연속 빈 줄을 넣지 말 것. 잔 소제목 남발과 "
        "한 문장씩 끊은 단락을 피하고, 여러 문장을 묶은 조밀한 산문 문단으로 작성할 것.",
    ]
    # 서두 반복 금지(동적) — 직전에 생성된 섹션들의 실제 첫 문장을 보여주고 같은 패턴의 서두를
    # 막는다(2026-07-06 테스터 지적: 매 페이지 첫 문장이 비슷해 페이지를 안 넘긴 느낌).
    # plan_report(dry-run)·첫 섹션은 기록이 없어 미부착(하위호환).
    if data.recent_openings:
        lines += [
            "",
            "[서두 반복 금지 — 직전 섹션들이 이미 사용한 첫 문장]",
            *[f"- {s}" for s in data.recent_openings],
            "위 문장들과 같은 패턴·유사 표현으로 이 섹션을 시작하지 말 것. 독자가 페이지를 "
            "넘길 때마다 새 내용이 시작된다고 느끼도록, 이 섹션 주제 고유의 내용으로 서두를 "
            "열 것.",
        ]
    # 구조 패턴 태그(구조 라벨 — 사건·길흉 확정 아님). 원국 섹션=도메인 무관 상위 N,
    # 도메인 섹션=해당 도메인 우선 선별. 과거·메타 등 도메인 없는 섹션은 생략(반복 방지).
    _sp_domains = None if is_natal_section else _DOMAIN_EVENT_KEYS.get(_SECTION_DOMAIN.get(sid, ""))
    if is_natal_section or _sp_domains:
        _patterns = select_llm_patterns(data.detected_patterns, domains=_sp_domains)
        if _patterns:
            lines += [
                "",
                "[구조 패턴 — 의미 설명 태그(구조 라벨일 뿐, 사건·길흉 확정 아님·도메인은 후보)]",
                *[p.llm_tag for p in _patterns],
                _STRUCTURE_PATTERN_INSTRUCTION,
            ]
    # 능동 제안(docs/15 Phase C) — 재물·직업 도메인 섹션에 '고려' 수준 재료 주입.
    # 목차·판정·점수 불변(절대원칙 10) — 섹션 컨텍스트 재료만 추가한다.
    _ds_domain = _SECTION_DOMAIN.get(sid)
    if _ds_domain in ("wealth", "career"):
        _suggestion_lines = format_direction_suggestion_lines(
            select_direction_suggestions(data.direction_suggestions, domains=[_ds_domain])
        )
        if _suggestion_lines:
            lines += [*_suggestion_lines, DIRECTION_SUGGESTION_INSTRUCTION]
    # 재물 준비기(P3) — 5년 종합(W-06)·행동 전략(W-08)에만 서술 전용 맥락 주입(판정 불변).
    if sid in ("W-06", "W-08"):
        _prep_lines = preparation_context_lines(data.preparation_context)
        if _prep_lines:
            lines += ["", *_prep_lines]
    # 물상(2단계 프로필) 사실 맥락 — 도메인 섹션에만 해당 항목 주입(상황 구체화, 판정 불변).
    _sd = _SECTION_DOMAIN.get(sid)
    if _sd:
        _facts = profile_facts_lines(data.extended_profile, _sd)
        if _facts:
            lines += [
                "",
                "[사용자 정보 — 입력한 사실 맥락(상황 구체화용, 판정 불변)]",
                *_facts,
                _PROFILE_FACTS_INSTRUCTION,
            ]
    # 궁합(RP-*) 전 섹션 — 사용자가 지정한 '상대와의 관계'를 풀이 방향으로 주입
    # (2026-07-03 데굴님 지시: 상사/연인/결혼예정/이혼예정 등 관계에 맞는 풀이).
    # 미지정이면 빈 목록 — 기존 중립 궁합 톤 그대로(하위호환·판정 불변).
    if sid.startswith("RP-"):
        _rel_lines = relation_context_lines(data.partner_relation_type)
        if _rel_lines:
            lines += ["", *_rel_lines]
    if sid in _PARTNER_NATAL_SECTIONS:
        lines += ["", *data.partner_natal_block()]
    elif sid in _COMPAT_SECTIONS:
        lines += ["", *data.compatibility_block()]
    elif sid in _SCORE_TABLE_SECTIONS:
        lines.append("")
        lines.append("[점수표 — 아래 표를 그대로 인용. 표 밖 새 수치 생성 금지]")
        lines += score_table_lines(data.result, data.candidates)
    elif not is_natal_section:
        lines.append("")
        section_domain = _SECTION_DOMAIN.get(sid)
        # 전 구간 스펙트럼(반복·편향 차단) — 연도 표 → 월 표 순. 테마 섹션은 대표 사건을 주제로
        # 한정(운 품질 등급은 도메인 무관 표기). Y-05 등 도메인 없는 섹션은 교차도메인 그대로.
        if sid in _YEAR_SPECTRUM_SECTIONS:
            lines += data.year_spectrum_block(section_domain, notable_only=reduction_level >= 2)
            lines.append("")
        if sid in _MONTH_OVERVIEW_SECTIONS:
            lines += data.month_overview_block(section_domain, notable_only=reduction_level >= 1)
            # 상담 사례 파생(P0) — 주목할 달의 시기 단정 차단('8월에 됩니다' 금지,
            # activation window 표현). 사례 모방 금지 포인트 §6 — 우선 J-06만(데굴님 확정 스코프).
            if sid in _DATE_CERTAINTY_SECTIONS:
                lines.append(AVOID_DATE_CERTAINTY_DIRECTIVE)
            lines.append("")
        # 후보 상세 — 도메인 스코프면 자기 도메인 후보(길·흉 포함), 아니면 전역 top 후보.
        if section_domain is not None:
            lines += data.luck_block(data.domain_candidates(section_domain))
        else:
            # 2부 과거·메타 섹션은 [대운표]만 — 미래 이벤트 후보가 섞이는 시간범위 불일치 차단.
            lines += data.luck_block(daewoon_only=sid in _DAEWOON_ONLY_SECTIONS)
        # 재물 섹션 — 원국 횡재 그릇(운 분리 잠재구조) 표면화(Phase 1).
        if sid in _WEALTH_CAPACITY_SECTIONS:
            lines += ["", *data.wealth_capacity_block()]
    elif data.evidence_paths:
        # 명식 섹션도 내부 근거를 활용하되, 분류 용어를 그대로 노출하지 말고 일상어로 풀어 녹인다.
        lines += [
            "",
            "[내부 근거 — '관계 발동·용기신 품질' 등 분류 용어나 '근거 경로:' 표기를 본문에 "
            "그대로 쓰지 말고, 이 인과를 일상어로 풀어 설명에 녹일 것]",
            *data.evidence_paths,
        ]
    # 관계·재물구조 섹션 — 결혼·자산 자원 구조(성별 인지, 중립) 표면화. 명식/운 분기와 무관.
    # 배우자성 성별 가드(남=재성·여=관성) + 연애 자기인식(이상형 인정) 가드를 함께 실어 반대 성별
    # 기준 오역·취향 부정을 차단(2026-06-22).
    if sid in _MARRIAGE_RESOURCE_SECTIONS:
        lines += [
            "",
            spouse_star_directive(data.marriage_resource.gender),
            *data.marriage_resource_block(),
            RELATIONSHIP_SELF_AWARENESS_DIRECTIVE,
            TENDENCY_SHIFT_DIRECTIVE,
        ]
        # 외적 인상·매력 신호 — notable 이상일 때만 표면화(미해당이면 빈 목록 → 무언급).
        impression = data.external_impression_block()
        if impression:
            lines += ["", *impression]
        # 궁위 관계망(P3) — 연·월·일·시 궁위 간 관계질(설명 레이어, 점수 미개입).
        network = palace_network_lines(analyze_palace_network(data.result), Domain.RELATIONSHIP)
        if network:
            lines += ["", *network]
    # 건강 섹션 — 원국 취약 구조(의료 면책 동반). C-02/C-06은 health 주제일 때만.
    if sid in _HEALTH_VULN_SECTIONS or (sid in _HEALTH_TOPIC_SECTIONS and spec.topic == "health"):
        lines += ["", *data.health_vulnerability_block()]
    # 부/귀 지향 — 명식 구조·직업 섹션.
    if sid in _WEALTH_STATUS_SECTIONS:
        lines += ["", *data.wealth_status_block()]
    # 이사 테마 — 십성 이유분류(이유·집성격 / 리스크·체크리스트) surface(이사 고도화 R2).
    if sid in _RELOCATION_REASON_SECTIONS:
        lines += ["", *data.relocation_reason_block(spec)]
    if sid in _RELOCATION_RISK_SECTIONS:
        lines += ["", *data.relocation_risk_block(spec)]
    # 현실 과업 절차 참고(2026-07-22) — 행동 전략·체크리스트 섹션에 L1/L2 절차 지식 부착.
    _proc_key = _PROCEDURE_PACK_SECTIONS.get(sid)
    if _proc_key is not None:
        lines += ["", procedure_reference_block(TASK_PACKS[_proc_key])]
    # 이사 테마 — M10 방위 적합(RL-04) / 월별 이동운 흐름·충돌(RL-06) surface.
    if sid in _RELOCATION_DIRECTION_SECTIONS:
        lines += ["", *data.relocation_direction_block(spec)]
    if sid in _RELOCATION_FLOW_SECTIONS:
        lines += ["", *data.relocation_flow_block(spec)]
    # 선발·배치 보조(2026-07-14 방안 2 — 목차 불변): 운 신호 섹션에 조건부 부착.
    # 이사→청약(RL-04), 직업→근무지 배치(J-04), 학업 FOCUS→학교·기숙사 배정(C-04).
    # notable 미달이면 빈 목록 → 무언급.
    _sel_domain = _SELECTION_AUX_SECTIONS.get(sid) or (
        "school_assignment" if sid == "C-04" and spec.topic == "education" else None
    )
    if _sel_domain is not None:
        _sel_aux = data.selection_block(_sel_domain)
        if _sel_aux:
            lines += ["", *_sel_aux]
    # 연간 총운(Y-04) — 세운·대운 천간 십성 이사 유형 간결 surface(인생 총운엔 미부착).
    if sid in _RELOCATION_YEAR_SECTIONS:
        lines += ["", *data.relocation_year_block(spec)]
    # 시대 기운(연운) — 개인 풀이 앞 맥락. Y-01(한해풀이 그 해)·F-11(총운 올해).
    if sid == "Y-01":
        lines += ["", *data.era_energy_block(int(spec.period.start[:4]))]
    elif sid == "F-11":
        lines += ["", *data.era_energy_block(data.today.year)]
    # 대운 풀이 관점·교체기 신호·안 맞는 구간 조언(2026-06-23, 전문가 강의 참고 — 서술 가이드).
    if sid in _DAEWOON_FRAMING_SECTIONS:
        lines += ["", _DAEWOON_FRAMING_DIRECTIVE]
        # 발현 진행 예외 모드(2026-07-21) — 기본 그라데이션을 뒤집는 대운만 주입(서술 전용).
        _prog_lines = _daewoon_progression_lines(data.daewoon_progression)
        if _prog_lines:
            lines += ["", *_prog_lines]
    if sid in _DAEWOON_TRANSITION_SIGNAL_SECTIONS:
        lines += ["", _DAEWOON_TRANSITION_SIGNALS_DIRECTIVE]
    if sid in _OFF_PEAK_ADVICE_SECTIONS:
        lines += ["", _OFF_PEAK_DAEWOON_ADVICE_DIRECTIVE]
        # 상담 사례 파생(P0) — 행동 전략은 '극복 아니라 관리' + 운 품질→의사결정 태도 번역.
        lines += [MANAGE_NOT_OVERCOME_DIRECTIVE, DECISION_ATTITUDE_DIRECTIVE]
    # 상담 사례 파생(P1·P2) — 활동 키워드·개운 행동 블록 + 키워드 조합 번역 지시(J-07).
    if sid in _ACTIVITY_REMEDY_SECTIONS:
        _ar = data.activity_remedy_block()
        if _ar:
            lines += ["", *_ar, KEYWORD_COMBO_TRANSLATION_DIRECTIVE]
    # 상담 사례 파생(P0) — 관계 행동 전략의 탈규범 안심(결혼 필수 강요 차단).
    if sid in _NON_NORMATIVE_SECTIONS:
        lines += ["", NON_NORMATIVE_REASSURANCE_DIRECTIVE]
    # 거주지 평가·추천(옵션1) — 거주 정보가 있으면 현 지역 평가 + 살면 좋은 지역(F-20·RL-04).
    if sid in _REGION_REPORT_SECTIONS:
        region_block = _region_report_block(data, spec)
        if region_block:
            lines += ["", *region_block]
    # Topic Builder(M01~M15) 배선(옵션1) — 섹션이 선언한 모듈을 실행해 확정 신호·정책 톤 주입.
    seen_modules: set[str] = set()
    for mc in plan.module_calls:
        if mc.module_id in seen_modules:
            continue
        seen_modules.add(mc.module_id)
        block = data.topic_module_block(mc.module_id, spec)
        if block:
            lines += ["", *block]
    # 간지 달력표 섹션(F-22·Y-12) — 용어 해설을 검수 사전 기준으로(간지 달력표 자체는 생성 후
    # 엔진이 결정론적으로 첨부하므로 여기 본문 데이터엔 넣지 않는다 — 절대원칙 1).
    if sid in _GANJI_CALENDAR_SECTIONS:
        term_block = data.terminology_block()
        if term_block:
            lines += ["", *term_block]
    subject_label = spec.subjects[0].label if spec.subjects else "본인"
    return SectionContext(
        section_id=plan.section_id,
        subject_label=subject_label,
        allowed_ganji=data.allowed_ganji,
        allowed_scores=data.allowed_scores,
        allowed_years=data.allowed_years,
        yongsin_element=yongsin,
        evidence_paths=data.evidence_paths,
        multi_subject=len(spec.subjects) > 1,
        body_prompt="\n".join(lines),
    )


def plan_report(
    birth: BirthInput,
    spec: ReportSpec,
    today: date | None = None,
    *,
    partner_birth: BirthInput | None = None,
) -> list[SectionContext]:
    """dry-run — 전 섹션의 실데이터 컨텍스트만 생성(LLM 미호출, 검증·개발용)."""
    data = _ReportData(birth, spec, today or date.today(), partner_birth=partner_birth)
    return [build_section_context(p, spec, data) for p in build_section_plans(spec)]


# 위험 노출 대상 섹션(테마사주 배선 — 2026-07-17 데굴님 승인): 기존 목차의
# C-06 "주의 시기·리스크" 슬롯 재사용(목차 변경 없음). 감수된 채팅 경로와
# 동일한 게이트·상태기·감사(run_exposed_reading)를 소비한다.
_RISK_EXPOSED_SECTION_ID = "C-06"


def _try_risk_exposed_section(
    data: _ReportData,
    spec: ReportSpec,
    body_prompt: str,
    system: str,
    call_type: str,
    subject_id: str | None,
) -> tuple[str | None, str]:
    """C-06 위험 노출 시도 — (완성 본문 | None, 유효 prompt).

    리포트는 기간이 상품 파라미터로 명시적이므로 파서 매핑 없이
    period_overview/future/연도 범위를 직접 전달한다(시간 재해석 없음 —
    allowed_years가 SSOT). 반환: INJECTED 성공=(감사 통과 본문, _),
    그 외=(None, 유효 prompt — SUPPRESSED면 guard 부착본, BYPASS/실패면
    원본)으로 기존 generate_reading 경로가 이어받는다(BLOCK 포함:
    위험 없는 일반 생성으로 폴백 — 위반 초안은 전달되지 않음).
    """
    from saju_engines.risk_presentation import estimate_tokens

    from . import risk_exposure_bootstrap as _reb
    from . import risk_exposure_service as _res

    if not _res.exposure_mode_active():
        return None, body_prompt
    try:
        years = data.allowed_years
        if not years:
            return None, body_prompt
        payload = _reb.build_risk_payload(list(data.scorer.risk_shadow))
        inputs = _reb.exposure_runtime_inputs(call_type)
        prompt, _sys, obs = _res.apply_risk_exposure(
            body_prompt, system,
            payload=payload,
            subject_id=subject_id,
            question_type="period_overview",
            temporal_scope="future",
            future_period_range=(str(min(years)), str(max(years))),
            counter=inputs["counter"],
            counter_model_id=inputs["counter_model_id"],
            resolved_model_id=inputs["resolved_model_id"],
            model_context_limit=inputs["context_limit"],
            base_prompt_tokens=estimate_tokens(body_prompt),
            user_input_tokens=0,
            existing_context_tokens=estimate_tokens(system),
            response_reserve=inputs["response_reserve"])
        _logger.info("report_risk_gate section=%s %s",
                     _RISK_EXPOSED_SECTION_ID, obs)
        if obs.get("disposition") != "INJECTED" or not payload:
            # SUPPRESSED=guard 부착 prompt·BYPASS=원본 — 기존 경로로.
            return None, prompt
        flow = _reb.run_exposed_reading(
            baseline_prompt=body_prompt,
            injected_prompt=prompt,
            system=system,
            observability=obs,
            payload=payload,
            call_type=call_type,
            request_context_id=(
                f"report:{subject_id or 'anon'}:{spec.product_code}:"
                f"{_RISK_EXPOSED_SECTION_ID}"),
            renderer=_tighten)
        if flow["outcome"] in ("DELIVER_GENERATED",
                               "DELIVER_SAFE_FALLBACK"):
            return flow["final_text"], prompt
        # BLOCK: 위험 본문 미전달 — 위험 없는 기존 생성으로 폴백(원본).
        return None, body_prompt
    except Exception:  # noqa: BLE001 — 위험 경로 실패=기존 경로(불변)
        _logger.exception("report_risk_section 실패 — 기존 경로 폴백")
        return None, body_prompt


def generate_report(
    birth: BirthInput,
    spec: ReportSpec,
    today: date | None = None,
    display_name: str = "회원",
    *,
    owner_id: str | None = None,
    subject_id: str | None = None,
    partner_birth: BirthInput | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
) -> ReportResult:
    """보고서 실생성 — ReportBuilder에 실데이터 컨텍스트 + llm_client 주입.

    owner_id·subject_id가 있으면 개인화(현실 신호 시그니처·코호트) LEI 정렬축이 후보 선별에 반영.

    Raises:
        RuntimeError: LLM 키 미설정(메인·폴백 모두) — 호출 측에서 dry-run 안내.
    """
    if not llm_client.is_available():
        raise RuntimeError("LLM API 키 미설정 — plan_report(dry-run)로 검증하세요")
    data = _ReportData(
        birth,
        spec,
        today or date.today(),
        owner_id=owner_id,
        subject_id=subject_id,
        partner_birth=partner_birth,
    )
    call_type = "report_full_section" if spec.product_code == "RPT_FULL" else "report_focus_section"
    persona_block = None
    try:
        from saju_engines.persona import PersonaEngine

        persona_block = PersonaEngine(_DICTS).build_block(spec.persona, display_name)
    except ValueError:
        persona_block = None

    def _regen_note(prompt: str, attempt: int) -> str:
        """정합성 재생성(attempt>0) 시 본문에 덧붙는 교정 지시 — 토큰 축소와 무관."""
        if attempt <= 0:
            return prompt
        return prompt + (
            f"\n\n[재생성 {attempt}회차] 직전 응답이 정합성 검사에 실패했다 — "
            "분량·간지·점수 규칙을 다시 확인하고, 내부 분류 용어(관계 발동/용기신 품질/"
            "복수 가능성 등)와 '근거 경로:' 표기를 본문에 노출하지 말 것(일상어로 풀어 서술)."
        )

    def generate_fn(plan: SectionPlan, context: SectionContext, attempt: int):
        # 보고서 전용 시스템 프롬프트(대화와 분리 — '정보 없음' 회피 문구 미포함).
        system = llm_client._REPORT_SYSTEM_PROMPT
        if persona_block:
            system = system + "\n\n" + persona_block
        # C-06 위험 노출(테마사주 배선): 감수된 게이트·상태기·감사 전체를
        # 채팅과 동일하게 소비 — INJECTED 성공 시 그 본문 사용, 그 외
        # (BYPASS/SUPPRESSED/BLOCK)는 유효 prompt로 기존 경로 계속.
        risk_prompt_override: str | None = None
        if plan.section_id == _RISK_EXPOSED_SECTION_ID and attempt == 0:
            risk_text, effective_prompt = _try_risk_exposed_section(
                data, spec, context.body_prompt, system, call_type,
                subject_id or owner_id)
            if risk_text is not None:
                data.record_opening(risk_text)
                return risk_text, 0, len(risk_text)
            if effective_prompt != context.body_prompt:
                risk_prompt_override = effective_prompt  # SUPPRESSED guard
        # Context Reduction(docs/09 L333) — 섹션 입력(본문+시스템)이 토큰 상한을 넘으면(가드
        # 예외) 단계를 올려 가변 블록(다년 월별·연도별 흐름)을 ★주목 위주로 축소하고 재호출한다.
        # 상한 내 섹션은 0단계로 한 번에 통과(전체 12개월 유지) — 초과한 섹션만 축소된다.
        last_exc: TokenBudgetExceeded | None = None
        for reduction_level in range(_MAX_REPORT_REDUCTION + 1):
            ctx = (
                context
                if reduction_level == 0
                else build_section_context(plan, spec, data, reduction_level=reduction_level)
            )
            try:
                body = (risk_prompt_override
                        if risk_prompt_override is not None
                        and reduction_level == 0 else ctx.body_prompt)
                text = llm_client.generate_reading(
                    _regen_note(body, attempt),
                    call_type=call_type,
                    system=system,
                    product_code=f"{spec.product_code}:{plan.section_id}",
                    owner_id=owner_id,
                    surface="report",
                    ref_id=subject_id,
                )
                if reduction_level > 0:
                    _logger.info(
                        "report Context Reduction 적용: section=%s level=%d (입력 상한 초과 회피)",
                        plan.section_id,
                        reduction_level,
                    )
                text = _tighten(text)  # 지면 낭비 정규화(공백수정)
                data.record_opening(text)  # 다음 섹션의 '서두 반복 금지' 재료(순차 생성)
                return text, 0, len(text)  # 토큰은 llm_client 장부가 집계(cached 포함)
            except TokenBudgetExceeded as exc:
                last_exc = exc  # 다음 단계로 더 축소해 재시도
        # 최대 축소(연도별까지)로도 상한을 못 맞춘 경우만 마감 — 현실 입력에선 미발생.
        raise last_exc  # type: ignore[misc]

    builder = ReportBuilder(
        dictionaries_dir=_DICTS,
        context_builder=lambda plan, s: build_section_context(plan, s, data),
        generate_fn=generate_fn,
        progress_fn=progress_fn,
    )
    result = builder.build(spec, display_name=display_name)
    # 간지 달력표 결정론적 첨부 — LLM 생성·분량 캡(_repair_section) 모두 거친 뒤 본문 끝에 붙인다.
    # 표는 엔진 계산값이므로 절단·정합성 검사·간지 변형 대상에서 제외한다(절대원칙 1).
    cal_md = ""
    for sec in result.sections:
        if sec.section_id in _GANJI_CALENDAR_SECTIONS and sec.passed:
            if not cal_md:
                cal_md = data.ganji_calendar_md()
            if cal_md:
                sec.text = f"{sec.text}\n\n{cal_md}".strip()
    if cal_md:
        result.total_chars = sum(len(s.text) for s in result.sections if s.passed)
    return result
