"""사용자 프로필 엔진 (v2.2 Phase 8.5 T8.5.1~T8.5.4·T8.5.8~T8.5.10, docs/11).

- 1단계 변환: BasicProfile → 만세력 BirthInput(보정은 기존 엔진 그대로 — 재구현 금지).
- 쌍둥이 시주 조정(2-2): order≥2 → 시주 (n-1)칸 전진. wrap 시 일·월·년주 불변,
  천간은 원 일간 기준 시두법(twin_wrap_convention 기본값 — 변경은 사용자 승인 필요).
- 2단계 연동: occupation→E3/E6, marital→M01/M02 분기, children→동반자 제안.
- Just-in-time 수집(1장 원칙 2): 세션 내 1회 요청, 거절 시 재요청 금지 + 한계 고지.
- 대화 추출 갱신(T8.5.8/F9): 사용자 확인 전 저장 금지.
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from functools import lru_cache
from pathlib import Path

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.profile import (
    BasicProfile,
    ChartVariantState,
    Children,
    ExtendedProfile,
)

# 12지지 순서(시진) — 子시 23:00 시작.
_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
# 시두법 — 일간 → 子시 천간(甲己→甲, 乙庚→丙, 丙辛→戊, 丁壬→庚, 戊癸→壬).
_SIDU_START = {"甲": 0, "己": 0, "乙": 2, "庚": 2, "丙": 4, "辛": 4,
               "丁": 6, "壬": 6, "戊": 8, "癸": 8}

# wrap 처리 유파 플래그(docs/11 2-2 — 기본값 변경은 사용자 승인 필요).
TWIN_WRAP_CONVENTION = "sidubeop_from_original_day"

# 대략 시간대 → 대표 후보 시각(시주 후보 2~3개 병기 모드 — 단일 확정 금지).
_APPROX_CANDIDATES: dict[str, list[str]] = {
    "새벽": ["01:30", "03:30", "05:30"],
    "아침": ["07:30", "09:30"],
    "낮": ["11:30", "13:30", "15:30"],
    "저녁": ["17:30", "19:30"],
    "밤": ["21:30", "23:30"],
}

# 미입력 영향표(docs/11 4장) — 차단 금지, 한계 고지 문구만.
MISSING_FIELD_NOTICES: dict[str, str] = {
    "birth_time": (
        "출생 시간 미입력 — 시주를 제외한 3주 분석이며 말년·자녀궁 정밀도에 한계가 있어요."
    ),
    "birth_place_city": (
        "출생 도시 미입력 — 표준시로 계산했어요"
        "(시 경계 ±30분 출생자는 시주가 달라질 수 있어요)."
    ),
    "occupation": (
        "직업 미입력 — 일반형 발현 확률로 안내해요"
        "(직업을 알려주시면 더 구체적으로 좁혀져요)."
    ),
    "residence_region": "거주 지역 미입력 — 방위 답변은 어려워요(날짜 추천은 정상 제공).",
    "living_room_facing": "거실 방향 미입력 — 배치 질문에 일반 원칙으로만 답해요.",
    "marital_status": "결혼 상태를 가정하지 않았어요 — 정확한 풀이를 위해 확인이 필요해요.",
    "children": "자녀 정보가 없어 질문에 담긴 정보로만 풀이했어요(등록하시면 이어볼 수 있어요).",
}


def basic_to_birth_input(
    basic: BasicProfile, reference_date: date_cls | None = None
) -> BirthInput:
    """1단계 프로필 → 만세력 입력(T8.5.1 — 보정은 엔진 기존 방식 그대로)."""
    return BirthInput(
        calendar_type=basic.calendar_type,
        is_leap_month=basic.is_leap_month if basic.calendar_type == "lunar" else None,
        birth_date=date_cls.fromisoformat(basic.birth_date),
        birth_time=None if basic.birth_time_unknown else basic.birth_time,
        birth_time_unknown=basic.birth_time_unknown,
        birth_place_name=basic.birth_place.city,
        country_code=basic.birth_place.country,
        longitude=basic.birth_place.longitude,
        gender="male" if basic.gender == "M" else "female",
        reference_date=reference_date,
    )


def approx_hour_candidates(approx: str) -> list[str]:
    """시간 모름+대략 시간대 → 시주 후보용 대표 시각 2~3개(단일 확정 금지)."""
    return list(_APPROX_CANDIDATES.get(approx, []))


# ── T8.5.10 쌍둥이 시주 조정 (2-2 전체 규격) ─────────────────────


def twin_adjusted_hour_pillar(
    original_stem: str, original_branch: str, day_stem: str, order: int
) -> tuple[str, str, bool]:
    """출생 순서에 따른 시주 전진 — (천간, 지지, wrap 여부).

    order=1: 변형 없음. order=n: 시지 (n-1)칸 전진 + 시두법 재계산(60갑자 전진과
    동일 결과). wrap(亥→子) 시에도 일·월·년주는 불변 — 조정은 시주 1기둥뿐.
    천간은 **원 일간** 기준 시두법으로 산출(TWIN_WRAP_CONVENTION 기본값).
    """
    shift = order - 1
    if shift == 0:
        return original_stem, original_branch, False
    branch_idx = _BRANCHES.index(original_branch)
    new_idx = (branch_idx + shift) % 12
    wrapped = branch_idx + shift >= 12
    new_branch = _BRANCHES[new_idx]
    new_stem = _STEMS[(_SIDU_START[day_stem] + new_idx) % 10]
    return new_stem, new_branch, wrapped


def chart_variant_state(order: int, active: str | None = None) -> ChartVariantState:
    """변형 상태 — order=1: original만 / order≥2: 둘 다(기본 active=twin_adjusted)."""
    if order <= 1:
        return ChartVariantState(available=["original"], active="original", twin_shift=0)
    return ChartVariantState(
        available=["original", "twin_adjusted"],
        active="twin_adjusted" if active is None else active,
        twin_shift=order - 1,
    )


_ORDER_LABELS = {2: "둘째", 3: "셋째", 4: "넷째", 5: "다섯째"}

_TWIN_NOTICE_ADJUSTED = (
    "{order_label}로 태어난 쌍둥이는 같은 시각에 태어나도\n"
    "시주(時柱)를 한 시진씩 뒤로 보는 해석법이 있어요.\n"
    "지금은 조정된 시주({adjusted_ganji})로 풀이하고 있습니다.\n"
    "실제 태어난 시간 그대로의 시주({original_ganji}) 풀이 —\n"
    "특히 시주가 담당하는 영역(말년·자녀·아랫사람·내면)이\n"
    "더 잘 맞는다고 느껴지면 설정에서 원본으로 전환해 보세요."
)
_TWIN_NOTICE_ORIGINAL = (
    "{order_label} 쌍둥이지만 실제 시각 그대로의 시주({original_ganji})로 풀이 중이에요.\n"
    "시주가 담당하는 영역(말년·자녀·아랫사람·내면) 풀이가 잘 맞지 않는다면\n"
    "조정된 시주({adjusted_ganji})를 사용해 보세요."
)


def render_twin_notice(
    order: int, adjusted_ganji: str, original_ganji: str, active: str
) -> str:
    """쌍둥이 안내 — 고정 템플릿 치환만(즉석 작문 금지). 노출 시점 관리는 호출 측."""
    label = _ORDER_LABELS.get(order, f"{order}째")
    template = _TWIN_NOTICE_ADJUSTED if active == "twin_adjusted" else _TWIN_NOTICE_ORIGINAL
    return template.format(
        order_label=label, adjusted_ganji=adjusted_ganji, original_ganji=original_ganji,
    )


# ── T8.5.3 occupation → E3/E6 연동 ──────────────────────────────

# 고용형태 → user_profile_event_gate occupation_status(구조적 분류는 category_id가 우선).
_EMPLOYMENT_FORM_STATUS: dict[str, str] = {
    "정규직": "employee", "계약직": "employee", "무급가족종사": "employee",
    "프리랜서": "freelancer", "자영업": "business_owner", "법인대표": "business_owner",
}
# 고용형태로 표현되지 않는 구조적 분류(공직·학생·무직)는 category_id가 employment_form보다 우선.
_CATEGORY_STATUS: dict[str, str] = {
    "O02": "public_official", "O17": "student", "O18": "unemployed",
}


def derive_occupation_status(
    employment_form: str | None, category_id: str | None
) -> str | None:
    """프로필 → user_profile_event_gate occupation_status 문자열을 파생한다.

    공직(O02)·학생(O17)·무직(O18)은 고용형태로 표현되지 않는 구조적 분류라 category_id가
    employment_form보다 우선한다(예: 공무원 정규직 → public_official). 그 외에는 고용형태로
    employee/freelancer/business_owner를 정한다. 어디에도 안 걸리면 None(게이트 미적용 — 규칙11).
    """
    if category_id in _CATEGORY_STATUS:
        return _CATEGORY_STATUS[category_id]
    if employment_form in _EMPLOYMENT_FORM_STATUS:
        return _EMPLOYMENT_FORM_STATUS[employment_form]
    return None


# 혼인 상태 → user_profile_event_gate relationship_status(사별은 새 인연 가능 → single).
_MARITAL_STATUS: dict[str, str] = {
    "미혼": "single", "연애중": "dating", "기혼": "married", "재혼": "married",
    "별거": "divorced", "이혼": "divorced", "사별": "single",
}


def derive_relationship_status(marital_status: str | None) -> str | None:
    """프로필 marital_status → user_profile_event_gate relationship_status. 미입력이면 None."""
    return _MARITAL_STATUS.get(marital_status) if marital_status else None


def profile_event_signals(
    subject_id: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """저장된 subject 프로필 → (employment_form, occupation_status, relationship_status, 직업분류).

    user_profile_event_gate 분기·특수직군 충형 길화(자료 9-6)의 입력 — 채팅·테마사주가 공유한다.
    프로필은 선택 입력이므로(규칙11) 조회 실패·부재·무DB는 조용히 (None×4)로 강등한다.
    """
    if not subject_id:
        return None, None, None, None
    import contextlib

    from .profile_store import ProfileStore  # 지연 임포트 — DB 의존을 모듈 로드와 분리

    with contextlib.suppress(Exception):
        profile = ProfileStore().load(subject_id)
        if profile and profile.extended:
            ext = profile.extended
            occ = ext.occupation
            form = occ.employment_form if occ else None
            category = occ.category_id if occ else None
            return (
                form,
                derive_occupation_status(form, category),
                derive_relationship_status(ext.marital_status),
                category,
            )
    return None, None, None, None


class OccupationTaxonomy:
    """occupation_taxonomy.json — 물상 매핑·발현 보정·context modifier(±10 한도)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        data = json.loads(
            (dictionaries_dir / "occupation_taxonomy.json").read_text("utf-8")
        )
        self._items: dict[str, dict] = {i["id"]: i for i in data["items"]}

    def category(self, category_id: str) -> dict | None:
        """분류 1건(없으면 None)."""
        return self._items.get(category_id)

    def form_bias(self, category_id: str, event_key: str) -> str | None:
        """E3: 해당 직업에서 가중할 발현 형태명(예: O14+relocation → '출장·파견')."""
        item = self._items.get(category_id)
        return (item or {}).get("formBias", {}).get(event_key)

    def reality_context(self, extended: ExtendedProfile | None) -> dict[str, int]:
        """E6 contextModifier 입력 — 직업 기반(±10 한도). 미입력이면 빈 dict(보정 0)."""
        if extended is None or extended.occupation is None:
            return {}
        item = self._items.get(extended.occupation.category_id) or {}
        return {
            k: max(-10, min(10, int(v)))
            for k, v in item.get("contextModifiers", {}).items()
        }


