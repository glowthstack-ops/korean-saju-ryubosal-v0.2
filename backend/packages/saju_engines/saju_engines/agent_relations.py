"""관계 대상 질문 — '누가 제안을 해올까'에 운의 십성을 나와의 관계 대상으로 옮긴다.

2026-10-13 데굴님 확정.

실로그: 해고 후 대화의 마지막 질문 "누가 제안을 해올까?"에 답이 문서운·시기만 말하고 '누구인지'를
답하지 않았다. 프롬프트에는 그 기간의 십성(11월 己亥: 천간 己 비견·지지 亥 정재)이 있었지만 사람의
관계 유형으로 옮기는 근거가 없었다.

규칙(데굴님 확정):
- 근거표 `interpretations/ten_god_relations.json`(십성군 5 → 사회적 관계 / 가족 관계).
- 천간·지지 십성을 둘 다 '가능한 관계 대상'으로 나란히 보여 준다(천간=드러난 제안자 같은
  역할 분리 없음).
- 사회적 관계는 직업·일반 질문, 가족 관계는 가족·연애 질문에서만.
- 십성·역할은 엔진 값(LuckPillar 십성·용희기구한)을 그대로 쓴다 — 새 계산 없음(절대원칙 1).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem

#: '누가/누구한테서/어떤 사람이' + 제안·연락·도움·소개·추천·채용 류 — 관계 대상을 묻는 질문.
#: '누가 이길까'처럼 행위 동사가 없는 비교 질문은 해당하지 않는다.
_AGENT_RE = re.compile(
    r"(?:누가|누구(?:가|한테서|에게서|로부터|를\s*통해|한테|에게)?|어떤\s*(?:사람|쪽|곳)(?:이|에서|한테서)?"
    r"|어디(?:서|에서))\s*[^.?!\n]{0,12}?"
    r"(?:제안|연락|도와|도움|소개|추천|채용|뽑|불러|찾아|오퍼|스카우트|손\s*내밀|끌어"
    r"|결혼|만나|만날|인연|사귀|짝|배우자|연인|애인)"
)
#: 제외 — 승부·순위 비교('둘 중 누가 뽑힐까'·'누가 이길까')와 사용자가 행위 주체인 질문
#: ('내가 누구한테 연락하면'·'직원을 누구를 뽑아야'). 관계 대상 블록은 '나에게 올 사람'을 위한
#: 것이다(2026-10-14 검수).
_AGENT_EXCLUDE_RE = re.compile(
    r"(?:둘|셋|중에?)\s*누가|누가\s*(?:더|이길|이기|뽑힐|붙을|합격|당선|우승|승리|앞설)"
    r"|(?:내가|제가|나는|저는)\s*[^.?!\n]{0,8}?누구|누구를\s*(?:뽑|채용|고용|선택|골라|만나야|소개해)"
)
_GUIN = ("천을귀인", "태극귀인", "천덕귀인", "월덕귀인")
_TEN_GOD_GROUP = {
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상", "편재": "재성", "정재": "재성",
    "편관": "관성", "정관": "관성", "편인": "인성", "정인": "인성",
}
_PATH = (
    Path(__file__).resolve().parents[3] / "dictionaries" / "interpretations"
    / "ten_god_relations.json"
)


def detect_agent_question(text: str) -> bool:
    """'누가 제안을 해올까'처럼 나와의 관계 대상을 묻는 질문인가.

    승부·순위 비교와 사용자가 행위 주체인 질문은 제외한다.
    """
    t = text or ""
    return bool(_AGENT_RE.search(t)) and not _AGENT_EXCLUDE_RE.search(t)


@lru_cache(maxsize=1)
def _table() -> dict[str, dict]:
    data = json.loads(_PATH.read_text(encoding="utf-8"))
    return {item["group"]: item for item in data["items"]}


def relation_target(ten_god: str, gender: str, include_family: bool) -> str:
    """십성 1개 → 관계 대상 문구(사회적 관계 + 조건에 맞는 가족 관계). 모르는 십성이면 빈 문자열."""
    group = _TEN_GOD_GROUP.get(ten_god)
    if group is None:
        return ""
    item = _table()[group]
    text = item["social"]
    note = (item.get("socialNote") or {}).get(ten_god)
    if note:
        text += f"({ten_god}는 {note})"
    if include_family:
        fam = [
            f["label"] for f in item.get("family", [])
            if (not f.get("gender") or f["gender"] == gender)
            and (not f.get("tenGods") or ten_god in f["tenGods"])
        ]
        if fam:
            text += f" / 가족: {'·'.join(fam)}"
    return text


def agent_relation_lines(
    pillars: list[object],
    fav: dict[str, str],
    gender: str,
    include_family: bool,
    sinsal_meaning: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """사건 후보 기간의 운 기둥들 → 관계 대상 줄.

    Args:
        pillars: LuckPillar 목록(label·stem·branch·stem_ten_god·branch_ten_god·luck_sinsal).
        fav: 오행 → 용희기구한(favorability_map).
        gender: 'male'/'female'(가족 관계 성별 조건).
        include_family: 가족 관계 칸 사용 여부(가족·연애 질문만).
        sinsal_meaning: 신살명 → 뜻(귀인 신살 보조 표기용).

    Returns:
        (LLM 입력 줄 목록, 노출 키 목록).
    """
    lines: list[str] = []
    keys: list[str] = []
    for p in pillars:
        stem, branch = str(getattr(p, "stem", "")), str(getattr(p, "branch", ""))
        stg, btg = str(getattr(p, "stem_ten_god", "")), str(getattr(p, "branch_ten_god", ""))
        s_role = fav.get(str(STEM_ELEMENT.get(Stem(stem), ""))) if stem else None
        b_role = fav.get(str(BRANCH_ELEMENT.get(Branch(branch), ""))) if branch else None
        parts = []
        for pos, ch, tg, role in (("천간", stem, stg, s_role), ("지지", branch, btg, b_role)):
            target = relation_target(tg, gender, include_family)
            if not target:
                continue
            role_txt = f"·{role}" if role else ""
            parts.append(f"{pos} {ch} {tg}({_TEN_GOD_GROUP[tg]}{role_txt}): {target}")
            keys.append(f"relation:{_TEN_GOD_GROUP[tg]}@{getattr(p, 'label', '')}")
        if not parts:
            continue
        line = f"- {getattr(p, 'label', '')} {getattr(p, 'ganji', '')} — " + " / ".join(parts)
        names = [
            getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
            for s in (getattr(p, "luck_sinsal", None) or [])
        ]
        guin = [n for n in names if n in _GUIN]
        if guin:
            meaning = "; ".join(
                f"{n}: {(sinsal_meaning or {}).get(n, '')}".rstrip(": ") for n in guin
            )
            line += f" · 보조(귀인 신살, 사람 특정 근거 아님): {meaning}"
        lines.append(line)
    return lines, keys
