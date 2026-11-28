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
#: 장면 필드 전체(장면·대하는 법·놀림)를 저작한 항목 — 귀인 4종 + 황은대사(P1-1), 현침(P1-2 보강).
#: 사고지·이동지·도화(P1-3)는 장면·놀림만 있어 test_clash_scenes_… 가 따로 본다.
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


def test_legacy_sinsal_excerpt_text_is_unchanged_by_scene_fields() -> None:
    """종전 신살 발췌(kind=sinsal)는 뜻·발현·양면 문구 그대로다 — 장면은 kind=scene 발췌로 간다."""
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


def test_group_trait_excerpt_keeps_two_faces_only() -> None:
    """십성다자 발췌(kind=ten_god_group)는 종전 두 얼굴·촉발 조건만 싣는다(장면은 scene_vocab)."""
    from saju_engines import chart_interpretation as ci

    source = Path(ci.__file__).read_text("utf-8")
    for key in ("scenesAbsent", "scenes_absent", "teaseAbsent", "adviceAbsent", '"parting"'):
        assert key not in source, key


# ── 4. P1-3 일간·지지·신강/신약, P1-4 공망 궁위(2026-11-28 3차) ─────────────────


def test_stem_scenes_cover_all_ten_and_branches_only_where_authored() -> None:
    data = json.loads((_INTERP / "stems_branches_text.json").read_text("utf-8"))
    for stem in data["stems"]:
        assert 2 <= len(stem["scenes"]) <= 3 and stem["howToTreat"] and stem["tease"], stem["char"]
        assert stem["imagery"] and stem["narrative"]  # 물상 칸은 그대로
    authored = {b["char"] for b in data["branches"] if "scenes" in b}
    assert authored == {"酉", "辰", "未"}
    # 반례: 외모 단정 소재는 놀림으로도 싣지 않는다(己 — 눈 크기).
    gi = next(s for s in data["stems"] if s["char"] == "己")
    assert "눈이 작" not in json.dumps(gi, ensure_ascii=False)
    assert set(data["elementTeases"]) == {"水"}


def test_strength_traits_cover_seven_bands_once() -> None:
    from saju_engines.dictionaries import StrengthTraitsFile, _lint_strength_traits

    raw = json.loads((_INTERP / "strength_traits.json").read_text("utf-8"))
    assert _lint_strength_traits(StrengthTraitsFile.model_validate(raw)) == []
    bands = [b for it in raw["items"] for b in it["bands"]]
    assert sorted(bands) == sorted(
        ["태신약", "신약", "중화신약", "중화", "중화신강", "신강", "태신강"]
    )
    by = {it["side"]: it for it in raw["items"]}
    assert by["weak"]["contrast"] and by["strong"]["contrast"]
    # 반례: 등급이 빠지거나 겹치면 lint 가 잡는다. 분류어(애착 유형)는 쓰지 못한다.
    by["weak"]["bands"].remove("태신약")
    assert any("7단계" in e for e in _lint_strength_traits(StrengthTraitsFile.model_validate(raw)))
    by["weak"]["bands"].append("태신약")
    by["weak"]["scenes"][0] = "막히면 피하는 회피형에 가까운 편이라 돌아가는 길을 찾는다."
    errors = _lint_strength_traits(StrengthTraitsFile.model_validate(raw))
    assert any("진단명 '회피형'" in e for e in errors)


def test_void_general_and_palaces_exclude_day_pillar() -> None:
    from saju_engines.dictionaries import VoidTenGodTextFile, _lint_void_ten_god_text

    raw = json.loads((_INTERP / "void_ten_god_text.json").read_text("utf-8"))
    assert _lint_void_ten_god_text(VoidTenGodTextFile.model_validate(raw)) == []
    assert raw["general"]["text"] and raw["general"]["advice"]
    assert sorted(p["palace"] for p in raw["palaces"]) == ["hour", "month", "year"]
    assert len(raw["items"]) == 10  # 십성별 문구는 그대로
    # 측정 없는 통계 주장은 싣지 않는다.
    blob = json.dumps(raw["palaces"], ensure_ascii=False)
    for bad in ("연예인", "대표가 많", "정치인", "CEO"):
        assert bad not in blob, bad
    # 반례: 궁위가 빠지면 lint 가 잡는다.
    raw["palaces"] = raw["palaces"][:2]
    assert any(
        "year·month·hour" in e
        for e in _lint_void_ten_god_text(VoidTenGodTextFile.model_validate(raw))
    )