# ── T8.5.4 결혼 상태/자녀 분기 ───────────────────────────────────


def marital_routing(marital_status: str | None, domain: str) -> dict:
    """M01/M02 분기 — '미혼' 가정 금지(모호하면 확인 질문).

    Returns:
        {'module','needs_confirmation','confirm_question'?}.
    """
    if domain != "relationship":
        return {"module": "M_DOMAIN", "needs_confirmation": False}
    if marital_status is None:
        return {
            "module": "M01", "needs_confirmation": True,
            "confirm_question": "현재 연애/결혼 상태를 알려주시면 더 정확해요 — 어떤 상태이신가요?",
        }
    if marital_status in ("기혼", "재혼", "별거"):
        return {
            "module": "M02", "needs_confirmation": True,
            "confirm_question": (
                "배우자와의 관계운으로 풀이할까요, 아니면 다른 의미의 연애운인가요?"
            ),
        }
    if marital_status in ("이혼", "사별"):
        return {"module": "M02_REMARRIAGE", "needs_confirmation": False}
    return {"module": "M01", "needs_confirmation": False}


def children_registration_suggestions(children: Children | None) -> list[str]:
    """출생 정보가 입력된 자녀 → 동반자 등록 제안(강제 아님, E14 전환은 별도)."""
    if children is None:
        return []
    return [
        c.label for c in children.items
        if c.birth_date is not None and c.registered_companion_id is None
    ]


