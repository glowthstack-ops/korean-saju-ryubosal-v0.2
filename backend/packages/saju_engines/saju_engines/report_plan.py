"""보고서 고정 목차 (v2.2 Phase 9, docs/10 3·4장 — 전체 규격).

RPT_FULL(22)·RPT_FOCUS generic(8)은 섹션 임의 추가·삭제·병합·순서변경 금지. dependsOn 규칙:
F-04(용신 확정)가 F-10~F-20 전체의 선행, F-21은 F-13~F-20 완료 후. F-08/F-09(과거 검증)를
미래(4부)보다 앞에 두는 것은 신뢰 형성 원칙(docs/01)에 따른 고정 순서.

테마 전용 목차(_THEME_TOCS): 주제별 스토리 구조가 다르다는 사용자 확정(2026-06-14)에 따라
generic FOCUS 대신 주제 전용 목차를 쓴다. 현재 재물운(wealth=W-01~W-09)만 정의. 각 테마 목차
자체는 고정 규격이며 임의 변형 금지(generic 규격의 주제 확장이지 폐기가 아님).
"""

from __future__ import annotations

from saju_shared_types.intent import SubjectKind
from saju_shared_types.report import ModuleCall, ReportSpec, SectionPlan, TargetChars

# RPT_FULL — 22섹션(docs/10 3장 표 그대로): (id, 제목, 모듈, min, max).
_FULL_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("F-01", "사주 원국 개요", ["T0"], 2_500, 3_500),
    ("F-02", "일간과 타고난 기질", ["T0", "M03"], 3_000, 4_000),
    ("F-03", "십성 구조와 사회적 성향", ["T0", "M03"], 3_500, 4_500),
    ("F-04", "신강약·격국·용신", ["T0"], 3_000, 4_000),
    ("F-05", "신살·공망·특수 구조", ["T0"], 2_500, 3_500),
    ("F-06", "성격/취향 종합과 행동 패턴", ["M03", "E5"], 3_000, 4_000),
    ("F-07", "대운 흐름 개관", ["T1", "M03"], 4_000, 5_000),
    ("F-08", "과거 주요 이벤트 복원", ["M14"], 4_500, 5_500),
    ("F-09", "과거 검증 확인 포인트", ["M14"], 1_500, 2_500),
    ("F-10", "현재 대운 정밀 분석", ["T1"], 3_500, 4_500),
    ("F-11", "올해 세운과 활성 신호", ["T1", "M15"], 3_000, 4_000),
    ("F-12", "현 시점 성향 시프트", ["M03"], 2_000, 3_000),
    ("F-13", "향후 대운 로드맵", ["T1", "M03"], 4_500, 5_500),
    ("F-14", "고점 이벤트 연도 Top", ["M07", "M01", "M09"], 4_500, 5_500),
    ("F-15", "직업·사업 전망", ["M07", "M08"], 4_000, 5_000),
    ("F-16", "재물 전망", ["M09"], 3_500, 4_500),
    ("F-17", "관계·가정 전망", ["M01", "M02", "M04", "M05"], 4_000, 5_000),
    ("F-18", "건강 전망과 주의 시기", ["M11"], 3_000, 4_000),
    ("F-19", "도메인별 행동 전략", ["E8"], 3_500, 4_500),
    ("F-20", "개운·보완 가이드", ["E8"], 2_500, 3_500),
    ("F-21", "핵심 요약 카드", [], 1_500, 2_000),
    ("F-22", "간지 달력표 + 용어 해설", ["T1"], 2_000, 3_000),
]

# RPT_FOCUS — 8섹션(docs/10 4장 표 그대로).
_FOCUS_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("C-01", "주제 요약", ["MODULE"], 1_500, 2_000),
    ("C-02", "명식 속 주제 구조", ["T0"], 3_000, 4_000),
    ("C-03", "기간 운 흐름", ["T1", "MODULE"], 3_500, 4_500),
    ("C-04", "이벤트 후보와 타임라인", ["MODULE", "E4"], 3_500, 4_500),
    ("C-05", "현실화 전망과 발현 형태", ["E3", "E6"], 2_500, 3_500),
    ("C-06", "주의 시기·리스크", ["RISK", "E8"], 2_000, 3_000),
    ("C-07", "행동 전략", ["E8"], 2_500, 3_500),
    ("C-08", "부록: 근거 경로와 점수표", ["EVIDENCE"], 1_500, 2_500),
]

