"""연운 시대 기운 분석 (v2.2, 2026-06-16).

그 해 간지의 오행·음양·계절·왕상으로 '올해는 어떤 기운의 해인가'를 명리로만 캐릭터화한다.
개인 사주와 무관한 사회 기운 맥락이며, **경제·시장·채용 예측은 포함하지 않는다**. 키워드는 오행
통설(시작·성장/드러남·확산/중재·정리/결실·구조/응축·저장)이며 단정·예언이 아니다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.era_energy import EraEnergyProfile

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

_YANG_STEMS = {"甲", "丙", "戊", "庚", "壬"}
# 지지 → 계절.
_BRANCH_SEASON = {
    "寅": "봄", "卯": "봄", "辰": "환절기", "巳": "여름", "午": "여름", "未": "환절기",
    "申": "가을", "酉": "가을", "戌": "환절기", "亥": "겨울", "子": "겨울", "丑": "환절기",
}
# 오행 통설 키워드(사회 기운 톤 — 단정 아님).
_ELEMENT_KEYWORDS = {
    "木": ["시작", "성장", "기획·확장"],
    "火": ["드러남", "확산·표현", "개인화"],
    "土": ["중재", "전환·정리", "안정"],
    "金": ["결실", "구조화·정리", "경쟁"],
    "水": ["응축", "저장·잠복", "내면·지혜"],
}
# 음양 전환 지지 — 午(하지: 양극→음생), 子(동지: 음극→양생). (label, 서술구).
_YINYANG_TURN = {
    "午": ("양→음 교차", "양에서 음으로 전환되는 교차의 해(하지 무렵)"),
    "子": ("음→양 교차", "음에서 양으로 전환되는 교차의 해(동지 무렵)"),
}


def era_energy_profile(stem: str, branch: str) -> EraEnergyProfile:
    """세운 간지(천간·지지) → 그 해의 명리 기운 캐릭터(개인 무관, 경제 예측 무관).

    Args:
        stem: 세운 천간(한자). branch: 세운 지지(한자).

    Returns:
        EraEnergyProfile — 오행·계절·음양·키워드·요약.
    """
    s_el = str(STEM_ELEMENT[Stem(stem)])
    b_el = str(BRANCH_ELEMENT[Branch(branch)])
    season = _BRANCH_SEASON.get(branch, "환절기")
    dominant = b_el  # 사회 기운의 중심은 계절(지지) 오행
    stem_yy = "양" if stem in _YANG_STEMS else "음"
    turn_label, turn_phrase = _YINYANG_TURN.get(branch, ("", ""))
    yinyang = turn_label or stem_yy
    keywords = list(dict.fromkeys(_ELEMENT_KEYWORDS.get(dominant, [])
                                  + _ELEMENT_KEYWORDS.get(s_el, [])))[:4]

    same = " 기운이 천간·지지로 겹쳐 강한 해" if s_el == b_el else "기운이 중심인 해"
    turn = f" {turn_phrase}." if turn_phrase else ""
    summary = (
        f"{stem}{branch}年 — {season} {dominant}{same}.{turn} "
        f"명리 통설로는 {'·'.join(keywords)}의 기운(개인·경제 단정 아님)."
    )
    return EraEnergyProfile(
        year_ganji=f"{stem}{branch}",
        stem_element=s_el,
        branch_element=b_el,
        dominant_element=dominant,
        season=season,
        yinyang=yinyang,
        keywords=keywords,
        summary=summary,
    )


def era_curated_note(
    year: int, ganji: str = "", dictionaries_dir: Path = _DICTS_DEFAULT
) -> str:
    """운영자 큐레이션 시대 노트(era_notes.json) — 그 해 사회 맥락(검수 하 수기, 참고용).

    연도(예: '2026') 또는 간지(예: '丙午') 키로 조회. 없으면 빈 문자열(명리 기운만 표시).
    자동 예측이 아니라 운영자가 입력한 통제된 노트다(2026-06-16 사용자 확정 — 옵션 1).
    """
    path = dictionaries_dir / "era_notes.json"
    if not path.exists():
        return ""
    items = json.loads(path.read_text("utf-8")).get("items", {})
    return items.get(str(year)) or items.get(ganji, "")
