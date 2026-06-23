"""페르소나 엔진 (v2.2 Phase 8.5 T8.5.5~T8.5.7, docs/11 5장).

- 조합 제약 검증(5-2): politeness↔honorific, jane→hagae, custom 금칙어·길이.
- 프롬프트 블록 조립(5-3): **고정 템플릿 슬롯 치환으로만** 생성(즉석 작문 금지 —
  절대 원칙 12). 페르소나는 문체 전용 — 점수·날짜·간지·판정 영향 금지.
- 준수 검사(5-4) 4종: 종결어미 화이트리스트 ≥93%(C-3) / 호칭 일치 / 존대 혼용 없음 /
  easy 미해설 전문용어 0건. 위반 시 해당 응답 재생성(호출 측).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from saju_shared_types.profile import PersonaConfig

# 5-3 고정 템플릿(규격 전문) — 수정 금지.
_PERSONA_TEMPLATE = (
    "[페르소나 — 필수 준수]\n"
    "당신은 {counselorAgeBand_label} {counselorGender_label} 사주 상담가다.\n"
    '호칭은 "{resolvedHonorific}"만 허용한다(다른 호칭 금지). 그러나 답변/섹션 전체에서 '
    "최대 2회까지만 호명한다 — 첫머리에 한 번이면 충분하다. 문장이나 문단을 호칭으로 시작하는 "
    "습관을 금지하고(거의 모든 문장을 호칭으로 여는 것 금지), 이후 문장은 호칭 없이 "
    "바로 서술한다.\n"
    "말투: {style_label}로만 말한다. 허용 종결어미: {endings_list}. "
    "이 목록 밖 종결어미 사용 금지.\n"
    "존대 수준: {politeness_label}. 혼용 금지.\n"
    "풀이 난이도: {difficulty_rule}\n"
    "1인칭·말버릇: {lexicon_phrases} 같은 말버릇의 결만 참고하되, 반드시 위 말투·종결어미로 "
    "바꿔 쓴다 — 예시가 해요체로 적혀 있어도 그대로 박지 말고 현재 말투로 변환할 것"
    "(예: 반말체면 '이 흐름 좋네요'→'이 흐름 좋네', '필요해요'→'필요해'). 다른 말투의 종결어미를 "
    "그대로 끼워 넣지 말 것(남용 금지, 응답당 2회 이하).\n"
    "금지: 페르소나를 이유로 점수·날짜·간지·판정을 바꾸는 것. "
    "사실 데이터는 입력 그대로 전달한다."
)

_GENDER_LABELS = {"female": "여성", "male": "남성", "neutral": "중성적인"}
_AGE_LABELS = {
    "20s": "20대", "30s": "30대", "40s": "40대", "50s": "50대", "60s_plus": "60대 이상",
}
_STYLE_LABELS = {
    "haeyo": "해요체", "hapsyo": "합쇼체", "hagae": "하게체", "banmal_chae": "반말체",
}
_POLITENESS_LABELS = {"jondae": "존댓말", "banmal": "반말"}

# 준수 검사용 스타일별 종결 접미 클래스 — 화이트리스트 원문(~예요 등)은 LLM 프롬프트용,
# 검사기는 한국어 활용을 포괄하는 접미로 판정한다(예: "있어요"도 해요체).
_STYLE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "haeyo": ("요",),
    "hapsyo": ("니다",),
    "hagae": ("네", "세", "게"),
    "banmal_chae": ("야", "어", "지", "봐", "아", "해", "거든", "래", "자"),
}

# easy 난이도에서 해설 없이 쓰면 위반인 전문용어(검사 4번 초안 목록).
_EXPERT_TERMS = [
    "십성", "지장간", "격국", "편관", "정관", "편인", "정인", "식신", "상관",
    "비견", "겁재", "편재", "정재", "용신", "기신", "희신", "공망", "삼합", "육합",
]


class PersonaValidation(BaseModel):
    """조합 제약 검증 결과."""

    valid: bool
    errors: list[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    """준수 검사(5-4) 결과 — 실패 시 해당 응답/섹션 재생성."""

    passed: bool
    ending_ratio: float = 1.0
    violations: list[str] = Field(default_factory=list)


class PersonaEngine:
    """persona_lexicon/honorific_presets 사전 기반(결정론)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        lex = json.loads((dictionaries_dir / "persona_lexicon.json").read_text("utf-8"))
        self._endings: dict[str, list[str]] = lex["endings"]
        self._difficulty_rules: dict[str, str] = lex["difficulty_rules"]
        self._lexicon: dict[str, dict] = lex["lexicon"]["byGenderAge"]
        hon = json.loads(
            (dictionaries_dir / "honorific_presets.json").read_text("utf-8")
        )
        self._presets: dict[str, dict] = {p["presetId"]: p for p in hon["presets"]}
        self._banned: list[str] = hon["bannedWords"]
        self._custom_max: int = hon["customMaxLength"]

    # ── T8.5.5 조합 제약 (5-2) ───────────────────────────────────

    def validate(self, config: PersonaConfig) -> PersonaValidation:
        """5-2 제약 전체 검증(speech 조합은 pydantic이 이미 강제)."""
        errors: list[str] = []
        h = config.user_honorific
        if h.type == "preset":
            preset = self._presets.get(h.preset_id or "")
            if preset is None:
                errors.append(f"알 수 없는 호칭 프리셋: {h.preset_id}")
            else:
                if config.speech.politeness not in preset["allowedPoliteness"]:
                    errors.append(
                        f"호칭 '{h.preset_id}'은(는) "
                        f"{config.speech.politeness}와 조합 불가"
                    )
                allowed_styles = preset.get("allowedStyles")
                if allowed_styles and config.speech.style not in allowed_styles:
                    errors.append(f"호칭 '{h.preset_id}'은(는) {allowed_styles} 전용")
        else:  # custom — 금칙어 + 길이 + politeness 모순.
            text = h.custom_text or ""
            if not text:
                errors.append("custom 호칭이 비어 있음")
            if len(text) > self._custom_max:
                errors.append(f"custom 호칭은 {self._custom_max}자 이하")
            for banned in self._banned:
                if banned in text:
                    errors.append("custom 호칭 금칙어 포함 — 사용 불가")
                    break
            if config.speech.politeness == "jondae" and text in ("너", "야"):
                errors.append("존댓말과 모순되는 custom 호칭")
        return PersonaValidation(valid=not errors, errors=errors)

    # ── T8.5.6 프롬프트 블록 조립 (5-3 — 템플릿 치환 전용) ────────

    def resolve_honorific(self, config: PersonaConfig, display_name: str) -> str:
        """호칭 문자열 확정."""
        h = config.user_honorific
        if h.type == "custom":
            return h.custom_text or display_name
        preset = self._presets[h.preset_id or "name_nim"]
        return str(preset["template"]).format(displayName=display_name)

    def build_block(self, config: PersonaConfig, display_name: str) -> str:
        """페르소나 프롬프트 블록 — 5-3 템플릿 슬롯 치환으로만 생성."""
        validation = self.validate(config)
        if not validation.valid:
            raise ValueError(f"페르소나 조합 무효: {validation.errors}")
        lexicon_key = f"{config.counselor_gender}_{config.counselor_age_band}"
        phrases = self._lexicon.get(lexicon_key, {}).get("phrases", [])
        return _PERSONA_TEMPLATE.format(
            counselorAgeBand_label=_AGE_LABELS[config.counselor_age_band],
            counselorGender_label=_GENDER_LABELS[config.counselor_gender],
            resolvedHonorific=self.resolve_honorific(config, display_name),
            style_label=_STYLE_LABELS[config.speech.style],
            endings_list=", ".join(self._endings[config.speech.style]),
            politeness_label=_POLITENESS_LABELS[config.speech.politeness],
            difficulty_rule=self._difficulty_rules[config.difficulty],
            lexicon_phrases=", ".join(f'"{p}"' for p in phrases),
        )

    # ── T8.5.7 준수 검사 (5-4 — 4종) ─────────────────────────────

    def check_compliance(
        self, text: str, config: PersonaConfig, display_name: str
    ) -> ComplianceReport:
        """응답 텍스트의 페르소나 준수 검사 — 대화/보고서 공통."""
        violations: list[str] = []

        # ① 종결어미 화이트리스트 비율 ≥93% — 스타일 접미 클래스로 판정(C-3, 2026-06-14:
        # 표·짧은 섹션의 비서술 문장 변동을 흡수하기 위해 95→93% 하향. 보고서 전용 게이트).
        sentences = [s.strip() for s in re.split(r"[.!?…\n]+", text) if s.strip()]
        own = _STYLE_SUFFIXES[config.speech.style]
        matched = sum(1 for s in sentences if s.endswith(own))
        ratio = matched / len(sentences) if sentences else 1.0
        if ratio < 0.93:
            violations.append(f"종결어미 화이트리스트 비율 {ratio:.0%} < 93%")

        # ② resolvedHonorific 외 호칭 미사용.
        resolved = self.resolve_honorific(config, display_name)
        for preset in self._presets.values():
            other = str(preset["template"]).format(displayName=display_name)
            # resolved의 부분 문자열인 호칭("길동님" 속 "길동")은 오탐이므로 제외.
            if other != resolved and other not in resolved and len(other) >= 2 \
                    and other in text:
                violations.append(f"허용 외 호칭 사용: {other}")

        # ③ politeness 혼용 없음 — 자기 스타일에 안 맞으면서 반대 수준 접미로 끝나는
        # 문장 검사("좋네요"처럼 자기 스타일에 맞는 문장은 혼용이 아님).
        opposite_styles = (
            ("hagae", "banmal_chae") if config.speech.politeness == "jondae"
            else ("haeyo", "hapsyo")
        )
        for s in sentences:
            if s.endswith(own):
                continue
            for style in opposite_styles:
                if s.endswith(_STYLE_SUFFIXES[style]):
                    violations.append(f"존대 수준 혼용: '...{s[-3:]}' 출현")
                    break
            else:
                continue
            break

        # ④ easy 난이도 — 미해설 전문용어 0건(용어 직후 풀어쓰기 괄호 필요).
        if config.difficulty == "easy":
            for term in _EXPERT_TERMS:
                for m in re.finditer(re.escape(term), text):
                    after = text[m.end():m.end() + 1]
                    if after != "(":
                        violations.append(f"easy 난이도 미해설 용어: {term}")
                        break

        return ComplianceReport(
            passed=not violations, ending_ratio=round(ratio, 3), violations=violations,
        )
