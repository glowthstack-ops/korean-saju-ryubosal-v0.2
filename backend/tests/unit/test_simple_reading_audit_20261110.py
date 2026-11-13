"""단식 참고 문단 점검 교정(2026-11-10) — 중복 삽입 3원인·과거형 문단·'다음 해 1월' 표기.

2026-11-09 실답 4건 중 3건에서 단식 내용이 두 번 나갔다(감사가 LLM 문단을 못 찾고 엔진 문단을
또 넣음). 원인: ① 후보 선택이 (키 개수, 유사도) 순 ② 운 간지 키가 한글 병기('戊戌(무술)월')와 불일치
③ 지난달 질문은 LLM 이 과거형으로 바꿔 첫 판정 문단에 녹여 씀. 아래 답 문단은 그 실답을 줄인 것이다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from saju_api.services import chat_service
from saju_api.services.report_service import _ReportData
from saju_engines import simple_reading as S
from saju_engines.speech_style import STYLES, has_haeyo_ending, past_sentence, restyle, to_past
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.llm_input import LlmInput, PeriodFortune
from saju_shared_types.report import ReportPeriod, ReportSpec

_DICT = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARK = chat_service.SIMPLE_READING_MARK


def _simple() -> dict:
    d = json.loads((_DICT / "daily_phrase_templates.json").read_text(encoding="utf-8"))
    return d["simple_layer"]


def _payload(line: str, label: str = "2026-10") -> LlmInput:
    pf = PeriodFortune(
        fortune_type="monthly", period_label=label, ganji="戊戌", pillar_line="-",
        simple_reading_line=line,
    )
    return LlmInput.model_construct(period_fortune=pf)


# ── ① 후보 선택: 유사도 높은 문단이 키 많은 문단에 밀리지 않는다 ─────────────────────


def test_high_similarity_paragraph_wins_over_paragraph_with_more_keys() -> None:
    """실답(己 일간 己亥월): LLM 문단 유사도 0.88·키 0개 vs '일간' 한 번 나온 재물 문단 키 1개."""
    line = S.simple_reference_line("己", "己亥", "month")
    llm_simple = (
        "나와 같은 기운인 己(기토) 비견과 재물 기운인 亥(해수)가 함께 들어오는 시기입니다. "
        "己亥(기해)월은 데굴님에게 천간 비견과 지지 정재가 섞인 달입니다. 나와 비슷한 사람이 곁에 "
        "옵니다. 동료로 삼으면 든든하고, 비교하기 시작하면 피곤해집니다. 고정 수입과 저축이 자리를 "
        "잡습니다. 들어온 돈을 나누어 모으면 불어나고, 지나치게 아끼면 기회를 놓칩니다. 다만 이 "
        "명식에서는 비견이 용신으로 작용하여 주변과 협력하는 것이 열쇠가 됩니다."
    )
    wealth = "재물 면에서는 월운의 己(기토)가 원국의 일간과 힘을 합치며 수입원을 불러오는 격입니다."
    answer = "\n\n".join(["이번 달은 유리한 흐름이 우세합니다.", llm_simple, wealth])
    fixed = chat_service._ensure_simple_reading_line(
        answer, _payload(line, "2026-11"), "t", "hapsyo",
    )
    assert fixed.count("나와 비슷한 사람이 곁에") == 1  # 중복 없음(종전: 2회)
    assert fixed.count(_MARK) == 1
    paras = fixed.split("\n\n")
    assert paras[0] == "이번 달은 유리한 흐름이 우세합니다."
    assert paras[1].startswith(_MARK) and paras[1].endswith("참고용입니다.)")
    assert "다만 이 명식에서는 비견이 용신으로" in fixed  # 개인 판정 문장은 살린다
    assert wealth in fixed


# ── ② 운 간지 키: 한글 병기 허용 ─────────────────────────────────────────────────


def test_ganji_key_matches_hangul_gloss() -> None:
    line = S.simple_reference_line("己", "戊戌", "month")
    assert chat_service._simple_paragraph_keys(line, "戊戌월은 기(己) 일간에게 비겁의 달") == 3
    glossed = "戊戌(무술)월은 기(己) 일간에게 비겁의 달"
    assert chat_service._simple_paragraph_keys(line, glossed) == 3
    # 반례: 다른 간지·다른 단위는 간지 키로 세지 않는다.
    assert chat_service._simple_paragraph_keys(line, "己亥(기해)월은 일간에게 비겁") == 2
    assert chat_service._simple_paragraph_keys(line, "戊戌(무술)년은 일간에게 비겁") == 2


def test_past_paraphrase_paragraph_is_replaced_not_duplicated() -> None:
    """실답(지난달 戊戌월): 과거형으로 풀어 쓴 둘째 문단 — 유사도는 낮아도 표지 3개로 잡힌다."""
    line = S.simple_reference_line("己", "戊戌", "month", past=True)
    llm = (
        "기(己) 일간인 데굴님에게 2026년 10월 戊戌(무술)월은 비겁의 기운이 가득했던 달이었습니다. "
        "돈이 크게 움직이거나 투자와 승부의 기회가 오기도 했겠지만, 충동적으로 지출한 부분은 다시 "
        "채우기 어려웠을 것입니다."
    )
    answer = "\n\n".join(["지난 10월은 경쟁과 조율이 따랐던 시기였습니다.", llm, "직업 면에서는 …"])
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t", "hapsyo")
    paras = fixed.split("\n\n")
    assert len(paras) == 3 and paras[1].startswith(_MARK)
    assert "비겁의 기운이 가득했던" not in fixed  # LLM 풀어 쓴 문단은 엔진 문단으로 교체
    assert "달이었습니다" in paras[1] and "움직였을 수 있습니다" in paras[1]


# ── ③ 첫 판정 문단에 녹여 쓴 경우: 판정 문장은 남긴다 ────────────────────────────


def test_first_paragraph_keeps_verdict_and_drops_only_overlap() -> None:
    line = S.simple_reference_line("己", "戊戌", "month", past=True)
    verdict = (
        "데굴님, 지난 2026년 10월 戊戌(무술)월은 나를 지지하는 기반이 두터워지면서도 누군가와 "
        "경쟁해야 하는 상황이 공존했던 시기였습니다."
    )
    overlap = (
        "이 달은 기(己) 일간에게 비겁(겁재)의 기운이 천간과 지지로 강하게 들어온 달이었습니다. "
        "돈이 크게 움직일 수 있는 흐름이었으며, 투자나 승부의 기회가 오기도 했겠지만 빌려주거나 "
        "충동적으로 지출한 재물은 돌아오기 어려웠을 것입니다."
    )
    personal = "다만 이 명식에서는 강한 토(土) 용신의 유입이 과하게 쏠렸을 것입니다."
    answer = "\n\n".join([f"{verdict} {overlap}", personal])
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t", "hapsyo")
    paras = fixed.split("\n\n")
    assert paras[0] == verdict  # 판정 문장 보존, 겹치는 두 문장만 제거
    assert paras[1].startswith(_MARK)
    assert paras[2] == personal
    assert "돈이 크게 움직일 수 있는 흐름이었으며" not in fixed


def test_first_paragraph_only_verdict_is_never_replaced() -> None:
    """반례: 첫 문단이 판정 한 문장뿐이면(표지 3개가 우연히 모여도) 그 문장은 그대로 남는다."""
    line = S.simple_reference_line("己", "戊戌", "month")
    verdict = "戊戌(무술)월은 기(己) 일간에게 비겁 기운이 강해 경쟁이 두드러지는 달입니다."
    fixed = chat_service._ensure_simple_reading_line(
        "\n\n".join([verdict, "재물은 …"]), _payload(line), "t",
    )
    paras = fixed.split("\n\n")
    assert paras[0] == verdict and paras[1].startswith(_MARK) and paras[2] == "재물은 …"


def test_unrelated_answer_still_gets_insertion() -> None:
    """반례: 단식 문단이 아예 없는 답은 종전대로 첫 문단 뒤 삽입."""
    line = S.simple_reference_line("己", "丁未", "year")
    answer = "내년은 전환점 같은 해입니다.\n\n직업과 문서 면에서 성과가 나타날 가능성이 큽니다."
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line, "2027"), "t")
    assert fixed.split("\n\n")[1] == line


# ── 과거형 문단 ──────────────────────────────────────────────────────────────


def test_past_sentence_rules() -> None:
    assert past_sentence("돈이 크게 움직여요.") == "돈이 크게 움직였을 수 있어요."
    assert past_sentence("돌아오기 어려워요.") == "돌아오기 어려웠을 수 있어요."
    assert past_sentence("다툼으로 새요.") == "다툼으로 샜을 수 있어요."
    assert past_sentence("자리를 잡아요.") == "자리를 잡았을 수 있어요."
    # 간지·구조 사실(서술격)은 추정형으로 흐리지 않는다.
    assert past_sentence("비겁의 달이에요.") == "비겁의 달이었어요."
    assert past_sentence("인성의 해예요.") == "인성의 해였어요."
    assert past_sentence("이야기가 함께 올 수 있어요.") == "이야기가 함께 올 수 있었어요."
    assert past_sentence("일로 나타나기도 해요.") == "일로 나타났을 수 있어요."
    # 권유·종결 없는 조언은 지난 기간에 싣지 않는다.
    assert past_sentence("힘을 모아보세요.") is None
    assert past_sentence("서류는 꼼꼼히.") is None
    assert to_past("돈이 크게 움직여요. 힘을 모아보세요.") == "돈이 크게 움직였을 수 있어요."


def test_past_covers_every_simple_dictionary_sentence() -> None:
    """사전 단식 문장 전부: 과거형으로 바뀌거나 권유·조언이라 빠진다 — 현재형 잔류 없음."""
    s = _simple()
    texts = [x for g in s["god_scene"].values() for x in g.values()]
    texts += list(s["strong_month"].values()) + list(s["year_tone"].values())
    texts += [v for k in ("month_same_group", "day_same_group") for v in s[k].values()]
    for text in texts:
        for sent in _SPLIT.split(text.strip()):
            got = past_sentence(sent)
            if got is None:
                assert sent.rstrip(".").endswith(("세요", "꼼꼼히")), sent
            else:
                assert re.search(r"(었어요|였어요|을 수 있어요)\.$", got), (sent, got)


@pytest.mark.parametrize("horizon", S.HORIZONS)
def test_past_reference_line_all_ganji(horizon: str) -> None:
    stems, branches = list(Stem), list(Branch)
    for dm in stems:
        for i in range(60):
            ganji = stems[i % 10].value + branches[i % 12].value
            line = S.simple_reference_line(dm.value, ganji, horizon, past=True)
            core, _, tail = line.partition(" (일간과 운의")
            assert tail == " 십성만 본 단식 풀이라 참고용이에요.)"  # 안내는 현재형 그대로
            assert "세요" not in core
            for sent in _SPLIT.split(core):
                assert re.search(r"(었어요|였어요|을 수 있어요)\.$", sent), sent
            for style in STYLES[1:]:  # 과거형도 페르소나 말투로 남김없이 바뀐다
                for sent in _SPLIT.split(restyle(line, style)):
                    assert not has_haeyo_ending(sent), (style, sent)


def test_present_reference_line_unchanged_by_default() -> None:
    """반례: past 를 주지 않으면 종전 현재형 문단 그대로."""
    line = S.simple_reference_line("己", "戊戌", "month")
    assert "달이에요" in line and "움직여요" in line and "모아보세요" in line


def test_report_yearly_block_uses_past_form_only_for_finished_year() -> None:
    """리포트 연 세운 블록(한해풀이 Y-04)도 지난 연도는 과거형 — 채팅만 고치고 놓친 입구."""
    birth = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:08:00", birth_place_name="서울",
        gender="male",
    )
    today = date(2026, 11, 10)

    def simple_line(year: int) -> str:
        spec = ReportSpec(
            product_code="RPT_YEAR", topic="general",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            period=ReportPeriod(start=f"{year}-01", end=f"{year}-12"),
        )
        block = _ReportData(birth, spec, today).yearly_sewoon_block(year)
        return next(ln for ln in block if ln.startswith("[단식 참고"))

    past = simple_line(2025)
    assert "乙巳년은" in past and "해였어요" in past and "세요" not in past
    # 반례: 올해(아직 끝나지 않은 해)·내년은 현재형 그대로(권유 문장 포함).
    for year, ganji in ((2026, "丙午"), (2027, "丁未")):
        now = simple_line(year)
        assert f"{ganji}년은" in now and "해예요" in now and "해였어요" not in now
        assert "보세요" in now


# ── '다음 해 1월' 표기 ───────────────────────────────────────────────────────


def test_months_label_marks_january_as_next_year() -> None:
    assert S.months_label([10]) == "10월"
    assert S.months_label([2, 3]) == "2·3월"
    assert S.months_label([1]) == "다음 해 1월"
    assert S.months_label([12, 1]) == "12월·다음 해 1월"


def test_panel_line_for_ox_month_year_says_next_year() -> None:
    """乙·庚년의 간여지동 달은 己丑월 하나 = 다음 해 1월(2030 庚戌 → 2031년 1월)."""
    s = _simple()
    for year_stem, year_branch in (("庚", "戌"), ("乙", "卯")):
        assert [m for m, _ in S.strong_months(Stem("己"), Stem(year_stem))] == [1]
        line = S.peak_month_line(Stem("己"), Stem(year_stem), Branch(year_branch), s)
        assert line is not None and line.startswith("다음 해 1월에는 ")
    # 반례: 2026 丙午(10월)·2028 戊申(2·3월 …)은 종전 표기 그대로.
    assert S.peak_month_line(Stem("己"), Stem("丙"), Branch("午"), s).startswith("10월에는 ")
    assert S.peak_month_line(Stem("己"), Stem("戊"), Branch("申"), s).startswith("2·3월에는 ")