def test_clash_scenes_dohwa_absent_note_and_marker_scenes() -> None:
    rel = json.loads((_INTERP / "relations_text.json").read_text("utf-8"))
    by = {it["name"]: it for it in rel["items"]}
    for name in ("자오충", "묘유충", "진술충"):
        assert len(by[name]["scenes"]) == 1 and by[name]["natalTrait"], name
    assert "scenes" not in by["인신충"]  # 반례: 저작하지 않은 쌍
    dohwa = json.loads((_INTERP / "dohwa_text.json").read_text("utf-8"))
    assert "끄는 힘이 없다는 뜻이 아니다" in dohwa["absentNote"]
    assert len(dohwa["types"]) == 4 and len(dohwa["combos"]) == 5
    sinsal = _items()
    for name in ("사고지", "이동지", "도화"):
        assert sinsal[name]["scenes"] and sinsal[name]["tease"], name


# ── 5. P2 배선·P3 계약(2026-11-28 4차) ───────────────────────────────────────────


def _result(birth_date: str, birth_time: str | None):  # type: ignore[no-untyped-def]
    from saju_api.services.manse_service import calculate
    from saju_shared_types.birth_input import BirthInput

    return calculate(BirthInput(
        birth_date=birth_date, birth_time=birth_time, birth_place_name="서울", gender="female",
        reference_date="2026-11-28",
    ))


def _scene_keys(result: object) -> list[str]:
    from saju_engines.chart_interpretation import build_chart_interpretation
    from saju_engines.scene_vocab import SCENE_KIND

    interp = build_chart_interpretation(result)  # type: ignore[arg-type]
    assert interp is not None
    return [e.key for e in interp.excerpts if e.kind == SCENE_KIND]


def test_scene_excerpts_follow_engine_judgments() -> None:
    from saju_engines.chart_interpretation import build_chart_interpretation
    from saju_engines.love_type import group_visible_counts
    from saju_engines.scene_vocab import MAX_SCENE_EXCERPTS, SCENE_KIND

    r = _result("1990-06-15", "18:10")  # 庚午 壬午 辛亥 丁酉 — 신약, 관성 3글자, 재성·인성 표면 0
    counts = group_visible_counts(r)
    keys = _scene_keys(r)
    assert keys[0] == f"일간 {r.pillars.day.stem} 장면"
    assert any(k.startswith("신약 쪽") for k in keys)
    assert f"관성 많음({counts['관성']}글자) 장면" in keys
    for group, n in counts.items():
        # 반례: 3글자 미만인 군은 '많음' 장면이 없고, 1글자 이상이면 '표면에 없음' 장면이 없다.
        assert (f"{group} 많음({n}글자) 장면" in keys) == (n >= 3 and group == "관성"), group
        if n > 0:
            assert not any(k.startswith(f"{group} 표면에 없음") for k in keys), group
    assert any(k.startswith("나란히 보기 — ") for k in keys)
    assert len(keys) <= MAX_SCENE_EXCERPTS
    # 장면 발췌는 명식 해석 자료의 맨 뒤다(토큰 가드가 먼저 덜어 낸다).
    interp = build_chart_interpretation(r)
    kinds = [e.kind for e in interp.excerpts]
    first = kinds.index(SCENE_KIND)
    assert all(k == SCENE_KIND for k in kinds[first:])


def test_scene_excerpts_respect_hour_unknown() -> None:
    r = _result("1973-05-20", None)  # 시주 미상 — 강약 등급 미확정
    assert "strength_band" in r.hour_unknown.unconfirmed
    keys = _scene_keys(r)
    assert keys and keys[0].startswith("일간 ")
    assert not any("신강 쪽" in k or "신약 쪽" in k or k.startswith("중화") for k in keys)
    assert not any("표면에 없음" in k for k in keys)  # 미상≠없음
    assert not any(k.startswith("공망 시주") for k in keys)