# ── T8.5.2 Just-in-time 수집 + 삭제 ──────────────────────────────


class JustInTimeTracker:
    """세션 단위 2단계 필드 요청 관리 — 1회만 요청, 거절 시 재요청 금지."""

    def __init__(self) -> None:
        self._requested: set[str] = set()
        self._declined: set[str] = set()

    def should_request(self, field: str) -> bool:
        """이 필드를 지금 요청해도 되는가(첫 요청만 True)."""
        if field in self._requested or field in self._declined:
            return False
        self._requested.add(field)
        return True

    def mark_declined(self, field: str) -> str:
        """거절 기록 — 같은 세션 재요청 금지, 한계 고지 문구 반환."""
        self._declined.add(field)
        return MISSING_FIELD_NOTICES.get(field, "해당 정보 없이 일반 기준으로 안내해요.")

    def limitation_notice(self, field: str) -> str:
        """미입력 한계 고지(4장 영향표)."""
        return MISSING_FIELD_NOTICES.get(field, "")


def delete_extended_field(
    extended: ExtendedProfile, field: str
) -> tuple[ExtendedProfile, list[str]]:
    """2단계 필드 개별 삭제 — (갱신본, 무효화할 캐시 키 목록).

    삭제 즉시 관련 Reality Context modifier 캐시 무효화(1장 원칙 4).
    """
    if field not in ExtendedProfile.model_fields:
        raise ValueError(f"알 수 없는 2단계 필드: {field}")
    updated = extended.model_copy(update={field: None})
    invalidations = {
        "occupation": ["reality_context", "event_form_bias"],
        "residence": ["location_base"],
        "marital_status": ["m01_m02_routing"],
        "children": ["companion_suggestions"],
    }
    return updated, invalidations.get(field, [])


