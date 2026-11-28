"""생활 장면 어휘 층 P1-1(2026-11-28) — 황은대사 판정과 신살 사전의 장면 필드.

근거: doc/v2_2/EXTERNAL_TEXT_GAP_CHOI_LIVE.md §4·§7. 각 검증에 반례(성립하면 안 되는 쪽)를 둔다.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from saju_manse_analysis.sinsal import sinsal_catalog as cat
from saju_manse_analysis.sinsal.sinsal_aggregator import _detect, sinsal_for_luck

from saju_engines import sinsal_modifier_config as cfg
from saju_engines.chart_interpretation import canonical_sinsal_names
from saju_engines.dictionaries import SinsalTextFile, _lint_sinsal_text
from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S

_DICT = (
    Path(__file__).resolve().parents[2] / "dictionaries" / "interpretations" / "sinsal_text.json"
)
_NAME = "황은대사"
#: 장면 필드를 저작한 항목 — 귀인 4종 + 황은대사(P1-1), 현침(P1-2 보강).
_SCENE_ITEMS = ("태극귀인", "암록", "문창귀인", "월덕귀인", _NAME, "현침")


def _pillars(year: str, month: str, day: str, hour: str | None = None) -> SimpleNamespace:
    """간지 문자열(예: '甲子')로 판정 함수가 읽는 최소 필드만 가진 원국을 만든다."""

    def pillar(gz: str) -> SimpleNamespace:
        return SimpleNamespace(stem=gz[0], branch=gz[1], ganji=gz)

    return SimpleNamespace(
        year=pillar(year), month=pillar(month), day=pillar(day),
        hour=pillar(hour) if hour else None, gongmang_branches=[],
    )


def _positions_of(pillars: SimpleNamespace, name: str) -> set[str]:
    """원국 판정에서 그 이름이 선 자리 집합."""
    return {pos for n, _cat, pos, _basis in _detect(pillars, None) if n == name}  # type: ignore[arg-type]


def _items() -> dict[str, dict]:
    return {it["name"]: it for it in json.loads(_DICT.read_text("utf-8"))["items"]}


# ── 1. 황은대사 표 — 현대 한국 자료 3곳 공통 표 ─────────────────────────────────


def test_hwangeun_table_matches_the_shared_modern_table() -> None:
    # 생월 寅~丑 순서의 황은대사 지지(역학동 조견표 표기와 같은 순서).
    order = [B.IN, B.MYO, B.JIN, B.SA, B.O, B.MI, B.SIN, B.YU, B.SUL, B.HAE, B.JA, B.CHUK]
    assert "".join(str(cat.HWANGEUN[m].value) for m in order) == "戌丑寅巳酉卯子午亥辰申未"
    assert len(cat.HWANGEUN) == 12
    # 반례: 土 지지에 한정된 표가 아니다(巳월=巳, 午월=酉).
    earth = {B.JIN, B.SUL, B.CHUK, B.MI}
    assert cat.HWANGEUN[B.SA] not in earth and cat.HWANGEUN[B.O] not in earth


def test_hwangeun_is_judged_on_day_and_hour_branch_only() -> None:
    # 午월 → 酉. 일지 酉.
    assert _positions_of(_pillars("甲子", "庚午", "丁酉", "庚子"), _NAME) == {"day"}
    # 시지 酉.
    assert _positions_of(_pillars("甲子", "庚午", "丁卯", "己酉"), _NAME) == {"hour"}
    # 일지·시지 모두 酉.
    assert _positions_of(_pillars("甲子", "庚午", "丁酉", "己酉"), _NAME) == {"day", "hour"}
    # 반례: 연지에만 酉가 있으면 성립하지 않는다.
    assert _positions_of(_pillars("癸酉", "戊午", "丁卯", "庚子"), _NAME) == set()
    # 반례: 巳월은 월지 자신(巳)과 같은 글자지만 월지 자리는 대조 대상이 아니다.
    assert _positions_of(_pillars("甲子", "己巳", "丁卯", "庚子"), _NAME) == set()
    assert _positions_of(_pillars("甲子", "己巳", "丁巳", "庚子"), _NAME) == {"day"}
    # 반례: 시주가 없으면 일지만 본다.
    assert _positions_of(_pillars("甲子", "庚午", "丁卯"), _NAME) == set()


def test_hwangeun_is_not_judged_from_luck() -> None:
    p = _pillars("甲子", "庚午", "丁卯", "庚子")  # 午월 → 酉
    for period in (None, "year", "month", "day"):
        names = {x.name for x in sinsal_for_luck(p, S.GI, B.YU, period)}  # type: ignore[arg-type]
        assert _NAME not in names


def test_hwangeun_is_visible_low_priority_and_separate_from_cheonsa() -> None:
    meta = cat.CATALOG_META[_NAME]
    assert meta["category"] == "noble_stars" and meta["polarity"] == "positive"
    assert _NAME not in cat.HIDDEN_NAMES  # 현대 자료 2곳 이상 — 표시 대상
    assert _NAME in cfg.SINSAL_PAYLOAD_LOW_PRIORITY  # 문구 감수 전 — 기존 신살을 밀어내지 않는다
    assert _NAME in canonical_sinsal_names()
    # 반례: 천사(계절×일주)와 다른 판정이다 — 午월 甲午일은 천사지만 황은대사(酉)가 아니다.
    p = _pillars("甲子", "庚午", "甲午", "甲子")
    assert _positions_of(p, "천사") == {"day"} and _positions_of(p, _NAME) == set()


# ── 2. 신살 사전 장면 필드 ───────────────────────────────────────────────────────


def test_scene_fields_are_authored_for_the_five_items() -> None:
    items = _items()
    for name in _SCENE_ITEMS:
        it = items[name]
        assert 1 <= len(it["scenes"]) <= 3, name
        assert it["howToTreat"] and it["tease"], name
        assert it["reviewed"] is False, name
    # 원리 한 줄은 성립 조건에서 참인 문장이 서는 항목에만 둔다.
    assert all("mechanism" in items[n] for n in ("암록", "문창귀인", "월덕귀인"))
    assert all("mechanism" not in items[n] for n in ("태극귀인", _NAME, "현침"))
    # 반례: 저작하지 않은 항목에는 장면 필드가 없다.
    assert not {"scenes", "mechanism", "howToTreat", "tease"} & set(items["천을귀인"])


def test_mechanism_sentences_hold_against_the_tables() -> None:
    from saju_shared_types.constants import SIX_COMBINATIONS

    # 암록 = 건록 글자의 육합.
    six = {frozenset(pair) for pair in SIX_COMBINATIONS}
    for stem, branch in cat.AMROK.items():
        assert frozenset({cat.CHEONROK[stem].value, branch.value}) in {
            frozenset(str(getattr(x, "value", x)) for x in pair) for pair in six
        }, stem
    # 문창 = 丙·丁은 戊·己와 같은 글자(사전 문장의 예외 병기 근거).
    assert cat.MUNCHANG[S.BYEONG] == cat.MUNCHANG[S.MU]
    assert cat.MUNCHANG[S.JEONG] == cat.MUNCHANG[S.GI]


def test_no_source_attribution_and_no_assertive_words_in_scene_fields() -> None:
    items = _items()
    for name in _SCENE_ITEMS:
        it = items[name]
        blob = " ".join([*it["scenes"], it.get("mechanism", ""), it["howToTreat"], it["tease"]])
        for bad in ("반드시", "무조건", "틀림없이", "확실히", "100%"):
            assert bad not in blob, (name, bad)
        # 출처(강사·채널·서비스·강의)는 장면 필드에 적지 않는다.
        for word in ("포스텔러", "초이", "라이브", "강의"):
            assert word not in blob, (name, word)
    # 이번에 추가한 항목은 근거 칸에도 출처를 적지 않는다.
    hwangeun = json.dumps(items[_NAME], ensure_ascii=False)
    assert not any(w in hwangeun for w in ("강의", "계산기"))


def test_lint_rejects_assertive_or_duplicated_scenes() -> None:
    data = json.loads(_DICT.read_text("utf-8"))
    assert _lint_sinsal_text(SinsalTextFile.model_validate(data)) == []
    by_name = {it["name"]: it for it in data["items"]}
    by_name["암록"]["tease"] = "축하 자리에서는 무조건 도망가는 쪽."
    by_name["문창귀인"]["scenes"] = [by_name["문창귀인"]["scenes"][0]] * 2
    errors = _lint_sinsal_text(SinsalTextFile.model_validate(data))
    assert any("암록 tease" in e and "무조건" in e for e in errors)
    assert any("문창귀인 scenes" in e and "중복" in e for e in errors)
    # 반례: 기존 필드(meaning 등)는 이 lint 대상이 아니다.
    data2 = json.loads(_DICT.read_text("utf-8"))
    {it["name"]: it for it in data2["items"]}["암록"]["caution"] = "무조건 믿지는 말 것."
    assert _lint_sinsal_text(SinsalTextFile.model_validate(data2)) == []


def test_scene_fields_are_not_wired_into_excerpts_yet() -> None:
    """P2 배선 전 — 신살 발췌(LLM 고정 prefix)는 종전 뜻·발현·양면 문구만 싣는다."""
    from saju_api.services.manse_service import calculate
    from saju_engines.chart_interpretation import build_chart_interpretation
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        birth_date="1990-07-15", birth_time="14:30", birth_place_name="서울", gender="female",
        reference_date="2026-11-28",
    ))
    interp = build_chart_interpretation(r)
    assert interp is not None
    text = " ".join(e.text for e in interp.excerpts if e.kind == "sinsal")
    assert text  # 발췌 자체는 있다
    for it in _items().values():
        for scene in it.get("scenes", []):
            assert scene not in text
        assert it.get("tease", "\0") not in text


# ── 3. P1-2 십성 5군·십성 개별 장면 칸(2026-11-28 2차) ───────────────────────────

_INTERP = _DICT.parent
_GROUPS = ("비겁", "식상", "재성", "관성", "인성")
_GROUP_SCENE_KEYS = (
    "scenes", "scenesAbsent", "study", "parting", "howToTreat", "tease", "teaseAbsent",
    "adviceAbsent",
)


def _group_items() -> dict[str, dict]:
    data = json.loads((_INTERP / "ten_god_group_traits.json").read_text("utf-8"))
    return {it["group"]: it for it in data["items"]}


def test_group_scene_fields_cover_all_five_groups() -> None:
    items = _group_items()
    assert set(items) == set(_GROUPS)
    for group in _GROUPS:
        it = items[group]
        assert all(it.get(k) for k in _GROUP_SCENE_KEYS), group
        assert 1 <= len(it["scenes"]) <= 3 and 1 <= len(it["scenesAbsent"]) <= 3, group
        # 있음 장면과 부재 장면은 서로 다른 문장이다.
        assert not set(it["scenes"]) & set(it["scenesAbsent"]), group
        # 종전 칸(두 얼굴·촉발 조건)은 그대로 남는다.
        assert it["faceA"] and it["faceB"] and it["trigger"], group


def test_group_scene_text_has_no_gender_or_stigma_words() -> None:
    # 성별 일반화·낙인 서술은 불채택(doc §6) — 장면 칸에 성별어·낙인 어휘가 없어야 한다.
    for group, it in _group_items().items():
        blob = " ".join(
            [*it["scenes"], *it["scenesAbsent"]] + [it[k] for k in _GROUP_SCENE_KEYS[2:]]
        )
        for bad in ("남자", "여자", "남성", "여성", "남편", "아내", "시집", "마마", "외도", "과부"):
            assert bad not in blob, (group, bad)


def test_individual_ten_god_scenes_only_where_authored() -> None:
    data = json.loads((_INTERP / "ten_gods_text.json").read_text("utf-8"))
    by = {it["tenGod"]: it for it in data["items"]}
    for name in ("정관", "편관", "상관"):
        assert by[name]["scenes"] and by[name]["howToTreat"] and by[name]["tease"], name
    # 반례: 저작하지 않은 십성에는 장면 칸이 없다.
    for name in ("비견", "겁재", "식신", "편재", "정재", "편인", "정인"):
        assert not {"scenes", "howToTreat", "tease", "mechanism"} & set(by[name]), name


def test_lint_rejects_diagnosis_names_and_stigma_in_scene_fields() -> None:
    from saju_engines.dictionaries import (
        TenGodGroupTraitsFile,
        TenGodsTextFile,
        _lint_ten_god_group_traits,
        _lint_ten_gods_text,
    )

    raw = json.loads((_INTERP / "ten_god_group_traits.json").read_text("utf-8"))
    assert _lint_ten_god_group_traits(TenGodGroupTraitsFile.model_validate(raw)) == []
    by = {it["group"]: it for it in raw["items"]}
    by["인성"]["tease"] = "잠이 부족하면 불면증이 오는 쪽."
    by["식상"]["parting"] = "마음이 식으면 바람처럼 떠나는 편이다."
    by["관성"]["scenesAbsent"] = [by["관성"]["scenes"][0]]
    errors = _lint_ten_god_group_traits(TenGodGroupTraitsFile.model_validate(raw))
    assert any("인성 tease" in e and "진단명 '불면증'" in e for e in errors)
    assert any("식상 parting" in e and "금지 어휘 '바람'" in e for e in errors)
    assert any("관성 장면 문장이 중복" in e for e in errors)

    raw2 = json.loads((_INTERP / "ten_gods_text.json").read_text("utf-8"))
    assert _lint_ten_gods_text(TenGodsTextFile.model_validate(raw2)) == []
    {it["tenGod"]: it for it in raw2["items"]}["상관"]["tease"] = "가만히 못 있는 ADHD 같은 쪽."
    errors2 = _lint_ten_gods_text(TenGodsTextFile.model_validate(raw2))
    assert any("상관 tease" in e and "진단명 'ADHD'" in e for e in errors2)

    # 신살 사전에도 같은 검사가 걸린다. 반례: 일상어 놀림("잠이 보약")은 통과한다.
    data = json.loads(_DICT.read_text("utf-8"))
    sinsal = {it["name"]: it for it in data["items"]}
    sinsal["암록"]["tease"] = "잠이 보약이라며 주말 내내 자는 쪽."
    assert _lint_sinsal_text(SinsalTextFile.model_validate(data)) == []
    sinsal["암록"]["tease"] = "사람 많은 곳에서는 공황이 오는 쪽."
    assert any("진단명 '공황'" in e for e in _lint_sinsal_text(SinsalTextFile.model_validate(data)))


def test_group_trait_excerpt_is_unchanged_before_wiring() -> None:
    """P2 배선 전 — 십성다자 발췌는 종전 두 얼굴·촉발 조건만 싣는다."""
    from saju_engines import chart_interpretation as ci

    source = Path(ci.__file__).read_text("utf-8")
    for key in ("scenesAbsent", "scenes_absent", "teaseAbsent", "adviceAbsent", '"parting"'):
        assert key not in source, key