# 테마 전용 목차(2026-06-14 사용자 확정) — 주제마다 다른 스토리 구조를 갖는다.
# 재물운: 성향→재물구조→축재형태→횡재→5년종합→주목할 달→행동전략→점수표. 그 외 주제는 generic FOCUS.
_WEALTH_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("W-01", "핵심 요약", ["MODULE"], 1_200, 1_800),
    ("W-02", "나의 재물 성향", ["T0", "M03"], 2_500, 3_500),
    ("W-03", "사주의 재물 구조", ["T0", "M09"], 3_000, 4_000),
    ("W-04", "운에서 드러난 축재 형태", ["M09", "E3"], 2_500, 3_500),
    ("W-05", "횡재·상속 가능성", ["M09", "E6"], 2_000, 3_000),
    ("W-06", "향후 5년 재물 종합 운세", ["T1", "M09"], 3_500, 4_500),
    ("W-07", "주목할 달 세부 정리", ["T1", "E4"], 3_000, 4_000),
    ("W-08", "재물 행동 전략", ["E8"], 2_000, 3_000),
    ("W-09", "부록: 점수표와 근거", ["EVIDENCE"], 1_500, 2_500),
]
# 직업·사업운(career): 성향→직업구조→직업변동형태→5년종합→주목할 달→행동전략→점수표.
_CAREER_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("J-01", "핵심 요약", ["MODULE"], 1_200, 1_800),
    ("J-02", "나의 직업 성향", ["T0", "M03"], 2_500, 3_500),
    ("J-03", "사주의 직업 구조", ["T0", "M07"], 3_000, 4_000),
    ("J-04", "운에서 드러난 직업 변동", ["M07", "E3"], 2_500, 3_500),
    ("J-05", "향후 5년 직업 종합 운세", ["T1", "M07"], 3_500, 4_500),
    ("J-06", "주목할 달 세부 정리", ["T1", "E4"], 3_000, 4_000),
    ("J-07", "직업 행동 전략", ["E8"], 2_000, 3_000),
    ("J-08", "부록: 점수표와 근거", ["EVIDENCE"], 1_500, 2_500),
]
# 관계·애정운(relationship) 단독 모드 베이스: 성향→배우자·인연구조→인연변화→5년종합→주목할 달→
# 행동전략→점수표. 상대(궁합) 모드 섹션은 별도 설계·확인 후 확장(상대 명식 계산·궁합 신호 필요).
_RELATIONSHIP_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("R-01", "핵심 요약", ["MODULE"], 1_200, 1_800),
    ("R-02", "나의 애정 성향", ["T0", "M03"], 2_500, 3_500),
    ("R-03", "배우자·인연 구조", ["T0", "M01"], 3_000, 4_000),
    ("R-04", "운에서 드러난 인연 변화", ["M01", "E3"], 2_500, 3_500),
    ("R-05", "향후 5년 애정 종합 운세", ["T1", "M01"], 3_500, 4_500),
    ("R-06", "주목할 달 세부 정리", ["T1", "E4"], 3_000, 4_000),
    ("R-07", "관계 행동 전략", ["E8"], 2_000, 3_000),
    ("R-08", "부록: 점수표와 근거", ["EVIDENCE"], 1_500, 2_500),
]
# 관계·애정운 궁합(상대 선택) 모드: 상대 명식이 등록되면 단독 8섹션 대신 궁합 전용 10섹션을 쓴다
# (2026-06-14 사용자 확정). 상대 해석(RP-03)·궁합 구조(RP-04·RP-05)·극복(RP-08)이 독립 섹션.
_RELATIONSHIP_PAIR_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("RP-01", "두 사람 관계 한눈에", ["MODULE", "M13"], 1_200, 1_800),
    ("RP-02", "나의 애정 성향", ["T0", "M03"], 2_000, 3_000),
    ("RP-03", "상대는 어떤 사람인가", ["T0", "M03"], 2_500, 3_500),
    ("RP-04", "두 사람의 궁합 구조", ["M13"], 3_000, 4_000),
    ("RP-05", "관계의 강점과 마찰점", ["M13"], 2_500, 3_500),
    ("RP-06", "운에서 함께 겪을 흐름", ["T1", "M01"], 3_000, 4_000),
    ("RP-07", "주목할 달 세부 정리", ["T1", "E4"], 2_500, 3_500),
    ("RP-08", "관계가 어려울 때 — 극복 마음가짐·행동", ["M13", "E8"], 2_500, 3_500),
    ("RP-09", "관계 운영 전략", ["E8"], 2_000, 3_000),
    ("RP-10", "부록: 점수표와 근거", ["EVIDENCE"], 1_500, 2_500),
]
# 이사·이동운(relocation): 성향→이유·집성격(십성)→이동 신호→리스크·체크리스트→
# 향후 흐름→행동전략→점수표. 이유·집성격(RL-03)·리스크(RL-05)는 relocation_ten_gods
# 십성 분류를 surface한다(이사 고도화 R2 — RELOCATION_ENHANCEMENT.md).
_RELOCATION_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("RL-01", "핵심 요약", ["MODULE"], 1_200, 1_800),
    ("RL-02", "나의 이동·정착 성향", ["T0", "M03"], 2_500, 3_500),
    ("RL-03", "이사의 이유와 집의 성격", ["T0", "M10"], 3_000, 4_000),
    ("RL-04", "운에서 드러난 이동 신호", ["M10", "E3"], 2_500, 3_500),
    ("RL-05", "리스크와 계약 전 체크리스트", ["M10"], 2_500, 3_500),
    ("RL-06", "향후 5년 이동 흐름과 주목할 달", ["T1", "E4"], 3_500, 4_500),
    ("RL-07", "이사 행동 전략", ["E8"], 2_000, 3_000),
    ("RL-08", "부록: 점수표와 근거", ["EVIDENCE"], 1_500, 2_500),
]
_THEME_TOCS: dict[str, list[tuple[str, str, list[str], int, int]]] = {
    "wealth": _WEALTH_TOC,
    "career": _CAREER_TOC,
    "relationship": _RELATIONSHIP_TOC,
    "relocation": _RELOCATION_TOC,
}