# ── T8.5.8 대화 추출 → 사용자 확인 → 갱신 (F9) ───────────────────


def apply_extracted_updates(
    extended: ExtendedProfile | None,
    updates: dict,
    confirmed: bool,
) -> tuple[ExtendedProfile | None, list[str], list[str]]:
    """대화에서 추출된 프로필 갱신 — **확인 전 저장 금지**(1장 원칙 3).

    Returns:
        (프로필, 확인 질문 목록(미확인 시), 무효화 캐시 키(확인 시)).
    """
    if not confirmed:
        questions = [
            f"말씀 중 '{field}: {value}'로 이해했어요 — 프로필에 저장할까요?"
            for field, value in updates.items()
        ]
        return extended, questions, []  # 무단 저장 금지

    base = extended or ExtendedProfile()
    valid = {k: v for k, v in updates.items() if k in ExtendedProfile.model_fields}
    updated = base.model_copy(update=valid)
    invalidations = [key for f in valid for key in delete_extended_field(base, f)[1]]
    return updated, [], invalidations


# ── 물상(2단계 프로필) 사실 맥락 → 풀이 프롬프트 주입용 (사용자 확정 2026-07-02) ──────────
# 계산 보정이 아니라 LLM이 상황에 맞게 구체화할 '사실 맥락'이다. 점수·간지·판정 불변, 페르소나 아님.
_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

# 질문 도메인(Domain enum 값) → 노출할 프로필 필드(개인정보 최소화·관련성 기준).
_PROFILE_DOMAIN_FIELDS: dict[str, tuple[str, ...]] = {
    "career": ("occupation",),
    "wealth": ("occupation",),
    "education": ("occupation",),
    "relocation": ("residence", "occupation"),
    "relationship": ("marital_status", "children"),
    "health": (),
    "general": ("occupation", "marital_status"),
}


@lru_cache(maxsize=1)
def _occupation_taxonomy() -> OccupationTaxonomy:
    return OccupationTaxonomy(_DICTS_DEFAULT)


def _occupation_label(category_id: str) -> str:
    """직업 분류 id → 한글 라벨(없으면 id 그대로)."""
    item = _occupation_taxonomy().category(category_id)
    return str(item.get("ko", category_id)) if item else category_id


def profile_facts_lines(extended: ExtendedProfile | None, domain: str | None) -> list[str]:
    """물상(2단계 프로필) 사실 맥락 줄 — 도메인에 맞는 항목만. 사실 서술(판정·페르소나 아님)."""
    if extended is None:
        return []
    fields = _PROFILE_DOMAIN_FIELDS.get(domain or "general", ("occupation", "marital_status"))
    lines: list[str] = []
    if "occupation" in fields and extended.occupation:
        occ = extended.occupation
        parts = [_occupation_label(occ.category_id)]
        if occ.detail:
            parts.append(occ.detail)
        if occ.employment_form:
            parts.append(occ.employment_form)
        lines.append("직업: " + " · ".join(p for p in parts if p))
    if "marital_status" in fields and extended.marital_status:
        lines.append(f"혼인 상태: {extended.marital_status}")
    if "children" in fields and extended.children and extended.children.count:
        lines.append(f"자녀: {extended.children.count}명")
    if "residence" in fields and extended.residence and extended.residence.region:
        lines.append(f"거주지: {extended.residence.region}")
    return lines


def profile_facts_for(subject_id: str | None, domain: str | None) -> list[str]:
    """저장된 subject 프로필 → 도메인 맞춤 사실 맥락 줄. 실패·부재·무DB는 조용히 [](규칙11)."""
    if not subject_id:
        return []
    import contextlib

    from .profile_store import ProfileStore  # 지연 임포트 — DB 의존을 모듈 로드와 분리

    with contextlib.suppress(Exception):
        profile = ProfileStore().load(subject_id)
        if profile is not None:
            return profile_facts_lines(profile.extended, domain)
    return []
