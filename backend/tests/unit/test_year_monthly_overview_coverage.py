"""연도 월별 요약 — 대상 연도 12개월 전체 커버(미계산 달이 '입춘 전'으로 새지 않도록).

실로그: '2027 이직운 월별'에서 2027-01만 데이터가 있고 2027-02~12가 모두 '입춘 전 — 전년 세운
구간(월운 정보 없음)'으로 표기됨. 원인은 monthly_luck에 그 해 한 달(2027-01)만 있어도 커버로
오판해 나머지 달의 월운을 온디맨드 계산하지 않던 것(2026-07-01 데굴님 지적).
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

# 乙丑년 庚辰월 丁亥일 戊申시(실로그 명식).
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1985-04-18", birth_time="16:00",
    birth_place_name="서울", gender="male",
)
_TODAY = date(2026, 7, 1)


def _overview_lines(question: str) -> list[str]:
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    pp = res.prompt_preview or ""
    out: list[str] = []
    inblock = False
    for ln in pp.splitlines():
        if "[월별 요약" in ln:
            inblock = True
            continue
        if inblock:
            if ln.startswith("(표 읽는"):
                break
            if ln.strip():
                out.append(ln.strip())
    return out


def test_future_year_all_12_months_covered() -> None:
    lines = _overview_lines("2027년 이직운은 어때? 월별로 알려줘")
    # 2027-01~2027-12 모든 달이 간지로 채워지고, '입춘 전(월운 정보 없음)' 미발생.
    for m in range(1, 13):
        prefix = f"2027-{m:02d}"
        row = next((x for x in lines if x.startswith(prefix)), None)
        assert row is not None, f"{prefix} 행 없음"
        assert "입춘 전" not in row, f"{prefix} 이 '입춘 전'으로 표기됨: {row}"
        # 간지 2글자가 라벨 뒤에 온다(예: '2027-02 壬寅 …').
        assert len(row) > len(prefix) + 2 and not row[len(prefix):].strip().startswith(":")
