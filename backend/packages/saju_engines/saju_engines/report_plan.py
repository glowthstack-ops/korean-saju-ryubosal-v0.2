"""보고서 고정 목차 (v2.2 Phase 9, docs/10 3·4장 — 전체 규격).

섹션 임의 추가·삭제·병합·순서변경 금지. dependsOn 규칙: F-04(용신 확정)가
F-10~F-20 전체의 선행, F-21은 F-13~F-20 완료 후. F-08/F-09(과거 검증)를 미래(4부)보다
앞에 두는 것은 신뢰 형성 원칙(docs/01)에 따른 고정 순서.
"""

from __future__ import annotations

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

# 주제별 변형(4장) — 제목·모듈만 교체, 섹션 추가/삭제 금지.
_FOCUS_VARIANTS: dict[str, dict[str, tuple[str, list[str]]]] = {
    "compatibility": {
        "C-02": ("두 명식의 구조 대조", ["M13"]),
        "C-04": ("관계 이벤트 타임라인", ["M13", "E4"]),
        "C-05": ("관계 운영 시나리오", ["M13"]),
    },
    "relocation": {
        "C-04": ("추천 시기·날짜 랭킹", ["M10"]),
    },
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

FULL_TOTAL_TARGET = 78_000  # 합계 목표 ±10%
MAX_PARALLEL_SECTIONS = 4  # 의존성 없는 섹션 병렬 상한(2장)
MAX_REGENERATIONS = 2  # 정합성 실패 재생성 한도(7장)


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
                target_chars=TargetChars(min=lo, max=hi),
                depends_on=depends,
            ))
        return plans

    variants = _FOCUS_VARIANTS.get(spec.topic or "", {})
    topic_module = _TOPIC_MODULE.get(spec.topic or "")
    plans = []
    for sid, title, modules, lo, hi in _FOCUS_TOC:
        if sid in variants:
            title, modules = variants[sid]
        # 'MODULE' 플레이스홀더 → 주제 모듈(없으면 원형 유지).
        resolved = [topic_module if m == "MODULE" and topic_module else m for m in modules]
        plans.append(SectionPlan(
            section_id=sid, title=title,
            module_calls=[ModuleCall(module_id=m) for m in resolved],
            target_chars=TargetChars(min=lo, max=hi),
        ))
    return plans