# RPT_YEAR 한해풀이(2026-06-14 사용자 확정) — 총운(RPT_FULL)에서 단일 년도에 의미 있는
# 항목만 발췌·중복 제거한 12섹션. 장기 항목(생애 대운 로드맵·과거 복원·고점 연도 Top·
# 성격 종합)은 제외하고, 원국+용신은 1섹션(Y-02)으로 압축한다. 세운 기준은 달력연도
# 1~12월(spec.period가 그 해로 스코프). 분량을 조여 공백 정상화 시 A4 약 14~18장
# (본문 21,600~28,400자, 1p≈1,600자). 목차 자체는 고정 규격 — 임의 변형 금지.
_YEAR_TOC: list[tuple[str, str, list[str], int, int]] = [
    ("Y-01", "올해 한눈에", [], 1_000, 1_400),
    ("Y-02", "내 사주와 용신 기초", ["T0"], 1_800, 2_400),
    ("Y-03", "올해가 속한 대운 맥락", ["T1"], 1_800, 2_400),
    ("Y-04", "세운과 활성 신호", ["T1", "M15"], 2_400, 3_000),
    ("Y-05", "월별 흐름과 주목할 달", ["M07", "M01", "M09", "E4"], 3_000, 3_800),
    ("Y-06", "직업·사업 흐름", ["M07", "M08"], 1_800, 2_400),
    ("Y-07", "재물 흐름", ["M09"], 1_800, 2_400),
    ("Y-08", "관계·가정 흐름", ["M01", "M02", "M04", "M05"], 1_800, 2_400),
    ("Y-09", "건강·주의 시기", ["M11"], 1_500, 2_000),
    ("Y-10", "올해의 행동 전략", ["E8"], 1_800, 2_400),
    ("Y-11", "개운·보완 가이드", ["E8"], 1_400, 1_800),
    ("Y-12", "간지 달력표(12개월)와 용어", ["T1"], 1_500, 2_000),
]

# 용신을 확정해 이후 섹션 검사 기준으로 전파하는 섹션(상품별). RPT_FULL=F-04, RPT_YEAR=Y-02.
YONGSIN_SECTIONS = {"F-04", "Y-02"}


def is_pair_relationship(spec: ReportSpec) -> bool:
    """관계운 + 상대(SELF 아닌 subject) 등록 → 궁합 모드(RP-01~RP-10)."""
    if spec.topic != "relationship":
        return False
    return any(s.kind != SubjectKind.SELF for s in spec.subjects)

# 주제별 변형(4장) — 제목·모듈만 교체, 섹션 추가/삭제 금지.
_FOCUS_VARIANTS: dict[str, dict[str, tuple[str, list[str]]]] = {
    "compatibility": {
        "C-02": ("두 명식의 구조 대조", ["M13"]),
        "C-04": ("관계 이벤트 타임라인", ["M13", "E4"]),
        "C-05": ("관계 운영 시나리오", ["M13"]),
    },
    # relocation은 전용 테마 목차(_RELOCATION_TOC)로 승격 — generic FOCUS 변형 미사용.
}

# FOCUS 주제 → 대표 모듈(planner._DOMAIN_MODULE과 정합). _FOCUS_TOC의 'MODULE'
# 플레이스홀더를 주제 모듈로 해석한다(섹션 추가/삭제 없음 — 모듈만 주제화). docs/02·10.
_TOPIC_MODULE: dict[str, str] = {
    "career": "M07",
    "wealth": "M09",
    "relationship": "M01",
    "relocation": "M10",
    "health": "M11",
    "education": "M12",
    "compatibility": "M13",
}

