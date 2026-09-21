"""12신살 방위 활용(Sinsal Direction) 계층 타입 — docs/18.

출생 연지의 삼합국을 기준으로 12신살을 12지지 방위에 배치하고, 방향 자체의 길흉이 아니라
**그 방향에 놓인 신살 × 사용 목적**으로 활용도를 판정하기 위한 사전 스키마·프로필·추천 타입.

원칙(docs/18 §1):
- 연지는 띠 계산이 아니라 만세력 年支(입춘 기준)를 쓴다.
- 절대 방위(`absolute_direction`)와 상대 신살(`relative_sinsal`)은 별개 필드다.
- 용신 오행 방위(`calendar/direction_rules.json`)와 합산하지 않는다 — 서로 다른 질문이다.
- 점수·판정·날짜·간지 파이프라인에 영향을 주지 않는 서술 전용(inert) 계층이다.
- 각도 경계는 정의하지 않는다(지지·4방 라벨만 저장).

이 모듈은 기존 `direction_suggestions`(E8 삶의 방향 능동 제안)와 **다른 계층**이다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .twelve_sinsal import TWELVE_SINSAL_ORDER

#: 4방 라벨. 寅卯辰=동 / 巳午未=남 / 申酉戌=서 / 亥子丑=북(지지 고정 방위).
Cardinal4 = Literal["동", "남", "서", "북"]

#: 8방위 코드(프로필 Direction8과 동일 표기) — 거실 주 창 방향 등 랜드마크 입력용.
Direction8Code = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

#: 12지지 방위 = 30° 등분, 子=정북 중심(345°~15°) — 2026-09-21 데굴님 승인(docs/18 §1-8 개정).
#: 16방위 이름 중 간방 4개(북동·남동·남서·북서)를 뺀 12개와 1:1 이라 사용자 노출 라벨로 쓴다.
#: 값 = (16방위 이름, 중심 각도). 구간은 중심 ±15°. 도수는 표기된 구간만 인용(임의 도수 생성 금지).
BRANCH_COMPASS: dict[str, tuple[str, int]] = {
    "子": ("정북", 0), "丑": ("북북동", 30), "寅": ("동북동", 60), "卯": ("정동", 90),
    "辰": ("동남동", 120), "巳": ("남남동", 150), "午": ("정남", 180), "未": ("남남서", 210),
    "申": ("서남서", 240), "酉": ("정서", 270), "戌": ("서북서", 300), "亥": ("북북서", 330),
}


def compass_range(branch: str) -> str:
    """지지의 나침반 구간 문자열('345°~15°')."""
    center = BRANCH_COMPASS[branch][1]
    return f"{(center - 15) % 360}°~{(center + 15) % 360}°"


def branch_compass_label(branch: str) -> str:
    """지지 → '북북동 15°~45°'(16방위 이름 + 구간). 프롬프트·리포트 공용 라벨."""
    return f"{BRANCH_COMPASS[branch][0]} {compass_range(branch)}"

#: 목적 × 신살 적합 등급(정성 4단계 — 수치 점수 금지, docs/18 §3).
FitGrade = Literal["fit", "support", "neutral", "caution"]

FIT_GRADE_KO: dict[str, str] = {
    "fit": "적합", "support": "보조", "neutral": "중립", "caution": "주의",
}

#: 서비스 판정 등급 5단계(docs/19 §1) — 사전 4등급 위에 얹는 **계산값**. 절대흉방(ABSOLUTE_AVOID)은
#: 만들지 않는다. STRONG_AVOID 는 목적 충돌(caution) + 시간·공간 중첩 조건(docs/19 §4)으로만 나온다.
Verdict = Literal["BEST_USE", "GOOD_USE", "NEUTRAL", "CAUTION", "STRONG_AVOID"]

VERDICT_KO: dict[str, str] = {
    "BEST_USE": "적극 활용", "GOOD_USE": "잘 맞음", "NEUTRAL": "중립",
    "CAUTION": "주의(목적 충돌)", "STRONG_AVOID": "강한 회피",
}

#: 사전 등급 → 기본 verdict(중첩 조건 평가 전).
VERDICT_BY_GRADE: dict[str, str] = {
    "fit": "BEST_USE", "support": "GOOD_USE", "neutral": "NEUTRAL", "caution": "CAUTION",
}


class SinsalGroupKey(StrEnum):
    """12신살 3개씩 4구간(영상 §6) — 각 구간은 순서가 있는 상태 전이(sequence)."""

    TRIAL = "trial"  # 겁살→재살→천살: 시련·외압 — 멈춤·집중·계획
    ACTIVITY = "activity"  # 지살→년살→월살: 활동·경험 — 이동·교류·노출
    ACHIEVEMENT = "achievement"  # 망신살→장성살→반안살: 성취·안정 — 노출→권한→안착
    TRANSITION = "transition"  # 역마살→육해살→화개살: 변화·수렴 — 변화→마찰→정리


class UsageMode(StrEnum):
    """방향을 '쓰는 방식' — 같은 신살이라도 다섯 가지를 합치면 해석이 모호해진다(§9)."""

    POSITION = "position"  # 공간 내 위치(방 중심 기준 책상·화장대가 놓인 쪽)
    FACE = "face"  # 바라보는 방향(책상에 앉아 시선이 향하는 쪽)
    HEAD = "head"  # 수면 시 머리 방향
    MOVE = "move"  # 이동 목적지 방향(현 위치 기준)
    ENTRANCE = "entrance"  # 출입구·문 방향


class Anchor(StrEnum):
    """방향을 재는 기준점 — 정하지 않으면 같은 책상도 결과가 달라진다."""

    HOME_CENTER = "home_center"
    ROOM_CENTER = "room_center"
    USER_POSITION = "user_position"


class EnvironmentState(StrEnum):
    """해당 방향의 공간 상태 — 벽·블라인드·창 사례(§ 차단·노출·개방)."""

    OPEN = "open"
    EXPOSED = "exposed"
    COVERED = "covered"
    BLOCKED = "blocked"


class UsageStrategy(StrEnum):
    """활용 전략 8종 — 활성화/회피 이분법 대신 신살마다 다른 쓰임을 구분한다."""

    ACTIVATE = "activate"  # 기운을 적극 활용(년살에서 촬영·메이크업)
    FOCUS = "focus"  # 머무르는 속성 활용(재살에서 장시간 공부)
    FACE = "face"  # 바라보는 대상으로 사용(천살 방향 모니터)
    SETTLE = "settle"  # 휴식·정착(반안살 쪽으로 머리)
    MOVE = "move"  # 움직임 자체를 사용(역마살 방향 여행)
    MODULATE = "modulate"  # 필요할 때만 열기(년살 창가·블라인드)
    SHIELD = "shield"  # 기운을 약하게 사용(월살을 가리거나 장식)
    REFLECT = "reflect"  # 수렴·내면화(화개살에서 상담·명상)


class DirectionPurpose(StrEnum):
    """사용 목적 16종(영상 §8 표 13종 + docs/19 §3 자료 3종 — 임의 추가·삭제 금지)."""

    STUDY = "study"  # 공부·시험
    RESEARCH = "research"  # 연구·기획
    BEAUTY = "beauty"  # 메이크업·외모 연출
    DATING = "dating"  # 소개팅·데이트
    SALES = "sales"  # 영업·장사
    BRANDING = "branding"  # SNS·유튜브·브랜딩
    PRESENTATION = "presentation"  # 발표·인지도
    LEADERSHIP = "leadership"  # 리더십·협상
    SLEEP = "sleep"  # 숙면
    TRAVEL = "travel"  # 여행·이동
    RELOCATION = "relocation"  # 이사·환경 변화
    COUNSELING = "counseling"  # 상담·명상
    REFLECTION = "reflection"  # 자기성찰·정리
    RECONCILIATION = "reconciliation"  # 화해·관계회복(docs/19 §3)
    NEW_START = "new_start"  # 새로운 일 시작(docs/19 §3)
    SETTLING = "settling"  # 안정·정착(docs/19 §3)


# ── 사전 스키마(dictionaries/sinsal_direction.json) ─────────────────────────


class SinsalDirectionEntry(BaseModel):
    """12신살 1종의 방위 활용 의미(영상 §7 재해석 — 전통 의미와 구분해 '활용 해석'으로만)."""

    name: str  # 12신살명(년살 표기 고정)
    hanja: str
    alias: str | None = None  # 도화살·수옥살 등 통용 별칭(병기용)
    group: SinsalGroupKey
    sequence_index: int = Field(ge=1, le=3)  # 구간 내 순서(1→2→3 상태 전이)
    core_meaning: str  # 영상의 핵심 의미(경쟁·쟁취·긴장 등)
    service_use: str  # 서비스 적용 예(경쟁 분석, 집중 작업 등)
    default_usage_mode: UsageMode
    strategy: UsageStrategy
    action_hints: list[str] = Field(min_length=1)
    cautions: list[str] = Field(default_factory=list)
    # docs/19 §2 — 이 신살 방향이 특히 −가 되는 상황 / +가 되는 상황(같은 방향도 목적에 따라
    # 뒤집힘).
    avoid_contexts: list[str] = Field(default_factory=list)
    use_contexts: list[str] = Field(default_factory=list)


class SinsalGroupEntry(BaseModel):
    """4구간 1종 — 핵심 성격·서비스 활용·순차 흐름(sequence) 문구."""

    key: SinsalGroupKey
    name_ko: str  # 시련·외압 / 활동·경험 / 성취·안정 / 변화·수렴
    sinsals: list[str] = Field(min_length=3, max_length=3)  # 순서 = 상태 전이 순서
    character: str  # 멈춤·집중·외부 압력 등
    service_use: str  # 공부·연구·사색·계획 등
    sequence_ko: str  # '경쟁/빼앗김 → 얽힘/구속 → 외력 앞에서 멈춤'
    quadrant_theme: str  # 방향판 제목('집중과 연구')


class PurposeEntry(BaseModel):
    """사용 목적 1종 — 우선 신살·사용 방식·목적×신살 적합 등급·행동 문구."""

    purpose: DirectionPurpose
    name_ko: str
    # 수동 방향 질문의 intent 도메인(파서가 읽는다 — 코드 맵 금지, 사전 SSOT). general 허용.
    domain: Literal[
        "career", "relationship", "relocation", "wealth", "education", "health", "general"
    ]
    keywords: list[str] = Field(min_length=1)  # 파서 감지 어휘(수동 질문)
    usage_mode: UsageMode
    primary_sinsals: list[str] = Field(min_length=1)  # 우선 활용 신살(순서=우선순위)
    grades: dict[str, FitGrade]  # 12신살 전체 등급(누락 시 lint 실패)
    action_template: str  # '{direction}쪽을 {mode_ko}로 활용해 볼 수 있습니다' 류
    trigger_domains: list[str] = Field(default_factory=list)  # 능동 제안 트리거(intent 도메인)

    @model_validator(mode="after")
    def _check_grades(self) -> PurposeEntry:
        """12신살 전체 등급이 있어야 하고 primary_sinsals 는 등급표에 있어야 한다."""
        missing = [s for s in TWELVE_SINSAL_ORDER if s not in self.grades]
        if missing:
            raise ValueError(f"{self.purpose}: 등급 누락 신살 — {missing}")
        for s in self.primary_sinsals:
            if s not in self.grades:
                raise ValueError(f"{self.purpose}: primary_sinsals에 미등록 신살 — {s}")
        return self


class SamjaeStageEntry(BaseModel):
    """삼재 1단계 — 12신살 대응·핵심 신호·현대 사건 후보(맥락 신호 전용, 점수 아님)."""

    stage: Literal["enter", "stay", "exit"]
    label_ko: str  # 들삼재/눌삼재/날삼재
    sinsal: str  # 역마살/육해살/화개살
    core_signal: str
    event_candidates: list[str] = Field(min_length=1)
    reading_note: str  # '움직임이 커지는 단계' 등 서술 지침


# ── 삼재 품질 캘리브레이션(docs/18 §4-2) ────────────────────────────────────


class SamjaeWeights(BaseModel):
    """quality_score 합성 가중치 — 서비스 캘리브레이션 상수(명리 수치 아님)."""

    annual_luck: float = Field(ge=0.0, le=1.0)
    daewoon_luck: float = Field(ge=0.0, le=1.0)
    event_direction: float = Field(ge=0.0, le=1.0)
    clash_note: float = Field(ge=0.0, le=1.0)
    ten_god_balance: float = Field(ge=0.0, le=1.0)
    alignment_bonus: float = Field(ge=0.0, le=1.0)


class SamjaeThresholds(BaseModel):
    """복/악 판정 임계(bok ≥ / ak ≤)·도메인 등급 임계·동조 최소 절댓값."""

    bok: float = Field(gt=0.0, le=1.0)
    ak: float = Field(ge=-1.0, lt=0.0)
    domain: float = Field(gt=0.0, le=1.0)
    alignment_min_abs: float = Field(ge=0.0, le=1.0)


class SamjaeStrengthBands(BaseModel):
    """강도 밴드 상한(약 < weak ≤ 중 < moderate ≤ 강)."""

    weak: float = Field(gt=0.0, lt=1.0)
    moderate: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> SamjaeStrengthBands:
        """밴드 상한은 약 < 중 순서여야 한다."""
        if self.weak >= self.moderate:
            raise ValueError("strength bands: weak < moderate 이어야 한다")
        return self


class SamjaeStrengthConfig(BaseModel):
    """강도 합성 — 세운 점수 절댓값·사건화 트리거·겹삼재 가산."""

    luck_weight: float = Field(ge=0.0, le=1.0)
    trigger_weight: float = Field(ge=0.0, le=1.0)
    trigger_max: float = Field(gt=0.0)
    overlap_bonus: float = Field(ge=0.0, le=1.0)
    bands: SamjaeStrengthBands


class SamjaeOverlapKind(BaseModel):
    """겹삼재 종류 — daewoon(대운 지지 삼재권) / natal_clash(삼재 세운 지지가 원국 지지와 충)."""

    kind: Literal["daewoon", "natal_clash"]
    label_ko: str
    phrase: str


class SamjaeStagePhrase(BaseModel):
    """단계(들/눌/날) × 품질(복/평/악) 9칸 표현 1칸."""

    stage: Literal["enter", "stay", "exit"]
    quality: Literal["bok", "normal", "ak"]
    phrase: str


class SamjaeQualityConfig(BaseModel):
    """`samjae_quality` 절 루트."""

    weights: SamjaeWeights
    thresholds: SamjaeThresholds
    strength: SamjaeStrengthConfig
    overlap_kinds: list[SamjaeOverlapKind] = Field(min_length=2, max_length=2)
    stage_quality_phrases: list[SamjaeStagePhrase] = Field(min_length=9, max_length=9)
    quality_meaning: dict[Literal["bok", "normal", "ak"], str]

    @model_validator(mode="after")
    def _full_grid(self) -> SamjaeQualityConfig:
        """단계 3 × 품질 3 = 9칸이 중복 없이 모두 있어야 하고 겹삼재 종류 2개가 각 1개."""
        cells = {(p.stage, p.quality) for p in self.stage_quality_phrases}
        if len(cells) != 9:
            raise ValueError("stage_quality_phrases: 3×3 전체 칸이 중복 없이 있어야 한다")
        kinds = {k.kind for k in self.overlap_kinds}
        if kinds != {"daewoon", "natal_clash"}:
            raise ValueError("overlap_kinds: daewoon·natal_clash 각 1개")
        return self


class SinsalDirectionDict(BaseModel):
    """`dictionaries/sinsal_direction.json` 루트."""

    schema_version: str = Field(alias="schema")
    version: str
    reviewed: bool
    notes: list[str] = Field(default_factory=list)
    sinsals: list[SinsalDirectionEntry] = Field(min_length=12, max_length=12)
    groups: list[SinsalGroupEntry] = Field(min_length=4, max_length=4)
    purposes: list[PurposeEntry] = Field(min_length=16, max_length=16)
    samjae_stages: list[SamjaeStageEntry] = Field(min_length=3, max_length=3)
    samjae_quality: SamjaeQualityConfig
    forbidden_framings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def sinsal(self, name: str) -> SinsalDirectionEntry:
        """12신살명 → 사전 항목."""
        for e in self.sinsals:
            if e.name == name:
                return e
        raise KeyError(name)

    def group(self, key: SinsalGroupKey) -> SinsalGroupEntry:
        """구간 키 → 사전 항목."""
        for g in self.groups:
            if g.key is key:
                return g
        raise KeyError(key)

    def purpose(self, purpose: DirectionPurpose) -> PurposeEntry:
        """목적 → 사전 항목."""
        for p in self.purposes:
            if p.purpose is purpose:
                return p
        raise KeyError(purpose)


# ── 프로필·추천 결과 ────────────────────────────────────────────────────────


class DirectionSector(BaseModel):
    """12방위 섹터 1칸 — 절대 지지·4방(고정)과 상대 신살(연지 의존)을 분리 보관."""

    branch: str  # 절대 지지(子…亥)
    absolute_direction: Cardinal4
    relative_sinsal: str
    group: SinsalGroupKey
    sequence_index: int


class DirectionQuadrant(BaseModel):
    """4방 1칸 — 그 방향에 놓인 3신살 구간과 방향판 제목."""

    absolute_direction: Cardinal4
    branches: list[str] = Field(min_length=3, max_length=3)
    sinsals: list[str] = Field(min_length=3, max_length=3)
    group: SinsalGroupKey
    theme: str  # '집중과 연구' 등
    service_use: str


class SinsalDirectionProfile(BaseModel):
    """사용자 기본 방향 프로필(연지 → 삼합 → 12방위 신살 → 4방 요약)."""

    year_branch: str
    trine_group: str  # '申子辰'
    sectors: list[DirectionSector] = Field(min_length=12, max_length=12)
    quadrants: list[DirectionQuadrant] = Field(min_length=4, max_length=4)
    samjae_branches: list[str] = Field(min_length=3, max_length=3)  # 들→눌→날 세운 지지

    def sector_of(self, sinsal: str) -> DirectionSector:
        """신살명 → 섹터."""
        for s in self.sectors:
            if s.relative_sinsal == sinsal:
                return s
        raise KeyError(sinsal)


class DirectionPick(BaseModel):
    """목적 추천 1건 — 어느 신살·지지·4방을 어떤 등급·행동으로.

    `grade` 는 사전 등급(정적), `verdict` 는 서비스 판정 5단계(docs/19 §1). verdict 는 기본값이
    등급 대응값이며 `direction_avoidance.annotate_avoidance` 가 시간·공간 중첩(docs/19 §4)을
    평가해 CAUTION→STRONG_AVOID 로 올리거나 BEST_USE 에 일치 근거를 덧붙인다.
    """

    sinsal: str
    branch: str
    absolute_direction: Cardinal4
    grade: FitGrade
    action: str
    verdict: Verdict = "NEUTRAL"
    verdict_evidence: list[str] = Field(default_factory=list)  # 한글 근거(수치 없음)
    same_quadrant_as_fit: bool = False  # 적합 방향과 같은 4방 안의 주의 신살(지지 단위 구분용)


class SinsalDirectionRecommendation(BaseModel):
    """목적 1종에 대한 방향 활용 추천(길방 1개가 아니라 적합/피함 분리).

    cautions 는 그 목적의 caution 등급 **전부**(docs/19 §6-3 — 2026-09-21 데굴님 결정). 적합 방향과
    같은 4방 안의 것은 `same_quadrant_as_fit` 로 표시해 지지 단위 안내에 쓴다.
    """

    purpose: DirectionPurpose
    purpose_ko: str
    usage_mode: UsageMode
    picks: list[DirectionPick]  # 적합·보조(우선순위순)
    cautions: list[DirectionPick]  # 목적 한정 피할 방향(caution 전부, 같은 4방 우선)
    strategy: UsageStrategy


class LandmarkNote(BaseModel):
    """거실 주 창 방향(프로필 livingRoomFacing)을 상대 랜드마크로 번역한 결과(P2 보완안).

    8방위 간방(NE/SE/SW/NW)은 지지 2개에 걸치므로 후보 2개를 모두 적고 나침반 확인을 권한다.
    """

    facing_code: Direction8Code
    facing_ko: str
    window_side: list[str]  # 창 쪽 후보 지지·신살 ('午 장성살')
    opposite_side: list[str]  # 창을 등진 쪽
    ambiguous: bool  # 간방 여부


class SinsalDirectionBlock(BaseModel):
    """LLM 입력 블록 — 프로필 요약 + 목적별 추천 + 랜드마크·기준점 고지.

    수동(proactive=False)이면 목적 전체 한 줄표(상황별 조언 재료)와 회피 근거 줄이 함께 실린다
    (docs/19 §6). 능동이면 목적 추천만 짧게.
    """

    profile: SinsalDirectionProfile
    recommendations: list[SinsalDirectionRecommendation] = Field(default_factory=list)
    landmark: LandmarkNote | None = None
    anchor: Anchor = Anchor.USER_POSITION
    proactive: bool = True  # 능동 제안(질문이 방향을 직접 묻지 않음)
    avoidance_basis: list[str] = Field(default_factory=list)  # 중첩 판정 기준(연도·세운 신살 등)
    # 사용자가 지목한 방향('남쪽은 어때?') — 첫 목적 기준으로 그 방향의 지지별 판정(docs/19 §6-7).
    asked_direction_ko: str | None = None
    asked_code: str | None = None  # 16방위 코드(N/NNE/NE/…) — 정방·간방·16방위 표현 분기용
    asked_sectors: list[DirectionPick] = Field(default_factory=list)
