"""단식 문장 톤 개정(dict.v1.25) + 세운×월운 단식·테마 배선 검증 (docs/17 §38·§39, 2026-11-27).

데굴님 "이전에 개발했던 단식풀이는 테마사주에서는 활용되지 않는 느낌" → "테마사주에서는 한해운세
같이 월별 풀이를 하는 경우 세운과 월운을 함께 보는 단식도 필요" → "받아들이고 쉬는 해 같은 문장은
보다 냉정하게 '본인의 의사와는 무관한 예상치 못한 단절이나 중단' 같이 임팩트 있게 · 관련된 모든
영역에 전체적인 톤 정리".

지키는 것: ① 버전 경계(11/28 보드는 종전 문장) ② 새 문장의 텍스트 정책·형식 계약 ③ 문체 전용
(키·사건·점수 불변) ④ 세운×월운 연결의 판정(겹침/연결·丑월 관할 세운·어긋난 해는 문장 없음)
⑤ 리포트 배선(테마 연도별 상세·주목할 달·종합, 한해 상·하반기)과 새지 않아야 할 곳(원국 섹션·총운)
⑥ 채팅 월 문단의 연결 문장.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_api.services import report_service
from saju_engines import daily_ilju_fortune as M
from saju_engines import simple_reading as S
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    DICT_VERSION_BEFORE_TONE_REVISION,
    TONE_REVISION_EFFECTIVE_FROM,
    active_dict_version,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_FROM = TONE_REVISION_EFFECTIVE_FROM  # 2026-11-29
_BEFORE = _FROM - dt.timedelta(days=1)
_HANJA = re.compile(r"[一-鿿]")
_DIGITS = re.compile(r"[0-9]")
_TODAY = dt.date(2026, 11, 27)
_YEAR_MARK = "[단식 참고 — 일간×운 십성군만"
_MONTH_MARK = "[단식 참고 — 세운×월운"
_SPAN_MARK = "[단식 참고 — 여러 해 흐름"
#: 이번 개정으로 문장이 바뀐 표(키는 그대로).
_REVISED_SIMPLE = (
    "year_tone", "year_same_group", "month_same_group", "day_same_group", "strong_month",
    "season_tone", "year_phase_turn", "god_scene", "ilju_seat",
)
_REVISED_MONTH = ("year_link", "month_action")


def _layers(d: dt.date) -> tuple[dict, dict]:
    t = M.load_daily_dicts_for(d).templates
    return t["simple_layer"], t["month_layer"]


def _sentences(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    items = value.values() if isinstance(value, dict) else value
    return [s for item in items for s in _sentences(item)]  # type: ignore[attr-defined]


def _keys(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    return {k for name, v in value.items() for k in _keys(v, f"{prefix}/{name}")}


# ── 버전 경계 ───────────────────────────────────────────────────────────────


def test_version_boundary_keeps_pregenerated_board() -> None:
    assert DICT_VERSION == "dict.v1.25" and DICT_VERSION_BEFORE_TONE_REVISION == "dict.v1.24"
    assert _FROM == dt.date(2026, 11, 29)
    assert active_dict_version(_FROM) == "dict.v1.25"
    assert active_dict_version(_BEFORE) == "dict.v1.24"  # 11/28 보드는 이미 생성됐다
    new, old = _layers(_FROM)[0], _layers(_BEFORE)[0]
    assert new["year_tone"]["인성+인성"].startswith(
        "본인 의사와 무관한 예상치 못한 단절이나 중단이 찾아오는 해예요."
    )
    # 반례: 이전 계약은 종전 문장 그대로다.
    assert old["year_tone"]["인성+인성"].startswith("받아들이고 쉬는 해예요.")


# ── 사전: 키 불변·문장 계약 ─────────────────────────────────────────────────


def test_revision_changes_sentences_only() -> None:
    """키 집합은 그대로, 대상 표의 문장은 전부 바뀌고, 대상이 아닌 표는 그대로다."""
    (new_s, new_m), (old_s, old_m) = _layers(_FROM), _layers(_BEFORE)
    for name in _REVISED_SIMPLE:
        assert _keys(new_s[name]) == _keys(old_s[name]), name
        assert not set(_sentences(new_s[name])) & set(_sentences(old_s[name])), name
    for name in _REVISED_MONTH:
        assert _keys(new_m[name]) == _keys(old_m[name]), name
        assert not set(_sentences(new_m[name])) & set(_sentences(old_m[name])), name
    # 오늘 카드(§3 콘셉트)와 판정에 쓰이는 표는 손대지 않았다.
    for name in ("day_scene", "month_tone", "stem_stage", "ilju_note", "year_overlap"):
        assert new_m[name] == old_m[name], name
    for name in ("god_axes", "year_cond", "year_ilju", "luck_sinsal", "year_span"):
        assert new_s[name] == old_s[name], name
    new_t, old_t = (M.load_daily_dicts_for(d).templates for d in (_FROM, _BEFORE))
    for name in ("events", "generic", "place_phrases", "lotto_phrases", "tone_layer"):
        assert new_t[name] == old_t[name], name


def test_revised_sentences_pass_text_policy() -> None:
    simple, month = _layers(_FROM)
    meta = ("since", "decision_ref", "note", "group_axes", "god_axes")
    sentences = _sentences({k: v for k, v in simple.items() if k not in meta})
    assert len(sentences) == len(set(sentences))  # 중복 문장 없음
    fragments = set(simple["season_tone"].values())  # 수식 구절(종결어미 없음)
    # 용어 정책은 이번에 다시 쓴 표에 건다 — 조건 줄(`year_cond`)은 신강약·용희신 용어를 쓰는
    # 키로 따로 승인됐다(§31-4).
    for name in _REVISED_SIMPLE:
        for sentence in _sentences(simple[name]):
            assert not _HANJA.search(sentence), sentence
            assert not any(word in sentence for word in polish._FORBIDDEN), sentence
            assert not any(g in sentence for g in S.GROUPS), sentence  # 용어 비노출(§3)
            assert sentence in fragments or sentence.endswith("."), sentence
    for sentence in _sentences({k: month[k] for k in _REVISED_MONTH}):
        assert not any(word in sentence for word in polish._FORBIDDEN), sentence
        assert not _HANJA.search(sentence) and not _DIGITS.search(sentence), sentence


def test_revised_sentences_keep_format_contracts() -> None:
    """코드가 기대는 문장 형식 — 말머리·치환 자리·연결 문장의 두 층 병기."""
    simple, month = _layers(_FROM)
    for head, key in (("올해는 ", "year"), ("이번 달은 ", "month"), ("오늘은 ", "day")):
        assert all(v.startswith(head) for v in simple[f"{key}_same_group"].values()), key
    assert all(v.startswith("이 영향은 ") for v in simple["strong_month"].values())
    assert all(v.startswith("{month}월부터는 ") for v in simple["year_phase_turn"].values())
    assert all(v.endswith("는") for v in simple["season_tone"].values())  # '… 흐름'을 꾸미는 구절
    links = month["year_link"]
    assert len(set(links.values())) == 20
    for key, sentence in links.items():
        assert sentence.endswith("요.") and sentence.count(".") == 1, (key, sentence)  # 한 문장
        assert "올해" in sentence and "이번 달" in sentence, (key, sentence)


def test_advice_sentences_are_direct_imperatives() -> None:
    """조언은 '~해보세요'가 아니라 '~하세요'로 끊는다(톤 기준 3) — 꼬리 '서류는 꼼꼼히.'만 예외."""
    simple, month = _layers(_FROM)
    for name in ("year_tone", "strong_month", "year_phase_turn"):
        for sentence in simple[name].values():
            assert "보세요" not in sentence, (name, sentence)
            last = [s for s in sentence.split(". ") if s.endswith(("세요.", "세요"))]
            assert last, (name, sentence)  # 조언 문장이 있다
    for sentence in month["month_action"].values():
        assert sentence.endswith("세요.") and "보세요" not in sentence, sentence
    # 반례: 이전 계약은 '~해보세요' 조언이었다.
    assert "보세요" in _layers(_BEFORE)[0]["year_tone"]["인성+인성"]


def test_board_decisions_unchanged_by_tone_revision() -> None:
    """문체 전용 — 같은 날을 이전 사전으로 계산해도 사건·확률·로또·장소·헤드라인이 같다."""
    ctx = M.build_day_context(_FROM)
    new = compute_board_v2(ctx, M.load_daily_dicts_for(_FROM))
    old = compute_board_v2(ctx, M.load_daily_dicts_for(_BEFORE))
    for a, b in zip(new.fortunes, old.fortunes, strict=True):
        assert a.headline == b.headline
        assert [(e.event_key, e.probability) for e in a.events] == [
            (e.event_key, e.probability) for e in b.events
        ]
        assert a.lotto_phrase == b.lotto_phrase and a.lucky_place == b.lucky_place
    assert new.year_flow != old.year_flow  # 반례: 패널 문장은 실제로 달라졌다


# ── 세운×월운 판정 ──────────────────────────────────────────────────────────


def test_governing_year_and_year_ganji() -> None:
    assert S.governing_year("2027-01") == 2026  # 丑월은 전년도 세운의 마지막 달
    assert S.governing_year("2027-02") == 2027 and S.governing_year("2027-12") == 2027
    assert S.governing_year("2027") is None and S.governing_year("2027-13") is None
    assert (S.year_stem_of(2026), S.year_branch_of(2026)) == (Stem("丙"), Branch("午"))
    assert (S.year_stem_of(2027), S.year_branch_of(2027)) == (Stem("丁"), Branch("未"))


def test_year_month_link_follows_daily_rule() -> None:
    simple, month = _layers(_FROM)
    del simple
    dm = Stem("甲")  # 2027 丁未: 세운 천간 군 = 식상
    # 戊申월(천간 재성) — 겹침 없음 → 식상>재성 연결 문장, 지시어는 '이 해·이 달'.
    aug = S.year_month_link(dm, Stem("丁"), Stem("戊"), Branch("申"), month)
    assert aug == S.link_scoped(month["year_link"]["식상>재성"])
    assert aug is not None and "이 해" in aug and "이 달" in aug
    assert "올해" not in aug and "이번 달" not in aug
    # 丙午월(천간·지지 식상) — 세운 군과 겹침 → 겹침 문장.
    jun = S.year_month_link(dm, Stem("丁"), Stem("丙"), Branch("午"), month)
    assert jun == S.link_scoped(month["year_overlap"])
    # 반례: 그 세운의 열두 달이 아닌 간지(戊申은 丙년의 달이 아니다) → 관계를 지어내지 않는다.
    assert S.year_month_link(dm, Stem("丙"), Stem("戊"), Branch("申"), month) is None
    # 반례: 연결 표가 없는 계약(v1.21 이전)은 문장 없음.
    assert S.year_month_link(dm, Stem("丁"), Stem("戊"), Branch("申"), {}) is None


def _months_of(year: int) -> list[tuple[str, str]]:
    """그 해 양력 라벨 12개(YYYY-01 … YYYY-12)와 월운 간지 — 01 은 전년도 세운의 丑월."""
    out: list[tuple[str, str]] = []
    for y in (year - 1, year):
        for stem, branch, month_no in S.month_ganji_of_year(S.year_stem_of(y)):
            label = f"{y + 1}-01" if month_no == 1 else f"{y}-{month_no:02d}"
            if label.startswith(str(year)):
                out.append((label, stem.value + branch.value))
    return sorted(out)


def test_year_month_lines_group_links_and_tag_months() -> None:
    simple, month = _layers(_FROM)
    lines = S.year_month_simple_lines(
        "甲", _months_of(2027), axis="일", simple=simple, month_layer=month,
    )
    text = "\n".join(lines)
    # 丑월(2027-01)은 丙午 세운 아래, 나머지는 丁未 세운 아래.
    assert lines[0] == "丙午년(2026년 세운 — 다음 해 1월까지 관할) 흐름과 달의 연결:"
    assert lines[1].startswith("- 2027-01: ")
    assert "丁未년(2027년 세운) 흐름과 달의 연결:" in lines
    # 같은 연결 문장을 받는 달은 한 줄로 묶인다(두 달씩 되풀이 금지).
    assert f"- 2027-08·2027-09: {S.link_scoped(month['year_link']['식상>재성'])}" in lines
    assert f"- 2027-05·2027-06·2027-07: {S.link_scoped(month['year_overlap'])}" in lines
    assert sum(1 for ln in lines if ln.startswith("- 2027-08")) == 1 + 1  # 연결 줄 + 장면 줄
    # 달별 장면 = 월운 천간 십성의 테마 영역, 표지는 가장 강한 구간(丁년 5~7월)·간여지동 달.
    assert "달별 장면(일 영역):" in lines
    assert f"- 2027-08 戊申: {simple['god_scene']['편재']['일']}" in lines
    assert (
        f"- 2027-06 丙午 [{S.MONTH_TAG_PEAK} · {S.MONTH_TAG_SAME}]: "
        f"{simple['god_scene']['식신']['일']}"
    ) in lines
    assert f"- 2027-12 壬子 [{S.MONTH_TAG_SAME}]: " in text
    assert sum(1 for ln in lines if ln[:6] == "- 2027" and " 년" not in ln) == 12 + 6
    # 영역이 없으면 그 십성의 기본 영역(채팅 월 문단과 같은 선택).
    plain = S.year_month_simple_lines("甲", _months_of(2027), simple=simple, month_layer=month)
    assert "달별 장면:" in plain
    first = simple["god_axes"]["편재"][0]
    assert f"- 2027-08 戊申: {simple['god_scene']['편재'][first]}" in plain
    # 반례: 일간이 비었거나 십성 장면이 없는 계약이면 줄 없음.
    assert S.year_month_simple_lines("", _months_of(2027), simple=simple, month_layer=month) == []
    assert S.year_month_simple_lines("甲", _months_of(2027), simple={}, month_layer=month) == []


def test_year_month_lines_put_past_months_in_past_tense() -> None:
    simple, month = _layers(_FROM)
    lines = S.year_month_simple_lines(
        "甲", _months_of(2026), past_before="2026-11", simple=simple, month_layer=month,
    )
    oct_ = next(ln for ln in lines if ln.startswith("- 2026-10 戊戌"))
    nov = next(ln for ln in lines if ln.startswith("- 2026-11 己亥"))
    assert "수 있어요" in oct_ and "했을 수" not in nov  # 지난 달만 과거 추정형
    # 같은 연결 문장이라도 지난 달과 남은 달은 따로 묶인다(시제가 다르다).
    link = S.link_scoped(month["year_link"]["식상>재성"])
    assert f"- 2026-11: {link}" in lines
    assert any(ln.startswith("- 2026-10: ") and ln != f"- 2026-10: {link}" for ln in lines)


def test_reference_line_theme_axis_span_and_month_link() -> None:
    simple, month = _layers(_FROM)
    # 연 지평 + 테마 영역: 일반 흐름 문장 대신 그 영역의 세운 천간·지지 십성 장면.
    themed = S.simple_reference_line(
        "甲", "丁未", "year", simple, month, year=2027, axis="일", span=False,
    )
    scene = simple["god_scene"]
    assert scene["상관"]["일"] in themed and scene["정재"]["일"] in themed
    assert simple["year_tone"]["식상+재성"] not in themed
    assert "년부터 3년은" not in themed  # span=False — 여러 해 흐름은 종합 섹션이 한 번
    plain = S.simple_reference_line("甲", "丁未", "year", simple, month, year=2027)
    assert simple["year_tone"]["식상+재성"] in plain and "년부터 3년은" in plain  # 반례: 기본 호출
    # 천간·지지가 같은 십성이면 장면은 한 번만.
    same = S.simple_reference_line("戊", "戊戌", "year", simple, month, axis="돈")
    assert same.count(simple["god_scene"]["비견"]["돈"]) == 1
    # 월 지평: 관할 세운 간지를 주면 이름 문장 바로 뒤에 연결 한 문장.
    linked = S.simple_reference_line("戊", "己亥", "month", simple, month, year_ganji="丙午")
    link = S.link_scoped(month["year_link"]["인성>비겁"])
    assert f"섞인 달이에요. {link} {simple['god_scene']['겁재']['돈']}" in linked
    # 반례: 세운이 없거나 그 달의 세운이 아니면 종전 문단 그대로.
    bare = S.simple_reference_line("戊", "己亥", "month", simple, month)
    wrong = S.simple_reference_line("戊", "己亥", "month", simple, month, year_ganji="丁未")
    assert link not in bare and bare == wrong
    # 반례: 일 지평은 세운 간지를 줘도 연결 문장이 없다.
    day = S.simple_reference_line("戊", "丙戌", "day", simple, month, year_ganji="丙午")
    assert "이 해" not in day
    # 지난 달 질문은 연결 문장도 과거형.
    past = S.simple_reference_line(
        "戊", "己亥", "month", simple, month, year_ganji="丙午", past=True,
    )
    assert "돌아왔을 수 있어요" in past


# ── 리포트 배선 ─────────────────────────────────────────────────────────────

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=dt.date(1978, 1, 2), birth_time="10:00",
    birth_place_name="서울", gender="male",
)


def _bodies(code: str, topic: str | None, end: str = "2031-12-31") -> dict[str, str]:
    spec = ReportSpec(
        product_code=code, subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01-01", end=end),
    )
    return {
        c.section_id: c.body_prompt for c in report_service.plan_report(_BIRTH, spec, _TODAY)
    }


def _block(body: str, mark: str) -> str:
    """머리줄부터 그 블록의 사용 규칙 줄 앞까지."""
    start = body.index(mark)
    return body[start: body.index("사용 규칙:", start)]


@pytest.fixture(scope="module")
def career() -> dict[str, str]:
    return _bodies("RPT_FOCUS", "career")


def test_theme_year_pages_carry_year_and_month_simple(career: dict[str, str]) -> None:
    for year in range(2026, 2032):
        body = career[f"J-05-Y{year}"]
        assert body.count(_YEAR_MARK) == 1 and body.count(_MONTH_MARK) == 1, year
        year_block = _block(body, _YEAR_MARK)
        ganji = f"{S.year_stem_of(year).value}{S.year_branch_of(year).value}"
        assert f"간단히 봤을 때, {ganji}년은" in year_block, year
        assert "년부터 3년은" not in year_block, year  # 여러 해 흐름은 종합 섹션에만
        month_block = _block(body, _MONTH_MARK)
        assert "달별 장면(일 영역):" in month_block, year
        labels = set(re.findall(r"- (\d{4}-\d{2}) ", month_block))
        # 그 해 달만, 빠짐없이. 첫 해의 1월(전년도 丑월)은 운 표가 올해 입춘부터라 원래 없다.
        first = 2 if year == 2026 else 1
        assert labels == {f"{year}-{m:02d}" for m in range(first, 13)}, year
        if year > 2026:  # 丑월은 전년도 세운이 관할한다
            assert f"({year - 1}년 세운 — 다음 해 1월까지 관할)" in month_block, year
    assert "[이 해 세운] 줄의 운 품질 등급" in career["J-05-Y2027"]  # 방향 기준 보조 줄


def test_theme_summary_and_focus_sections(career: dict[str, str]) -> None:
    # 종합 섹션: 여러 해 흐름 한 문장만(연·월 단식 없음).
    j05 = career["J-05"]
    assert j05.count(_SPAN_MARK) == 1 and "년부터 3년은" in j05
    assert _YEAR_MARK not in j05 and _MONTH_MARK not in j05
    # 주목할 달: 이 섹션의 후보 달만(상한 6) — 열두 달을 다 싣지 않는다.
    j06 = _block(career["J-06"], _MONTH_MARK)
    labels = re.findall(r"- (\d{4}-\d{2}) ", j06)
    assert 1 <= len(labels) <= report_service._SIMPLE_FOCUS_MONTHS_MAX
    assert "달별 장면(일 영역):" in j06
    # 반례: 원국·성향·전략·부록 섹션에는 단식 블록이 없다.
    for sid in ("J-01", "J-02", "J-03", "J-07", "J-08"):
        body = career[sid]
        assert all(mark not in body for mark in (_YEAR_MARK, _MONTH_MARK, _SPAN_MARK)), sid
    assert all(_SPAN_MARK not in career[f"J-05-Y{y}"] for y in range(2026, 2032))


def test_theme_axis_follows_topic() -> None:
    wealth = _bodies("RPT_FOCUS", "wealth")
    assert "달별 장면(돈 영역):" in wealth["W-06-Y2027"]
    assert "달별 장면(일 영역):" not in wealth["W-06-Y2027"]
    relation = _bodies("RPT_FOCUS", "relationship")
    assert "달별 장면(연애 영역):" in relation["R-05-Y2027"]
    health = _bodies("RPT_FOCUS", "health")  # 전용 섹션 도메인이 없어 주제로 정한다
    assert "달별 장면(몸 영역):" in health["C-03-Y2027"]
    # 이사·학업은 맞는 영역이 없어 십성의 기본 영역 — 연 문단은 일반 흐름 문장.
    reloc = _bodies("RPT_FOCUS", "relocation")
    block = _block(reloc["RL-06-Y2027"], _MONTH_MARK)
    assert "달별 장면:" in block and "영역):" not in block
    simple = S._current_layers()[0]
    assert simple is not None
    assert simple["year_tone"]["식상+재성"] in _block(reloc["RL-06-Y2027"], _YEAR_MARK)
    assert reloc["RL-06"].count(_SPAN_MARK) == 1 and reloc["RL-06"].count(_MONTH_MARK) == 1


def test_year_report_half_pages_and_y04() -> None:
    year = _bodies("RPT_YEAR", None, end="2026-12-31")
    h1, h2 = _block(year["Y-05-H1"], _MONTH_MARK), _block(year["Y-05-H2"], _MONTH_MARK)
    assert set(re.findall(r"- (\d{4}-\d{2}) ", h1)) == {f"2026-{m:02d}" for m in range(2, 8)}
    assert set(re.findall(r"- (\d{4}-\d{2}) ", h2)) == {
        *(f"2026-{m:02d}" for m in range(8, 13)), "2027-01",
    }
    assert "丙午년(2026년 세운 — 다음 해 1월까지 관할)" in h2  # 한 세운의 열두 달
    assert "달별 장면:" in h1 and "영역):" not in h1
    assert _YEAR_MARK not in year["Y-05-H1"]  # 연 단식은 Y-04 가 맡는다
    # Y-04 는 종전과 같은 연 문단(일반 흐름 문장 + 여러 해 흐름).
    y04 = _block(year["Y-04"], _YEAR_MARK)
    simple = S._current_layers()[0]
    assert simple is not None
    assert simple["year_tone"]["식상+식상"] in y04 and "년부터 3년은" in y04
    assert _MONTH_MARK not in year["Y-04"]


def test_full_report_has_no_simple_blocks() -> None:
    """반례: 총운은 이번 범위가 아니다(세운 섹션을 뺀 구조 — 넣을 자리는 따로 정한다)."""
    full = _bodies("RPT_FULL", None)
    assert all(
        mark not in body for body in full.values() for mark in (_YEAR_MARK, _MONTH_MARK, _SPAN_MARK)
    )


def test_pair_theme_carries_both_subjects_month_simple() -> None:
    from saju_api.services.report_service import (
        _expand_report_plans,
        _ReportData,
        build_section_context,
    )
    from saju_engines.report_plan import build_section_plans
    from saju_shared_types.intent import InlineBirth

    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[
            SubjectRef(kind=SubjectKind.SELF, label="데굴"),
            SubjectRef(
                kind=SubjectKind.INLINE_TEMP, label="짝",
                inline_birth=InlineBirth(date="1982-03-08", time="10:00", gender="F"),
                relation_type="romance",
            ),
        ],
        topic="relationship", period=ReportPeriod(start="2026-07", end="2031-12"),
    )
    partner = BirthInput(
        calendar_type="solar", birth_date="1982-03-08", birth_time="10:00",
        birth_place_name="서울", gender="female",
    )
    data = _ReportData(
        _BIRTH, spec, _TODAY, owner_id=None, subject_id=None, partner_birth=partner,
    )
    plans = _expand_report_plans(build_section_plans(spec), data)
    plan = next(p for p in plans if p.section_id == "RP-06-Y2027")
    body = build_section_context(plan, spec, data).body_prompt
    assert body.count(_MONTH_MARK) == 2
    assert "· 본인(데굴) 기준]" in body and "· 상대(짝) 기준]" in body
    assert body.index("· 본인(데굴) 기준]") < body.index("· 상대(짝) 기준]")


# ── 채팅 월 문단 ────────────────────────────────────────────────────────────


def test_chat_month_paragraph_links_year_and_month() -> None:
    from saju_api.services.chat_service import _build_period_fortune
    from saju_shared_types.intent import Domain, Granularity, IntentJson, QueryType, TimeRange

    birth = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    )

    def _fortune(kind: str, start: str, gran: Granularity) -> str:
        intent = IntentJson(
            intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.GENERAL,
            time_range=TimeRange(type="absolute", granularity=gran, start=start, end=start),
        )
        pf = _build_period_fortune(birth, intent, _TODAY, kind)
        assert pf is not None
        return pf.simple_reading_line

    month = _fortune("monthly", "2026-11", Granularity.MONTH)
    assert month.startswith("간단히 봤을 때, 己亥월은")
    assert month.count("이 해") == 1 and "이 달" in month  # 세운×월운 연결 한 문장
    assert "올해" not in month and "이번 달" not in month
    # 반례: 연 총운 문단에는 달 연결 문장이 없다(종전 구성 그대로).
    year = _fortune("yearly", "2026", Granularity.YEAR)
    links = {S.link_scoped(v) for v in _layers(_FROM)[1]["year_link"].values()}
    assert not any(link in year for link in links)
