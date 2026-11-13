"""여러 달 기간 질문에 '운에서 서는 구조'·운 신살이 실린다(2026-11-13 데굴님 실답).

실답: "11월부터 1월까지의 취업운" 뒤 "도움되는 신살의 발동이나 구조는 없어?" — 입력에 원국 신살·
원국 구조와 방위표만 있고, 운에서 서는 구조와 그 달에 들어오는 신살은 전혀 실리지 않았다.
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from saju_api.services import chat_service
from saju_api.services.manse_service import pattern_timeline
from saju_engines.pattern_transit import window_structure_lines
from saju_shared_types.birth_input import BirthInput

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울", gender="male",
)
_WINDOW = ["2026-11", "2026-12", "2027-01"]


def _rows(labels):
    return [SimpleNamespace(period=lb) for lb in labels]


def test_window_structure_lines_follow_the_manse_timeline() -> None:
    tl = pattern_timeline(_BIRTH, 2026)
    lines = window_structure_lines([tl], _WINDOW)
    # 대운·세운 줄 + 달 3줄. 1월 라벨(2027-01)은 2026년 절기 타임라인에 속한다.
    assert lines[0].startswith(f"대운 {tl.daewoon_ganji}(원국 대비 — 이 기간의 큰 배경): ")
    assert lines[1].startswith(f"세운 {tl.year_ganji} 2026년(대운 대비): ")
    # 달 줄은 '월운'으로 시작한다(월 라벨로 시작하면 월별 요약 표의 행과 같은 모양이 된다).
    assert [ln.split(" ")[:2] for ln in lines[2:]] == [["월운", lb] for lb in _WINDOW]
    # 칸 값은 만세력 화면과 같다 — 타임라인 행의 그 달 칸에서 변동 있는 것만.
    i = tl.month_labels.index("2026-12")
    expected = [f"{r.name_ko} {r.months[i].label}" for r in tl.rows
                if r.months[i] is not None and r.months[i].status != "unchanged"]
    assert expected, "반례 없음: 12월에 변동이 하나도 없으면 줄 검증이 되지 않는다"
    assert lines[3].endswith(": " + " · ".join(expected))
    # 반례: 타임라인에 없는 달은 건너뛰고, 걸친 달이 없으면 대운·세운 줄도 내지 않는다.
    assert window_structure_lines([tl], ["2028-05"]) == []


def test_window_block_added_for_month_windows_only() -> None:
    block = chat_service._window_structure_block(_BIRTH, _rows(_WINDOW), "취업운 정리해줘")
    assert block is not None and block.startswith("[운에서 서는 구조 — 2026-11–2027-01")
    assert "월운 2027-01 辛丑(세운 대비)" in block
    assert not any(ln[:7] in _WINDOW for ln in block.splitlines())
    assert "[운 신살" not in block  # 신살을 묻지 않으면 신살 줄은 싣지 않는다
    # 13개월 이상 표는 앞 12개월까지만 싣는다(블록을 통째로 빼지 않는다).
    long = [f"2026-{m:02d}" for m in range(2, 13)] + ["2027-01", "2027-02"]
    capped = chat_service._window_structure_block(_BIRTH, _rows(long), "q")
    assert capped is not None and "월운 2027-01 " in capped and "월운 2027-02 " not in capped
    # 반례: 기간이 없으면 싣지 않는다.
    assert chat_service._window_structure_block(_BIRTH, [], "q") is None


def test_window_block_uses_year_lines_for_multi_year_questions() -> None:
    # 여러 해 질문 — 요약 표가 앞 12개월뿐이어도 질문 범위의 해마다 세운 줄을 싣는다.
    months = [f"2027-{m:02d}" for m in range(1, 13)]
    rng = SimpleNamespace(start="2027", end="2030")
    block = chat_service._window_structure_block(_BIRTH, _rows(months), "재물운 흐름", rng)
    assert block is not None
    for year, ganji in ((2027, "丁未"), (2028, "戊申"), (2029, "己酉"), (2030, "庚戌")):
        assert f"세운 {ganji} {year}년(대운 대비): " in block
    # 같은 대운 줄은 한 번만 — 그 대운이 덮는 해를 '큰 배경'으로 밝힌다(2027-01 은 2026년 절기).
    assert block.count("대운 壬辰(원국 대비 — 2026~2030년의 큰 배경): ") == 1
    assert "대운 줄이 가장 큰 배경 흐름" in block  # 층의 크기 지시
    # 대운 줄이 세운·월운 줄보다 먼저 온다.
    body = block.splitlines()[1:]
    assert body[0].startswith("대운 ") and any(ln.startswith("세운 ") for ln in body[1:])
    # 연 단위 표(행이 해)도 세운 줄로 싣는다.
    yearly = chat_service._window_structure_block(_BIRTH, _rows(["2028", "2029"]), "q")
    assert yearly is not None and "세운 戊申 2028년" in yearly and "월운 " not in yearly
    # 반례: 해를 걸친 짧은 범위(11월~1월)에는 다음 해 세운 줄을 붙이지 않는다.
    short = chat_service._window_structure_block(
        _BIRTH, _rows(_WINDOW), "취업운", SimpleNamespace(start="2026-11", end="2027-01")
    )
    assert short is not None and "세운 丁未 2027년" not in short
    # 신살을 물으면 해마다 세운 신살 줄도 — 도움만이 아니라 주의도 함께 싣는다.
    asked = chat_service._window_structure_block(
        _BIRTH, _rows(["2028", "2029"]), "도움되는 신살 있어?"
    )
    line = next(ln for ln in asked.splitlines() if ln.startswith("세운 2028년 戊申 신살: "))
    assert "도움 — " in line and "주의 — " in line


def test_window_block_adds_luck_sinsal_when_asked() -> None:
    block = chat_service._window_structure_block(
        _BIRTH, _rows(_WINDOW), "도움되는 신살의 발동이나 구조는 없어?"
    )
    assert block is not None and "[운 신살 — 2026-11–2027-01" in block
    # 己 일간의 천을귀인은 子·申 — 庚子월(2026-12)에 '도움' 신살로 실린다.
    line = next(ln for ln in block.splitlines() if ln.startswith("월운 2026-12 庚子 신살: "))
    assert "도움 — " in line and "천을귀인" in line


def test_window_block_skipped_when_hour_unknown() -> None:
    unknown = BirthInput(
        birth_date=date(1980, 11, 22), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="male",
    )
    # 시주 미상은 세력 기반 구조 상태를 산출하지 않는다(정책) — 블록도 없다.
    assert chat_service._window_structure_block(unknown, _rows(_WINDOW), "구조는?") is None


def test_daewoon_change_inside_window_gets_its_own_backdrop_line() -> None:
    # 2026~2036년 — 중간에 대운이 壬辰 → 癸巳 로 바뀐다. 대운마다 덮는 해와 함께 한 줄씩.
    block = chat_service._window_structure_block(
        _BIRTH, [], "재물운 흐름", SimpleNamespace(start="2026-11", end="2036-10")
    )
    assert block is not None
    # 구조 줄의 대운 머리만 본다(창고 블록의 대운 줄은 '(원국 대비'가 없다).
    heads = [
        ln.split(": ")[0] for ln in block.splitlines()
        if ln.startswith("대운 ") and "(원국 대비" in ln
    ]
    assert heads == [
        "대운 壬辰(원국 대비 — 2026~2034년의 큰 배경)",
        "대운 癸巳(원국 대비 — 2035~2036년의 큰 배경)",
    ]


def test_theme_report_block_carries_daewoon_backdrop() -> None:
    # 테마 리포트의 [구조 변화(운)] 블록에도 대운 배경·세운 줄이 달 줄보다 먼저 실린다.
    from saju_api.services.report_service import _ReportData, build_section_context
    from saju_engines.report_plan import build_section_plans
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    spec = ReportSpec(
        product_code="RPT_FOCUS", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="career", period=ReportPeriod(start="2026-11", end="2029-12"),
    )
    data = _ReportData(_BIRTH, spec, date(2026, 11, 13), owner_id=None, subject_id=None)
    seen = 0
    for plan in build_section_plans(spec):
        body = build_section_context(plan, spec, data).body_prompt
        i = body.find("[구조 변화(운)")
        if i < 0:
            continue
        seen += 1
        lines = body[i:].split("\n\n")[0].splitlines()
        assert lines[1].startswith("대운 ") and "큰 배경" in lines[1], plan.section_id
        assert any(ln.startswith("세운 ") for ln in lines[2:]), plan.section_id
    assert seen >= 3, "반례 없음: 구조 변화 블록이 실린 섹션이 없으면 배선이 검증되지 않는다"
    # 반례: 시주 미상 명식에는 배경 줄을 만들지 않는다.
    unknown = BirthInput(
        birth_date=date(1980, 11, 22), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="male",
    )
    data_u = _ReportData(unknown, spec, date(2026, 11, 13), owner_id=None, subject_id=None)
    assert data_u.pattern_backdrop_lines(data_u.candidates) == []


def test_full_report_decade_pages_carry_daewoon_structure_state() -> None:
    # 총운의 대운별 페이지(F-14-D*)에 그 대운의 구조 상태(대운 줄 + 그 10년의 세운 줄)가 실린다.
    from saju_api.services import report_service as rs
    from saju_engines.report_plan import build_section_plans
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    spec = ReportSpec(
        product_code="RPT_FULL", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2026-11", end="2036-12"),
    )
    data = rs._ReportData(_BIRTH, spec, date(2026, 11, 13), owner_id=None, subject_id=None)
    plans = rs._expand_report_plans(build_section_plans(spec), data)
    pages = {p.section_id: p for p in plans if p.section_id.startswith("F-14-D")}
    # 현재 대운(壬辰, 2025~2034) 페이지 — 대운 줄 1 + 세운 줄 10.
    sid = next(s_ for s_, w in data.decade_windows.items() if w[2] == "壬辰")
    body = rs.build_section_context(pages[sid], spec, data).body_prompt
    i = body.find("[이 대운의 구조 상태")
    assert i >= 0
    lines = body[i:].split("\n\n")[0].splitlines()
    assert lines[1].startswith("대운 壬辰(원국 대비 — 2025~2034년의 큰 배경): ")
    assert sum(1 for ln in lines if ln.startswith("세운 ")) == 10
    assert "재다신약 강화" in lines[1]  # 부담 쪽 변화도 그대로 싣는다
    # 반례: 명식 섹션(F-01)에는 운 층 블록이 없다.
    f01 = next(p for p in plans if p.section_id == "F-01")
    assert "[이 대운의 구조 상태" not in rs.build_section_context(f01, spec, data).body_prompt
