"""사용자 프로필 & 페르소나 schemas (v2.2 Phase 8.5, docs/11 — 전체 규격).

docs/11의 필드·enum·분류는 예시가 아니라 전체 규격 — 임의 추가·삭제·재해석 금지.
원칙: 2단계 미입력은 어떤 기능도 차단하지 않는다(정밀도만 차이, 4장 영향표).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Direction8 = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class BirthPlace(BaseModel):
    """출생지 — 진태양시(경도) 보정 입력. 좌표 변환은 시스템이 수행."""

    country: str = "KR"
    city: str
    longitude: float | None = None


class MultipleBirth(BaseModel):
    """쌍둥이/다태아 (docs/11 2-2). 미입력 = 해당 없음."""

    total: int = Field(ge=2)
    order: int = Field(ge=1)

    @model_validator(mode="after")
    def _order_in_range(self) -> MultipleBirth:
        if self.order > self.total:
            raise ValueError("order는 1~total 범위")
        return self


class BasicProfile(BaseModel):
    """1단계 — 사주 계산 필수(미완료 시 서비스 진입 불가)."""

    birth_date: str  # 'YYYY-MM-DD'
    calendar_type: Literal["solar", "lunar"] = "solar"
    is_leap_month: bool = False
    birth_time: str | None = None  # 'HH:mm', null = 시간 모름
    birth_time_unknown: bool = False
    birth_time_approx: Literal["새벽", "아침", "낮", "저녁", "밤"] | None = None
    birth_place: BirthPlace
    gender: Literal["M", "F"]
    multiple_birth: MultipleBirth | None = None
    display_name: str = Field(min_length=2, max_length=10)


class Occupation(BaseModel):
    """직업 — 닫힌 분류(O01~O18, 자유 텍스트 아님)."""

    category_id: str = Field(pattern=r"^O(0[1-9]|1[0-8])$")
    detail: str | None = Field(default=None, max_length=30)
    employment_form: (
        Literal["정규직", "계약직", "프리랜서", "자영업", "법인대표", "무급가족종사"] | None
    ) = None


class Residence(BaseModel):
    """거주 — region은 M10 방위 기준점, livingRoomFacing은 풍수 질문 전용(혼용 금지)."""

    region: str
    living_room_facing: Direction8 | Literal["unknown"] | None = None


class ChildItem(BaseModel):
    """자녀 1명 — 출생 정보 입력 시 동반자 등록 제안(강제 아님)."""

    label: str
    gender: Literal["M", "F"] | None = None
    birth_date: str | None = None
    registered_companion_id: str | None = None


class Children(BaseModel):
    """자녀 정보."""

    count: int = Field(ge=0)
    items: list[ChildItem] = Field(default_factory=list)


MaritalStatus = Literal["미혼", "연애중", "기혼", "재혼", "별거", "이혼", "사별"]


class ExtendedProfile(BaseModel):
    """2단계 — 전 필드 스킵 가능. 부재로 오류/기능 숨김 금지(구현 가드)."""

    occupation: Occupation | None = None
    residence: Residence | None = None
    marital_status: MaritalStatus | None = None
    children: Children | None = None


# ── 페르소나 (5장 — 조합형) ─────────────────────────────────────

Politeness = Literal["jondae", "banmal"]
SpeechStyle = Literal["haeyo", "hapsyo", "hagae", "banmal_chae"]
# 유효 조합(전체 규격): jondae→haeyo|hapsyo, banmal→banmal_chae|hagae.
VALID_SPEECH: dict[str, set[str]] = {
    "jondae": {"haeyo", "hapsyo"},
    "banmal": {"banmal_chae", "hagae"},
}


class SpeechConfig(BaseModel):
    """말투 — politeness×style 유효 조합 강제."""

    politeness: Politeness = "jondae"
    style: SpeechStyle = "haeyo"

    @model_validator(mode="after")
    def _valid_combo(self) -> SpeechConfig:
        if self.style not in VALID_SPEECH[self.politeness]:
            raise ValueError(f"무효 조합: {self.politeness}+{self.style}")
        return self


HonorificPresetId = Literal[
    "name_nim", "nim_only", "name_only", "neo", "jane", "gogaeknim", "seonsaengnim",
]


class UserHonorific(BaseModel):
    """호칭 — preset 또는 custom(금칙어 필터 통과 필수, 검증은 persona 엔진)."""

    type: Literal["preset", "custom"] = "preset"
    preset_id: HonorificPresetId | None = "name_nim"
    custom_text: str | None = Field(default=None, max_length=10)


class PersonaConfig(BaseModel):
    """페르소나 5축 (docs/11 5-1). 기본값: female·40s·jondae+haeyo·standard·name_nim."""

    counselor_gender: Literal["female", "male", "neutral"] = "female"
    counselor_age_band: Literal["20s", "30s", "40s", "50s", "60s_plus"] = "40s"
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    difficulty: Literal["easy", "standard", "expert"] = "standard"
    user_honorific: UserHonorific = Field(default_factory=UserHonorific)


# ── 쌍둥이 차트 변형 (2-2) ──────────────────────────────────────

ChartVariant = Literal["original", "twin_adjusted"]


class ChartVariantState(BaseModel):
    """차트 변형 관리 — order≥2는 두 변형 보관, active로만 사전계산·풀이."""

    available: list[ChartVariant]
    active: ChartVariant
    twin_shift: int = Field(ge=0)  # order - 1


class UserProfile(BaseModel):
    """user_profiles 행 (docs/11 6장)."""

    user_id: str
    basic: BasicProfile
    extended: ExtendedProfile | None = None
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    extended_completed_at: str | None = None  # null = 2단계 스킵 상태