def test_scene_flag_off_restores_previous_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from saju_engines import period_v2_config
    from saju_engines.chart_interpretation import build_chart_interpretation
    from saju_engines.context_reducer import build_birth_summary, serialize_chart_prefix
    from saju_engines.scene_vocab import SCENE_VOCAB_USE_RULE

    r = _result("1990-06-15", "18:10")
    _scene_keys_on = _scene_keys(r)
    summary = build_birth_summary(r)
    on = serialize_chart_prefix(summary, build_chart_interpretation(r))
    assert on.count(SCENE_VOCAB_USE_RULE) == 1  # 사용 규칙은 장면 줄 앞에 한 번
    first_scene = next(
        i for i, line in enumerate(on) if line.startswith("일간 ") and " 장면: " in line
    )
    assert on.index(SCENE_VOCAB_USE_RULE) == first_scene - 1
    monkeypatch.setattr(period_v2_config, "SCENE_VOCAB_ENABLED", False)
    off = serialize_chart_prefix(summary, build_chart_interpretation(r))
    assert SCENE_VOCAB_USE_RULE not in off and not any(" 장면: " in line for line in off)
    # 플래그를 끄면 장면 줄과 사용 규칙만 빠지고 나머지 줄은 그대로다.
    added = [line for line in on if line not in off]
    assert added[0] == SCENE_VOCAB_USE_RULE and len(added) == 1 + len(_scene_keys_on)
    assert [line for line in off if line not in on] == []


def test_contrast_scene_grammar_and_lint() -> None:
    from saju_engines.dictionaries import ContrastScenesFile, _lint_contrast_scenes

    raw = json.loads((_INTERP / "contrast_scenes.json").read_text("utf-8"))
    assert _lint_contrast_scenes(ContrastScenesFile.model_validate(raw)) == []
    raw["items"][0]["reactions"][0]["when"] = "group:관성:many"
    raw["items"][1]["reactions"][1]["when"] = raw["items"][1]["reactions"][0]["when"]
    errors = _lint_contrast_scenes(ContrastScenesFile.model_validate(raw))
    assert any("when 문법 오류 — group:관성:many" in e for e in errors)
    assert any("같은 when 이 중복" in e for e in errors)


def test_on_off_audit_flags_only_negated_sentences() -> None:
    from saju_engines.scene_vocab import find_on_off_claims

    text = (
        "문창귀인이 있지만 충을 맞아 쓸 수 없어요. 월덕귀인은 공망이라 힘을 잃어요.\n"
        "귀인은 충이 있어도 두 기질이 번갈아 나와요. 올해는 이직이 거론될 수 있어요. "
        "쓸 수 없는 물건은 버리는 편이 좋아요."
    )
    hits = find_on_off_claims(text)
    assert hits == ["문창귀인이 있지만 충을 맞아 쓸 수 없어요.", "월덕귀인은 공망이라 힘을 잃어요."]
    assert find_on_off_claims("") == []


def test_felt_chain_directive_keeps_grade_and_orders_cause_effect() -> None:
    from saju_engines.structural_context import LUCK_FELT_CHAIN_DIRECTIVE as d

    # 기신 쪽: 방향이 안 보임 → 편함 → 유입 없음 → 축적분으로 버팀 → 부담 순서.
    steps = ("당장은 몸이", "새로 들어오는 것이 없다", "쌓아 둔 것으로", "부담이 된다")
    order = [d.index(w) for w in steps]
    assert order == sorted(order)
    assert "엔진 판정만 따른다" in d and "뒤집어 판정하지 말 것" in d


def test_sinsal_glossary_endpoint_hides_hidden_names() -> None:
    from fastapi.testclient import TestClient

    from saju_api.main import app

    res = TestClient(app).get("/api/v2/manse/sinsal-glossary")
    assert res.status_code == 200
    data = res.json()
    assert data["암록"]["scenes"] and data["암록"]["tease"] and data["암록"]["mechanism"]
    assert data["천을귀인"]["scenes"] == [] and data["천을귀인"]["meaning"]  # 장면 미저작 항목
    assert not set(data) & cat.HIDDEN_NAMES  # 반례: 숨김 신살은 싣지 않는다
