"""보고서 정합성 검사 (v2.2 Phase 9, docs/10 7장 — 결정적 검사 8종 전체).

LLM 출력 후 **코드로** 검증한다. 실패 시 해당 섹션만 재생성(최대 2회), 2회 실패 시
작업 보류 + 관리자 알림. LLM에게 자기 검증을 맡기지 않는다(절대 원칙 1).
"""

from __future__ import annotations

import re
from pathlib import Path

from saju_shared_types.profile import PersonaConfig
from saju_shared_types.report import SectionContext, SectionPlan

from .llm_event_serializer import INTERNAL_JARGON_LABELS
from .persona import PersonaEngine

# 본문 간지 추출(천간+지지 2자) — 검사 2.
_GANJI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
# 점수(NN점)·연도(YYYY년) 추출 — 검사 3.
_SCORE_RE = re.compile(r"(\d{2,3})\s*점")
_YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*년")
# 용신 표기 — 검사 4.
_YONGSIN_RE = re.compile(r"용신[은는이가의]?\s*([木火土金水])")
# 금지 표현(검사 5 — 절대 원칙 3·8, prohibited_styles 초안).
_PROHIBITED_PATTERNS = [
    r"반드시\s*\S{0,6}(한다|된다|입니다)",
    r"틀림없이", r"무조건\s*\S{0,6}(된다|한다)", r"100\s*%",
    r"당첨된다", r"당첨될", r"합격한다", r"당선된다", r"떨어진다",
    r"이혼하게\s*된다", r"죽는다", r"확실히\s*\S{0,6}(된다|한다)",
]


class ReportChecker:
    """섹션 텍스트 정합성 검사기 — 페르소나 검사(6)는 persona 엔진 재사용."""

    def __init__(self, dictionaries_dir: Path) -> None:
        self._persona = PersonaEngine(dictionaries_dir)

    def check_section(
        self,
        plan: SectionPlan,
        context: SectionContext,
        text: str,
        persona: PersonaConfig,
        display_name: str = "회원",
    ) -> list[str]:
        """검사 1~8 전체 — 위반 사유 목록(빈 목록 = 통과)."""
        violations: list[str] = []

        # 1. 분량 — targetChars 범위.
        n = len(text)
        if not (plan.target_chars.min <= n <= plan.target_chars.max):
            violations.append(
                f"분량 위반: {n}자 (목표 {plan.target_chars.min}~{plan.target_chars.max})"
            )

        # 2. 간지 표기 — 미제공 간지 등장 = 즉시 실패.
        allowed = set(context.allowed_ganji)
        for ganji in set(_GANJI_RE.findall(text)):
            if ganji not in allowed:
                violations.append(f"미제공 간지 등장: {ganji}")

        # 3. 수치 일치 — 점수·연도 정규식 추출 대조.
        for m in _SCORE_RE.finditer(text):
            score = int(m.group(1))
            if score <= 100 and context.allowed_scores and score not in context.allowed_scores:
                violations.append(f"입력에 없는 점수: {score}점")
        for m in _YEAR_RE.finditer(text):
            year = int(m.group(1))
            if context.allowed_years and year not in context.allowed_years:
                violations.append(f"입력에 없는 연도: {year}년")

        # 4. 용신 일관 — F-04 확정 용신과 이후 섹션 표기 일치.
        if context.yongsin_element:
            for m in _YONGSIN_RE.finditer(text):
                if m.group(1) != context.yongsin_element:
                    violations.append(
                        f"용신 불일치: 본문 {m.group(1)} ≠ 확정 {context.yongsin_element}"
                    )

        # 5. 금지 표현 — prohibited_styles.
        for pattern in _PROHIBITED_PATTERNS:
            if re.search(pattern, text):
                violations.append(f"금지 표현: /{pattern}/")

        # 6. 페르소나 준수 — docs/11 5-4 4종 검사 재사용.
        persona_report = self._persona.check_compliance(text, persona, display_name)
        violations += [f"페르소나: {v}" for v in persona_report.violations]

        # 7. 대상 표기 — 다중 subject 보고서는 섹션별 대상 라벨 명시.
        if context.multi_subject and context.subject_label not in text[:200]:
            violations.append(f"섹션 서두 대상 라벨 누락: {context.subject_label}")

        # 8. 내부용어 노출 — 근거 경로/스코어링 분류 라벨을 본문에 그대로 쓰면 순화 위반(soft).
        # 근거 경로는 '내부 근거'로만 활용하고 사용자 본문엔 일상어로 풀어 녹여야 한다(2026-06-16).
        # 사실 위반이 아니므로 재생성을 유발하지 않고 기록만 한다(_HARD_VIOLATION_PREFIXES 제외).
        leaked = [label for label in INTERNAL_JARGON_LABELS if label in text]
        if "근거 경로" in text:
            leaked.append("근거 경로")
        if leaked:
            violations.append("내부용어 노출(순화 필요): " + ", ".join(leaked))

        return violations
