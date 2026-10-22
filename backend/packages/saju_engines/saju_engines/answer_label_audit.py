"""답변 본문의 내부 표기 결정론 교정·관측 — EMPLOYMENT_HISTORY_CALIBRATION.md §4-2 (2026-10-22).

실답(thread web-mvjij2wx) 누수 두 가지를 재호출 없이 고친다.
- 순위 표기: 프롬프트의 창 내 상대 순위('상위 3위')를 본문이 "성취 신호가 1위로 나타나지만"처럼
  옮겼다 → '가장 강하게 / 두 번째로 / 세 번째로'로 바꾼다. 1~3위만 다루고, 숫자·간지는 건드리지
  않는다.
- 기간 라벨 원문: 후보 라벨 'YYYY-MM'이 "2026-12 庚子월"처럼 그대로 나왔다 → 'YYYY년 M월'.
  날짜('2026-10-22')·범위('2026-10~2027-09')는 건드리지 않는다.
관측: 진입 시기 두 칸 지시가 붙은 답의 첫 문단에 '성사 달'·'움직이는 달'이 모두 있는가(로그 전용).
순수 함수.
"""

from __future__ import annotations

import re

_RANK_ADV = {"1": "가장 강하게", "2": "두 번째로", "3": "세 번째로"}
_RANK_ADJ = {"1": "가장 강한", "2": "두 번째로 강한", "3": "세 번째로 강한"}
# 'N위' + 조사. 앞이 숫자·가운뎃점이면(예: '2·3위', '10위') 제외.
_RANK_RE = re.compile(r"(?<![\d·])([1-3])위(로|인|의|에서|에|는|은|가|이)?(?![\d])")
# 'YYYY-MM' 단독(뒤에 '-DD'·'~'가 붙는 날짜·범위 제외, 앞이 숫자·'~'·'-'면 제외). 라벨 뒤에 모델이
# 붙인 '월'은 같이 삼킨다 — 실답(2026-10-22 web-mvjm3vcc) '2026-11월' → '2026년 11월월' 교정.
_RAW_PERIOD_RE = re.compile(r"(?<![\d~\-])(19|20)(\d{2})-(0[1-9]|1[0-2])(월)?(?![\d\-~])")
# 앞자리 0이 붙은 달('05월') — 날짜·라벨 일부가 아닌 단독 표기만 '5월'로.
_ZERO_MONTH_RE = re.compile(r"(?<![\d\-])0([1-9])월")
_RELATIVE_YEAR_RE = re.compile(r"내후년|내년|올해|작년")
_FIRST_PARA_SPLIT = re.compile(r"\n\s*\n")


def rewrite_rank_labels(text: str) -> tuple[str, list[tuple[str, str]]]:
    """'1위로 나타나' → '가장 강하게 나타나', '2위인 달' → '두 번째로 강한 달' 등.

    Returns:
        (본문, 변경 목록).
    """
    changes: list[tuple[str, str]] = []

    def _sub(m: re.Match[str]) -> str:
        n, particle = m.group(1), m.group(2) or ""
        if particle == "로":
            out = _RANK_ADV[n]
        elif particle in ("인", "의"):
            out = _RANK_ADJ[n]
        else:
            out = f"{_RANK_ADJ[n]} 신호{particle}"
        changes.append((m.group(0), out))
        return out

    return _RANK_RE.sub(_sub, text), changes


def rewrite_raw_period_labels(text: str) -> tuple[str, list[tuple[str, str]]]:
    """'2026-12' → '2026년 12월'(날짜·범위 제외). (본문, 변경 목록)."""
    changes: list[tuple[str, str]] = []

    def _sub(m: re.Match[str]) -> str:
        out = f"{m.group(1)}{m.group(2)}년 {int(m.group(3))}월"
        changes.append((m.group(0), out))
        return out

    out = _RAW_PERIOD_RE.sub(_sub, text)
    out, n_zero = _ZERO_MONTH_RE.subn(lambda m: f"{m.group(1)}월", out)
    if n_zero:
        changes.append(("0M월", f"{n_zero}건"))
    if "월월" in out:  # 방어 — 어떤 경로로든 겹친 '월월'은 한 글자로.
        changes.append(("월월", "월"))
        out = out.replace("월월", "월")
    return out, changes


def relative_year_mentions(text: str) -> list[str]:
    """'내년·내후년·올해·작년' 상대 연도 표현 목록(중복 포함) — 로그 전용 관측.

    실답(2026-10-22 web-mvjm3vcc): 2027년 2월·5월 후보를 두고 "내년 하반기부터 준비해 내후년
    상반기에 결론"이라 적어 한 해가 밀렸다. 결정론으로 고치면 숫자만 바뀌고 뜻은 그대로 틀리므로,
    지시문으로 숫자 연도를 요구하고 발생만 센다.
    """
    return _RELATIVE_YEAR_RE.findall(text or "")


_DONE_STEM_RE = re.compile(r"성사")
_MOVE_STEM_RE = re.compile(r"움직이|움직여|움직임")


def entry_window_labels_present(text: str) -> tuple[bool, bool]:
    """첫 문단에 (성사 칸 어간, 움직이는 칸 어간)이 있는가 — 두 칸 지시 준수 관측(로그 전용).

    실답(2026-10-22 web-mvjjpmvz)은 "성사 기운이 뚜렷한 달 … 미리 움직이며"로 의미는 지켰으나
    '성사 달·움직이는 달' 정확 표기는 없었다 — 관측은 어간 기준, 정확 표기는 지시문이 계속 요구한다.
    """
    first = _FIRST_PARA_SPLIT.split(text.strip(), maxsplit=1)[0] if text else ""
    return (bool(_DONE_STEM_RE.search(first)), bool(_MOVE_STEM_RE.search(first)))