# RPT_FULL dependsOn 규칙(3장).
_F04_DEPENDENTS = [f"F-{n:02d}" for n in range(10, 21)]  # F-10~F-20
_F21_DEPS = [f"F-{n:02d}" for n in range(13, 21)]  # F-13~F-20
# RPT_YEAR dependsOn — Y-02(용신 확정)가 Y-03~Y-11 전체의 선행(검사 4 용신 일관).
_Y02_DEPENDENTS = [f"Y-{n:02d}" for n in range(3, 12)]  # Y-03~Y-11


def calibrate_chars(lo: int, hi: int) -> tuple[int, int]:
    """편집 의도 목표분량(목차표 값)을 LLM 실측 분량 밴드로 압축한다(분량 검사 기준, 전 상품 공통).

    실측(2026-06-14, gemini-3-flash): 섹션 출력은 목표 크기와 무관하게 ~1,550~1,950자에 수렴한다
    (예: 목표 4,500~5,500자인 F-08·F-14 → 1,953·1,718자). 목표를 일괄 길게 유지하면 분량 검사
    (무허용오차)가 항상 실패하므로(2026-06-14 사용자 확정 'B'), 목표를 실측 밴드로 하향한다.
    의도 분량의 상대 강조는 약하게만 반영(짧은 요약 vs 표준/긴 섹션 2단)하고, 하한은 안전하게
    낮춰 통과시키고 상한은 출력 변동을 흡수한다.
    """
    mid = (lo + hi) / 2
    if mid < 2_200:  # 요약·확인·부록 등 짧은 섹션
        return 700, 2_200
    return 900, 2_900  # 표준·타임라인·복원 등


FULL_TOTAL_TARGET = 41_000  # 캘리브레이션 후 합계 목표 ±10%(A4 약 25장)
YEAR_TOTAL_TARGET = 18_000  # 한해풀이 합계 목표 ±10%(A4 약 11~14장)


def _tc(lo: int, hi: int) -> TargetChars:
    """목차표 의도 분량 → 캘리브레이션된 검사 기준 TargetChars."""
    cmin, cmax = calibrate_chars(lo, hi)
    return TargetChars(min=cmin, max=cmax)
MAX_PARALLEL_SECTIONS = 4  # 의존성 없는 섹션 병렬 상한(2장)
MAX_REGENERATIONS = 1  # 사실 위반 시에만 재생성(비용 절감, 2026-06-14: 2→1)


def build_section_plans(spec: ReportSpec) -> list[SectionPlan]:
    """상품·주제에 따른 고정 목차 → SectionPlan 목록(규격 순서 그대로)."""
    if spec.product_code == "RPT_FULL":
        plans = []
        for sid, title, modules, lo, hi in _FULL_TOC:
            depends: list[str] = []
            if sid in _F04_DEPENDENTS:
                depends = ["F-04"]
            elif sid == "F-21":
                depends = list(_F21_DEPS)
            plans.append(SectionPlan(
                section_id=sid, title=title,
                module_calls=[ModuleCall(module_id=m) for m in modules],
                target_chars=_tc(lo, hi),
                depends_on=depends,
            ))
        return plans

    if spec.product_code == "RPT_YEAR":
        plans = []
        for sid, title, modules, lo, hi in _YEAR_TOC:
            depends = ["Y-02"] if sid in _Y02_DEPENDENTS else []
            plans.append(SectionPlan(
                section_id=sid, title=title,
                module_calls=[ModuleCall(module_id=m) for m in modules],
                target_chars=_tc(lo, hi),
                depends_on=depends,
            ))
        return plans

    variants = _FOCUS_VARIANTS.get(spec.topic or "", {})
    topic_module = _TOPIC_MODULE.get(spec.topic or "")
    # 관계운 + 상대 등록 → 궁합 전용 10섹션. 그 외엔 테마 전용 목차(있으면) / generic FOCUS.
    if is_pair_relationship(spec):
        toc = _RELATIONSHIP_PAIR_TOC
    else:
        toc = _THEME_TOCS.get(spec.topic or "", _FOCUS_TOC)
    plans = []
    for sid, title, modules, lo, hi in toc:
        if sid in variants:
            title, modules = variants[sid]
        # 'MODULE' 플레이스홀더 → 주제 모듈(없으면 원형 유지).
        resolved = [topic_module if m == "MODULE" and topic_module else m for m in modules]
        plans.append(SectionPlan(
            section_id=sid, title=title,
            module_calls=[ModuleCall(module_id=m) for m in resolved],
            target_chars=_tc(lo, hi),
        ))
    return plans
