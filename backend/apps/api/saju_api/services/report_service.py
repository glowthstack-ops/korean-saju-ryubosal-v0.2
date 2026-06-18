"""보고서 생성 서비스 (v2.2.1 PR-E — Phase 9 파이프라인 운영 배선, docs/10).

ReportBuilder(테스트 전용이던 골격)에 **실데이터 컨텍스트 빌더**와 LLM 호출을
주입한다. 섹션 프롬프트 = 고정 prefix(원국·명식 구조+해석 자료 — 대화와 동일,
캐시 적중) + 섹션 과제 + 섹션별 데이터 블록(대운표·이벤트 후보·근거 경로).

분석은 엔진(만세 계산·스코어링)이, 본 서비스는 직렬화와 호출만 한다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from saju_manse_analysis.luck.luck_calendar import luck_month_label

from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.compatibility_engine import analyze_compatibility, compatibility_lines
from saju_engines.context_reducer import (
    build_birth_summary,
    serialize_chart_prefix,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import favorability_map
from saju_engines.hap_lines import luck_hap_mode_lines
from saju_engines.health_vulnerability import analyze_health_vulnerability
from saju_engines.manifestation_branch import branch_summary
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.report_builder import ReportBuilder
from saju_engines.report_event_input import (
    month_overview_lines,
    precise_candidate_clusters,
    score_table_lines,
)
from saju_engines.report_plan import YONGSIN_SECTIONS, build_section_plans
from saju_engines.structural_context import (
    era_energy_lines,
    health_lines,
    marriage_resource_lines,
    wealth_capacity_lines,
    wealth_status_lines,
)
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_engines.wealth_status_lean import analyze_wealth_status_lean
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN as _EVENT_DOMAIN_V2
from saju_shared_types.events import EventCandidate, EventPolarity
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import SubjectKind
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.report import ReportResult, ReportSpec, SectionContext, SectionPlan

from . import llm_client
from .manse_service import calculate
from .personalization import fetch_personal_inputs

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_SCORE_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}
_TOP_CANDIDATES = 8
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


def _period_end_month(period: str) -> str:
    """기간의 끝 달(YYYY-MM) — 연('2026')=그 해 12월, 월('2026-02')=그대로, 일=그 달."""
    if len(period) == 4:
        return f"{period}-12"
    if len(period) == 7:
        return period
    return period[:7]

# 섹션별 작성 지침(docs/10 3·4장 데이터소스 요약 — 목차 규격은 report_plan이 강제).
_SECTION_GUIDES: dict[str, str] = {
    "F-01": "사주 원국의 전체 그림을 소개할 것 — 4주 구성과 각 주의 십성·운성을 쉬운 비유로.",
    "F-02": "일간 글자의 물상과 일주 서사를 중심으로 타고난 기질을 풀어낼 것.",
    "F-03": "원국 십성 구성([명식 해석 자료]의 십성 발췌)을 엮어 사회적 성향을 서술할 것.",
    "F-04": "강약·격국·용신 판정과 그 근거를 설명할 것 — 용신 오행을 명시적으로 표기할 것.",
    "F-05": "신살·공망·특수 구조를 양면(빛/그림자)으로 설명할 것 — 신살은 보조 자료임을 전제.",
    "F-06": "앞 섹션들의 재료를 종합해 성격·취향·행동 패턴의 이야기로 묶을 것.",
    "F-22": "간지 달력표를 요약하고 본문에 쓴 용어를 짧게 풀이할 것.",
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
    "J-06": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
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
    "R-07": "행동 전략을 — 다가서기/거리두기/대화/정리 준비 단위. 상대 강요·운명론 표현 금지.",
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
    "RP-09": "관계 운영 전략을 — 다가서기/거리두기/대화/기대 조정 단위. 강요·확정 표현 금지.",
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
    "Y-12": "이 해 12개월 간지 달력표를 요약하고 본문에 쓴 용어를 짧게 풀이할 것.",
}
_DEFAULT_GUIDE = "아래 데이터 블록의 사실만 사용해 섹션 제목에 맞는 이야기로 서술할 것."
# 명식 구조 섹션(운 데이터 블록 미부착) — 인사·원국 재설명 1회 원칙.
_NATAL_SECTIONS = {
    "F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "C-02",
    "W-02", "W-03", "J-02", "J-03", "R-02", "R-03", "RP-02",
    "RL-02",  # 이사 테마 — 이동·정착 성향(원국 기초)
    "Y-02",  # 한해풀이 — 원국+용신 기초(운 데이터 블록 미부착)
}
# 부록 점수표 섹션(실제 표 부착).
_SCORE_TABLE_SECTIONS = {"C-08", "W-09", "J-08", "R-08", "RP-10", "RL-08"}
# 이사 테마 — 십성 이유분류(reason_profiles) surface 섹션(이사 고도화 R2).
_RELOCATION_REASON_SECTIONS = {"RL-03"}
_RELOCATION_RISK_SECTIONS = {"RL-05"}
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
    "Y-06": "career", "Y-07": "wealth", "Y-08": "relationship", "Y-09": "health",
    "F-15": "career", "F-16": "wealth", "F-17": "relationship", "F-18": "health",
    "RL-04": "relocation", "RL-06": "relocation",  # 이사 테마 — 이동 신호·향후 흐름
}
# 12개월 전체 흐름 표를 부착하는 섹션(한해풀이 월별 흐름 — 모든 달 누락 없이).
_MONTH_OVERVIEW_SECTIONS = {"Y-05"}
# 원국 횡재 그릇 블록을 부착하는 재물 섹션(Phase 1 — 횡재 잠재구조 표면화).
_WEALTH_CAPACITY_SECTIONS = {"W-04", "W-05", "Y-07", "F-16"}
# 결혼·자산 자원 구조 블록을 부착하는 관계·재물구조 섹션(중립 구조 신호 — 신규 키 없음).
# 직업 테마(J-*)에는 부적합이라 미부착(개별 intent는 주제 적합 섹션만 — 선택적).
_MARRIAGE_RESOURCE_SECTIONS = {
    "R-03", "R-05", "RP-03", "RP-04", "F-17", "Y-08", "W-03",
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
        self, birth: BirthInput, spec: ReportSpec, today: date,
        *, owner_id: str | None = None, subject_id: str | None = None,
        partner_birth: BirthInput | None = None,
    ) -> None:
        self.today = today  # 시제 앵커(프롬프트 주입) — 모델이 과거/현재/미래를 추론하지 않도록.
        chart_birth = birth.model_copy(update={"reference_date": today})
        self.result: ManseV2Result = calculate(chart_birth)
        self.scorer = EventEngineV2(_DICTS)
        # 개인화(저장된 subject 한정): 현실 신호 시그니처 + 활성 코호트 → LEI 정렬축.
        # 미설정·실패 시 무개인화 폴백(규칙11).
        sig, cohort = fetch_personal_inputs(owner_id, subject_id, self.result)
        scored = self.scorer.score_legacy_personalized(
            self.result, levels=_SCORE_LEVELS, signature=sig, cohort=cohort,
        )
        in_period = [
            c for c in scored
            if spec.period.start[:4] <= c.period[:4] <= spec.period.end[:4]
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
                c for c in pool
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
        self.wealth_capacity = analyze_wealth_capacity(self.result)  # 원국 횡재 그릇(운 분리)
        self.marriage_resource = analyze_marriage_resource(self.result)  # 결혼·자산 자원(성별 인지)
        self.health_vulnerability = analyze_health_vulnerability(
            self.result, favorability_map(self.result),
        )  # 원국 건강 취약 구조(운 미반영 — 의료 진단·수명 예측 아님)
        self.wealth_status_lean = analyze_wealth_status_lean(self.result)  # 부/귀 지향(원국 구조)
        self.prefix_lines = serialize_chart_prefix(
            self.summary, build_chart_interpretation(self.result),
        )
        self.evidence_paths = self._evidence_paths_for(self.candidates)
        self.allowed_ganji = self._collect_ganji()
        self.allowed_years = self._collect_years(spec)
        # 섹션별 도메인 후보·12개월 표가 surface하는 점수를 모두 허용(검사3 — 미제공 점수 차단은
        # '엔진이 산출하지 않은' 점수만 막으면 됨). 전 scored 점수는 모두 실제 엔진 산출값이다.
        self.allowed_scores = sorted({c.score for c in scored})

        # 관계운 상대(궁합) 모드 — 상대 명식 + 원국A↔원국B 궁합 신호(엔진 계산).
        self.partner_summary = None
        self.partner_prefix_lines: list[str] = []
        self.compatibility = None
        if partner_birth is not None:
            partner_chart = partner_birth.model_copy(update={"reference_date": today})
            partner_result = calculate(partner_chart)
            self.partner_summary = build_birth_summary(partner_result)
            self.partner_prefix_lines = serialize_chart_prefix(
                self.partner_summary, build_chart_interpretation(partner_result),
            )
            self_label = spec.subjects[0].label if spec.subjects else "본인"
            partner_label = next(
                (s.label for s in spec.subjects if s.kind != SubjectKind.SELF), "상대",
            )
            self.compatibility = analyze_compatibility(
                self.result, partner_result,
                self.summary.useful_gods, self.partner_summary.useful_gods,
                self_label=self_label, partner_label=partner_label,
            )

    def partner_natal_block(self) -> list[str]:
        """상대 명식 구조 블록(RP-03 — 상대는 어떤 사람인가)."""
        if not self.partner_prefix_lines:
            return ["[상대 명식 없음 — 상대 출생정보가 등록되지 않았습니다.]"]
        return ["[상대 명식 — 엔진 확정값]", *self.partner_prefix_lines[1:]]

    def compatibility_block(self) -> list[str]:
        """궁합 신호 블록(RP-04·RP-05·RP-08 — 엔진 계산 사실)."""
        if self.compatibility is None:
            return ["[궁합 신호 없음 — 상대 명식이 없어 비교할 수 없습니다.]"]
        return compatibility_lines(self.compatibility)

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
                lines.append(
                    f"{y}년은 올해다 — {past}, {t.month}월은 이번 달, {future}다."
                )
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

    def month_overview_block(self) -> list[str]:
        """[12개월 흐름] — 이 해 12개월 전체를 빠짐없이(한해풀이 Y-05 전용, 반복 방지)."""
        overview = month_overview_lines(self.result, self.scored)
        if not overview:
            return []
        # 기반 최고 달을 이름 박아 지목 — 그 달에 두드러진 사건이 없어도 누락되지 않게(채팅과 동일).
        lc = self.result.luck_cycles
        best = [p.label for p in (lc.monthly_luck if lc else []) if p.luck_label == "강한 용신운"]
        callout = (
            f" 특히 {', '.join(best[:3])}은(는) '강한 용신운'이라 두드러진 사건이 없어도 "
            "기반이 가장 좋은 달이니 반드시 그렇게 짚을 것."
            if best else ""
        )
        return [
            "[12개월 흐름 — 이 해 12개월 전체. 한두 강신호만 반복하지 말고 각 달을 한두 문장으로 "
            "고르게 짚을 것. ★주목 표시된 달은 더 자세히. 좋은 달과 주의할 달의 1차 기준은 사건 "
            "밀도가 아니라 각 달의 운 품질 등급〈…〉('강한 용신운'>'용신운(부분)'>'혼합'>"
            "'기신운')이며, 사건(이직·이사 등)은 그 위에 십성으로 얹어 '무슨 일'을 설명한다. "
            "'강한 용신운' 달은 "
            "두드러진 사건이 없어도 기반이 가장 좋은(가장 도움되는) 달로 짚고, 각 달 기운의 "
            "활용·대비 방향도 곁들일 것." + callout + "]",
            *overview,
        ]

    # ── 구조 해석 블록(누출 안전) — 포맷은 structural_context 단일 소스에 위임. ──
    def wealth_capacity_block(self) -> list[str]:
        """[원국 횡재 그릇] — structural_context.wealth_capacity_lines 위임(재물 섹션 전용)."""
        return wealth_capacity_lines(self.wealth_capacity)

    def marriage_resource_block(self) -> list[str]:
        """[결혼·자산 자원 구조] — structural_context 위임(성별 인지·중립)."""
        return marriage_resource_lines(self.marriage_resource)

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
            "profiles": [], "directions": {}, "monthly": {}, "conflicts": [],
        }
        try:
            from saju_engines.precompute import CompositeBuilder
            from saju_engines.relocation import RelocationResolver
            from saju_shared_types.precompute import CompositeLevel
            from saju_shared_types.relocation import RelocationPeriod, RelocationQuery

            comps = CompositeBuilder(_DICTS).build(
                self.result, "report", "1.0.0",
                f"{self.today.isoformat()}T00:00:00+00:00",
                levels={CompositeLevel.YEAR, CompositeLevel.MONTH},
            )
            anchor = spec.period.start[:4]
            subject = spec.subjects[0]
            yongsin = (
                self.summary.useful_gods.yongsin[0]
                if self.summary.useful_gods.yongsin else "土"
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
            return ["[이사 이유·집 성격 — 이번 기간 뚜렷한 이동 십성 신호가 약함. "
                    "일반적 이동·정착 성향으로 서술하고 단정하지 말 것]"]
        lines = ["[이사의 이유·집 성격 — 십성 분류. 천간=명분(이유)/지지=현장(집·지역). "
                 "아래 라벨을 일상어로 풀어 서술하고 단정 표현은 금지]"]
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
            return ["[리스크·체크리스트 — 일반 이사 점검(등기부·계약 조건·실거주·하자 확인)으로 "
                    "안내하고 공포를 조장하지 말 것]"]
        lines = ["[리스크·계약 전 체크리스트 — 십성별. 겁주지 말고 "
                 "'확인하면 안심되는' 점검 항목으로 안내]"]
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
            p for p in self._relocation_ctx(spec)["profiles"]
            if p.source.startswith(("세운", "대운"))
        ]
        if not profiles:
            return []
        lines = ["[올해 이사·이동의 성격 — 세운 천간(올해 대표)·대운 천간(장기 배경) 십성. "
                 "이사를 한다면 이런 결이라는 유형 분류일 뿐, 실제 이사 여부 단정은 금지]"]
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

    def luck_block(self, candidates: list[EventCandidate] | None = None) -> list[str]:
        """[대운표]+[이벤트 후보] — 운 관련 섹션의 데이터 블록.

        candidates를 주면 그 후보만(섹션별 도메인 스코프), 없으면 전역 top 후보를 쓴다.
        """
        cands = self.candidates if candidates is None else candidates
        lines = ["[대운표]"]
        lc = self.result.luck_cycles
        if lc is not None:
            for d in lc.daewoon_table:
                lines.append(
                    f"대운 {d.ganji} ({d.approx_start_date.year}-{d.approx_end_date.year}, "
                    f"{d.start_age}-{d.start_age + 9}세)"
                )
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


# 주제 코드 → 한글 라벨(프레이밍 표기용). frontend themeLabel과 의미 정합.
_TOPIC_KO: dict[str, str] = {
    "career": "직업·사업운", "wealth": "재물운", "relationship": "애정·관계운",
    "health": "건강운", "education": "학업·시험운", "relocation": "이사·이동운",
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


def build_section_context(
    plan: SectionPlan, spec: ReportSpec, data: _ReportData
) -> SectionContext:
    """섹션 1개의 실데이터 컨텍스트(docs/06 계약 + docs/10 검사 기준)."""
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
        "지면 절약: 문단은 빈 줄 하나로만 구분하고 연속 빈 줄을 넣지 말 것. 잔 소제목 남발과 "
        "한 문장씩 끊은 단락을 피하고, 여러 문장을 묶은 조밀한 산문 문단으로 작성할 것.",
    ]
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
        if sid in _MONTH_OVERVIEW_SECTIONS:
            # 월별 흐름 — 12개월 전체 표 + (주목할 달 상세용) 전역 후보 블록.
            lines += data.month_overview_block()
            lines.append("")
            lines += data.luck_block()
        elif sid in _SECTION_DOMAIN:
            # 도메인 섹션 — 자기 도메인 후보만(길·흉 포함) 사용해 반복·편향 차단.
            lines += data.luck_block(data.domain_candidates(_SECTION_DOMAIN[sid]))
        else:
            lines += data.luck_block()
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
    if sid in _MARRIAGE_RESOURCE_SECTIONS:
        lines += ["", *data.marriage_resource_block()]
    # 건강 섹션 — 원국 취약 구조(의료 면책 동반). C-02/C-06은 health 주제일 때만.
    if sid in _HEALTH_VULN_SECTIONS or (
        sid in _HEALTH_TOPIC_SECTIONS and spec.topic == "health"
    ):
        lines += ["", *data.health_vulnerability_block()]
    # 부/귀 지향 — 명식 구조·직업 섹션.
    if sid in _WEALTH_STATUS_SECTIONS:
        lines += ["", *data.wealth_status_block()]
    # 이사 테마 — 십성 이유분류(이유·집성격 / 리스크·체크리스트) surface(이사 고도화 R2).
    if sid in _RELOCATION_REASON_SECTIONS:
        lines += ["", *data.relocation_reason_block(spec)]
    if sid in _RELOCATION_RISK_SECTIONS:
        lines += ["", *data.relocation_risk_block(spec)]
    # 이사 테마 — M10 방위 적합(RL-04) / 월별 이동운 흐름·충돌(RL-06) surface.
    if sid in _RELOCATION_DIRECTION_SECTIONS:
        lines += ["", *data.relocation_direction_block(spec)]
    if sid in _RELOCATION_FLOW_SECTIONS:
        lines += ["", *data.relocation_flow_block(spec)]
    # 연간 총운(Y-04) — 세운·대운 천간 십성 이사 유형 간결 surface(인생 총운엔 미부착).
    if sid in _RELOCATION_YEAR_SECTIONS:
        lines += ["", *data.relocation_year_block(spec)]
    # 시대 기운(연운) — 개인 풀이 앞 맥락. Y-01(한해풀이 그 해)·F-11(총운 올해).
    if sid == "Y-01":
        lines += ["", *data.era_energy_block(int(spec.period.start[:4]))]
    elif sid == "F-11":
        lines += ["", *data.era_energy_block(data.today.year)]
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
    birth: BirthInput, spec: ReportSpec, today: date | None = None,
    *, partner_birth: BirthInput | None = None,
) -> list[SectionContext]:
    """dry-run — 전 섹션의 실데이터 컨텍스트만 생성(LLM 미호출, 검증·개발용)."""
    data = _ReportData(birth, spec, today or date.today(), partner_birth=partner_birth)
    return [build_section_context(p, spec, data) for p in build_section_plans(spec)]


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
        birth, spec, today or date.today(), owner_id=owner_id, subject_id=subject_id,
        partner_birth=partner_birth,
    )
    call_type = (
        "report_full_section" if spec.product_code == "RPT_FULL" else "report_focus_section"
    )
    persona_block = None
    try:
        from saju_engines.persona import PersonaEngine

        persona_block = PersonaEngine(_DICTS).build_block(spec.persona, display_name)
    except ValueError:
        persona_block = None

    def generate_fn(plan: SectionPlan, context: SectionContext, attempt: int):
        # 보고서 전용 시스템 프롬프트(대화와 분리 — '정보 없음' 회피 문구 미포함).
        system = llm_client._REPORT_SYSTEM_PROMPT
        if persona_block:
            system = system + "\n\n" + persona_block
        prompt = context.body_prompt
        if attempt > 0:
            prompt += (
                f"\n\n[재생성 {attempt}회차] 직전 응답이 정합성 검사에 실패했다 — "
                "분량·간지·점수 규칙을 다시 확인하고, 내부 분류 용어(관계 발동/용기신 품질/"
                "복수 가능성 등)와 '근거 경로:' 표기를 본문에 노출하지 말 것(일상어로 풀어 서술)."
            )
        text = llm_client.generate_reading(
            prompt, call_type=call_type, system=system,
            product_code=f"{spec.product_code}:{plan.section_id}",
            owner_id=owner_id, surface="report", ref_id=subject_id,
        )
        text = _tighten(text)  # 지면 낭비 정규화(공백수정)
        return text, 0, len(text)  # 토큰은 llm_client 장부가 집계(cached 포함)

    builder = ReportBuilder(
        dictionaries_dir=_DICTS,
        context_builder=lambda plan, s: build_section_context(plan, s, data),
        generate_fn=generate_fn,
        progress_fn=progress_fn,
    )
    return builder.build(spec, display_name=display_name)
