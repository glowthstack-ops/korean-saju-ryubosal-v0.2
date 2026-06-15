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
from saju_engines.hap_lines import luck_hap_mode_lines
from saju_engines.manifestation_branch import branch_summary
from saju_engines.report_builder import ReportBuilder
from saju_engines.report_event_input import precise_candidate_clusters, score_table_lines
from saju_engines.report_plan import YONGSIN_SECTIONS, build_section_plans
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN as _EVENT_DOMAIN_V2
from saju_shared_types.events import EventCandidate
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


def _tighten(text: str) -> str:
    """LLM 출력의 지면 낭비 정규화 — 연속 빈 줄을 1개로, 줄 끝 공백 제거(공백수정 안전망).

    프롬프트 지시(지면 절약)를 LLM이 어겨도 렌더 페이지가 부풀지 않도록 후처리한다.
    마크다운 표·문단 구분에 필요한 빈 줄 1개는 보존한다.
    """
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
    "C-08": "근거 경로와 점수표를 그대로 정리해 부록으로 제시할 것.",
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
    "Y-05": "이 해 12개월 흐름을 월별로 짚되, 한 달에 1~2문장으로 조밀하게. 주목할 달을 강조할 것.",
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
    "Y-02",  # 한해풀이 — 원국+용신 기초(운 데이터 블록 미부착)
}
# 부록 점수표 섹션(실제 표 부착).
_SCORE_TABLE_SECTIONS = {"C-08", "W-09", "J-08", "R-08", "RP-10"}
# 궁합 모드 — 상대 명식 블록 부착 섹션(RP-03).
_PARTNER_NATAL_SECTIONS = {"RP-03"}
# 궁합 모드 — 궁합 신호 블록 부착 섹션(RP-04·RP-05·RP-08).
_COMPAT_SECTIONS = {"RP-04", "RP-05", "RP-08"}


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
        self.scored = scored  # 전체 점수화(필터 전) — 발현 분기(같은 계열 형제) 산출용.
        self.summary = build_birth_summary(self.result)
        self.prefix_lines = serialize_chart_prefix(
            self.summary, build_chart_interpretation(self.result),
        )
        self.evidence_paths = [
            " → ".join(self.scorer.readable_path(c)) for c in self.candidates[:3]
            if self.scorer.readable_path(c)
        ]
        self.allowed_ganji = self._collect_ganji()
        self.allowed_years = self._collect_years(spec)
        self.allowed_scores = sorted({c.score for c in self.candidates})

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

    def _branch_lines(self) -> list[str]:
        """후보 기간별 발현 분기 — 같은 계열·같은 시점에 점수화된 형제 사건(강도순).

        후보(top) 사건의 같은 EVENT_CATEGORY 계열 형제를 전체 점수화(self.scored)에서
        같은 시점으로 스코프해 도출한다(같은 시점 점수화된 형제만 — 추측 배제).
        """
        out: list[str] = []
        by_period: dict[str, list[Any]] = {}
        for c in self.candidates:
            by_period.setdefault(c.period, []).append(c)
        for period in sorted(by_period):
            siblings = [s for s in self.scored if s.period == period]
            focal_keys = [c.event_key for c in by_period[period]]
            line = branch_summary(focal_keys, siblings)
            if line:
                out.append(f"{period}: {line}")
        return out

    def luck_hap_lines(self) -> list[str]:
        """후보 기간 운(세운·월운·대운) 천간이 원국과 맺는 천간합의 작용 모드 줄.

        원국 합은 prefix(serialize_chart_prefix)에 이미 있으므로, 여기서는 운 관여 합만.
        """
        lc = self.result.luck_cycles
        if lc is None:
            return []
        by_label = {p.label: p.ganji for p in [*lc.yearly_luck, *lc.monthly_luck]}
        cand_years = {int(c.period[:4]) for c in self.candidates if c.period[:4].isdigit()}
        stems: set[str] = set()
        branches: set[str] = set()
        for c in self.candidates:
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

    def luck_block(self) -> list[str]:
        """[대운표]+[이벤트 후보 Top] — 운 관련 섹션의 데이터 블록."""
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
        lines += precise_candidate_clusters(self.result, self.candidates)
        hap_lines = self.luck_hap_lines()
        if hap_lines:
            lines.append("")
            lines.append(
                "[합 작용(운) — 후보 기간 운 천간이 원국과 맺는 천간합의 모드·신뢰도(엔진 판정). "
                "단정 말고 신뢰도(확정/조건부/불성)대로, 합거된 십성은 그 시기 기능 "
                "약화/전환으로 서술]"
            )
            lines += hap_lines
        branch_lines = self._branch_lines()
        if branch_lines:
            lines.append("")
            lines.append(
                "[발현 분기 — 같은 계열(이동·재물·학업 등)에서 같은 에너지가 갈릴 수 있는 형제 "
                "사건. 둘 다 나열만 하지 말고, 사용자의 상황(직업 유무 등)·맥락에서 성립 불가능한 "
                "형제는 배제해 가능한 쪽으로 좁혀 해석할 것 — 예: 직장이 없으면 '이직'은 성립하지 "
                "않아 같은 이동 에너지는 '이사'다.]"
            )
            lines += branch_lines
        if self.evidence_paths:
            lines.append("")
            lines.append("[근거 경로 — 최소 1개를 본문에 그대로 인용할 것]")
            lines += self.evidence_paths
        return lines


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
        lines += data.luck_block()
    elif data.evidence_paths:
        # 명식 섹션도 근거 인용 의무(docs/10 — 섹션당 evidence path ≥1).
        lines += ["", "[근거 경로 — 최소 1개를 본문에 그대로 인용할 것]", *data.evidence_paths]
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
                "분량·간지·점수·근거 인용 규칙을 다시 확인해 작성할 것."
            )
            # C-2: 근거 경로 미인용이 잦아 재생성 시 원문 그대로 인용을 강제한다.
            if context.evidence_paths:
                quoted = " / ".join(context.evidence_paths)
                prompt += (
                    "\n[필수] 다음 근거 경로 중 최소 하나를 본문 문장 속에 글자 그대로"
                    "(화살표 '→' 포함, 요약·수정·띄어쓰기 변경 없이) 한 번 인용하라: "
                    f"{quoted}"
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
