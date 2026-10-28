"""해외 근무(주재원·파견·현지 취업·이민) 질문 층 — 이동 신호 × 직업 신호 동시 활성화 (2026-10-28).

배경(실로그 web-mvrq8ocg): "주재원을 나가고 싶은데 해외에서 일한 운이 몇년도에 있어?"가 파서에
해외 근무 어휘가 없어 career 총운으로 떨어졌고, 답은 국내 이직 제안·면접 시기 서술이 됐다.

설계 근거: 데굴님이 제공한 참고 체계(2026-10-28, 전통 명리의 역마·관성·인성·재성 해석을 현대 해외
근무 상황에 적용한 추론 틀)를 본 리포의 엔진 값으로 번역한다. 핵심 원칙은 다음과 같다.

- **이동과 해외를 분리**: 이동 신호(이사·거주 변경 후보)는 이동 '후보'를 만들 뿐 해외 출국을
  확정하지 않는다.
- **이동과 직업을 결합**: 직업 관련 신호(이직·입사·승진·계약 문서)가 같은 기간에 함께 활성화될 때만
  해외 근무 후보를 높인다 — 한쪽만 있으면 '이동 신호만'/'직업 신호만'으로 구분해 표기한다.
- **근무 형태를 분리**: 주재원·해외 발령(조직 인사) / 파견·출장(일시 수행) / 해외 취업·현지 이직(새
  고용) / 해외 정착·이민(생활 기반 이동)은 별개 사건 유형이다.
- **단일 신살·십성 과대평가 금지**: 역마나 관성 하나로 해외 발령을 판정하지 않는다.
- **사건 확정도 부족 시 표현 완화**: '해외 발령 확정' 대신 '직장과 거주 환경의 동시 변화 가능성'.
- **발생 가능성 ≠ 성과**: 이동이 성립할 수 있다는 것과 이동 후 결과가 좋다는 것은 다른 판정이다.

새 점수 모델은 없다 — 기존 사건 후보(relocation·career_change·job_gain·promotion·
contract_document)의 점수와 세운 기둥의 십성을 **조합·표기**만 한다(절대원칙 1·9·10). 유형 힌트
(관성 주도=조직 발령형 등)는
운 간지의 십성에서 읽는 서술 힌트이며 판정이 아니다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from saju_shared_types.events import EventKey

#: 해외 근무 유형 — 참고 체계 §3의 A~D + 미지정.
OVERSEAS_KINDS: tuple[str, ...] = (
    "assignment", "dispatch", "local_hire", "emigration", "unspecified",
)
_KIND_KO = {
    "assignment": "주재원·해외 발령(조직 인사)",
    "dispatch": "해외 파견·출장(일시 수행)",
    "local_hire": "해외 취업·현지 법인 이직(새 고용)",
    "emigration": "해외 정착·이민(생활 기반 이동)",
    "unspecified": "해외 근무(형태 미지정)",
}

# 어휘 — 구체 유형을 먼저 본다(주재원 > 파견 > 현지 취업 > 이민 > 미지정).
_KIND_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("assignment", re.compile(
        r"주재원|주재\s*(?:근무|발령|나가)|해외\s*(?:발령|전근|근무지|지사|법인\s*근무)|해외로\s*발령"
    )),
    ("dispatch", re.compile(r"해외\s*(?:파견|출장)|파견\s*(?:근무|나가|가|갈)|단기\s*파견|파견")),
    ("local_hire", re.compile(
        r"해외\s*(?:취업|이직|취직|채용|구직)|현지\s*(?:채용|취업|법인(?:으로|에)?\s*이직)"
        r"|(?:외국|해외|글로벌|외국계)\s*(?:회사|기업)(?:로|으로|에)\s*(?:이직|취업|들어)"
    )),
    ("emigration", re.compile(r"이민|해외\s*(?:정착|이주)|영주권|외국에\s*(?:정착|눌러)")),
    ("unspecified", re.compile(
        r"해외\s*(?:근무|생활|진출|일자리|커리어|경력|에서\s*(?:일|근무|살))|해외에서\s*(?:일|근무|살)"
        r"|해외(?:로|에)?\s*(?:나가|나갈|나감|가서\s*일|가는)|외국에서\s*(?:일|근무|살)|외국\s*(?:근무|생활)"
    )),
)
#: 해외 여행·관광은 근무가 아니다 — 근무 어휘 없이 여행만 있으면 제외.
_TRAVEL_ONLY_RE = re.compile(r"여행|관광|휴가|놀러")


def detect_overseas_work(text: str) -> str | None:
    """발화의 해외 근무 유형(OVERSEAS_KINDS 중 하나) — 해외 근무 질문이 아니면 None.

    '해외 여행'처럼 여행·관광 어휘만 있고 근무 어휘가 없으면 None(이동 사건 경로 유지).
    """
    t = text or ""
    for kind, pat in _KIND_RES:
        if pat.search(t):
            return kind
    return None


def is_travel_only(text: str) -> bool:
    """근무 어휘 없이 여행·관광만 말하는가(해외 근무 층 비적용)."""
    return bool(_TRAVEL_ONLY_RE.search(text or "")) and detect_overseas_work(text) is None


#: 유형별 직업 신호 사건 키(참고 체계 §3) — 이동 신호는 공통으로 relocation.
JOB_KEYS_BY_KIND: dict[str, tuple[EventKey, ...]] = {
    "assignment": (EventKey.PROMOTION, EventKey.CONTRACT_DOCUMENT, EventKey.CAREER_CHANGE),
    "dispatch": (EventKey.CONTRACT_DOCUMENT, EventKey.CAREER_CHANGE),
    "local_hire": (EventKey.CAREER_CHANGE, EventKey.JOB_GAIN, EventKey.CONTRACT_DOCUMENT),
    "emigration": (EventKey.CONTRACT_DOCUMENT, EventKey.CAREER_CHANGE),
    "unspecified": (
        EventKey.CAREER_CHANGE, EventKey.JOB_GAIN, EventKey.PROMOTION, EventKey.CONTRACT_DOCUMENT,
    ),
}
#: 의도 앵커 — 주 사건은 이동(relocation), 동반 사건은 유형별 직업 키. 이직(career_change)을 주
#: 사건으로
#: 두면 국내 이직 서술·진입 두 칸 지시가 따라온다(실답).
PRIMARY_EVENT = EventKey.RELOCATION

#: 점수 경계 — tone_for_score 의 '조짐이 약하게 있습니다' 상한(55)과 같은 눈금을 쓴다.
_STRONG = 55
_WEAK = 40

_TEN_GOD_GROUP = {
    "정관": "관성", "편관": "관성", "식신": "식상", "상관": "식상",
    "정재": "재성", "편재": "재성", "정인": "인성", "편인": "인성",
    "비견": "비겁", "겁재": "비겁",
}
#: 십성 군 → 유형 힌트(참고 체계 §1·§3). 힌트이지 판정이 아니다.
_HINT_BY_GROUP = {
    "관성": "조직 인사·직책 변화(관성 주도) — 주재원·발령형 검토",
    "식상": "실무 수행·산출(식상 주도) — 파견·출장형 검토",
    "재성": "거래·계약·현지 보수(재성 주도) — 해외 영업·현지 취업형 검토",
    "인성": "문서·자격·승인·회사 지원(인성 주도) — 비자·계약·연수 절차 검토",
    "비겁": "동료·경쟁·독립(비겁 주도) — 자발 이동·독립형 검토",
}


class _Cand(Protocol):
    event_key: EventKey
    period: str
    score: int


class _Pillar(Protocol):
    label: str
    ganji: str
    stem_ten_god: str
    branch_ten_god: str
    yongsin_alignment: str


@dataclass(frozen=True)
class OverseasYearSignal:
    """한 해의 해외 근무 신호 — 이동·직업 신호의 최고 점수와 동시 활성화 등급."""

    year: str
    ganji: str
    move_score: int
    job_score: int
    job_key: EventKey | None
    tier: str  # strong | moderate | move_only | job_only | none
    hint: str
    yongsin_alignment: str


def _year_of(period: str) -> str:
    return period[:4]


def _max_score(
    cands: Iterable[_Cand], keys: Sequence[EventKey], year: str,
) -> tuple[int, EventKey | None]:
    best, best_key = 0, None
    for c in cands:
        if c.event_key in keys and _year_of(c.period) == year and c.score > best:
            best, best_key = c.score, c.event_key
    return best, best_key


def _tier(move: int, job: int) -> str:
    if move >= _STRONG and job >= _STRONG:
        return "strong"
    if move >= _WEAK and job >= _WEAK:
        return "moderate"
    if move >= _WEAK:
        return "move_only"
    if job >= _WEAK:
        return "job_only"
    return "none"


_TIER_KO = {
    "strong": "직장·거주 환경 동시 변화 가능성 — 강",
    "moderate": "직장·거주 환경 동시 변화 가능성 — 중",
    "move_only": "이동 신호만(직업 신호 약함) — 국내 이사·출장과 구분 불가",
    "job_only": "직업 신호만(이동 신호 약함) — 해외보다 국내 직무 변화 쪽",
    "none": "뚜렷한 신호 없음",
}


def overseas_year_signals(
    candidates: Iterable[_Cand],
    yearly: Iterable[_Pillar],
    years: Sequence[str],
    kind: str,
) -> list[OverseasYearSignal]:
    """연도별 해외 근무 신호 — 이동(relocation) 최고 점수 × 유형별 직업 키 최고 점수 → 등급.

    Args:
        candidates: 사건 후보(월·연 후보 모두 — 연도 단위로 묶는다).
        yearly: 세운 기둥(십성 힌트·용신 정렬).
        years: 표기할 연도 라벨('2026'…), 순서 유지.
        kind: OVERSEAS_KINDS 중 하나.

    Returns:
        연도별 신호 목록(years 순). 세운 기둥이 없는 해는 건너뛴다.
    """
    cands = list(candidates)
    by_year = {p.label: p for p in yearly if len(p.label) == 4}
    job_keys = JOB_KEYS_BY_KIND.get(kind, JOB_KEYS_BY_KIND["unspecified"])
    out: list[OverseasYearSignal] = []
    for y in years:
        p = by_year.get(y)
        if p is None:
            continue
        move, _ = _max_score(cands, (EventKey.RELOCATION,), y)
        job, job_key = _max_score(cands, job_keys, y)
        groups = [
            _TEN_GOD_GROUP.get(g) for g in (p.stem_ten_god, p.branch_ten_god)
            if _TEN_GOD_GROUP.get(g)
        ]
        hint = " / ".join(dict.fromkeys(_HINT_BY_GROUP[g] for g in groups if g in _HINT_BY_GROUP))
        out.append(OverseasYearSignal(
            year=y, ganji=p.ganji, move_score=move, job_score=job, job_key=job_key,
            tier=_tier(move, job), hint=hint, yongsin_alignment=p.yongsin_alignment,
        ))
    return out


_EVENT_KO = {
    EventKey.RELOCATION: "이동·거주 변화", EventKey.CAREER_CHANGE: "이직·직업 변화",
    EventKey.JOB_GAIN: "취업·입사", EventKey.PROMOTION: "승진·직책",
    EventKey.CONTRACT_DOCUMENT: "계약·문서",
}


def render_overseas_block(signals: Sequence[OverseasYearSignal], kind: str) -> list[str]:
    """LLM 입력 블록 — 연도별 신호표 + 해석 규칙. 신호가 없으면 규칙 줄만 돌려준다."""
    kind_ko = _KIND_KO.get(kind, _KIND_KO["unspecified"])
    lines = [
        f"[해외 근무 신호 — 이동 신호 × 직업 신호 동시 활성화(엔진 값, 유형: {kind_ko})] "
        "이동 신호=이동·거주 변화 후보 최고 점수, 직업 신호=유형별 직업 사건 후보 최고 점수. "
        "등급은 두 신호가 같은 해에 함께 있는지로만 정한다. 십성 힌트는 그 해 세운 간지의 십성에서 "
        "읽은 "
        "서술 힌트이지 판정이 아니다."
    ]
    for s in signals:
        job_ko = _EVENT_KO.get(s.job_key, "") if s.job_key else ""
        job_txt = f"{s.job_score}({job_ko})" if job_ko else str(s.job_score)
        line = (
            f"- {s.year}년 {s.ganji} — 이동 {s.move_score} · 직업 {job_txt} → {_TIER_KO[s.tier]}"
            f" · {s.yongsin_alignment}"
        )
        if s.hint:
            line += f" · 힌트: {s.hint}"
        lines.append(line)
    return lines


OVERSEAS_DIRECTIVE = (
    "[해외 근무 해석 규칙] ① 역마·이동 신호 하나로 해외 출국을, 관성 하나로 해외 발령을 "
    "판정하지 말 것 — [해외 근무 신호]의 등급(이동×직업 동시 활성화)만 근거로 쓴다. ② 등급이 "
    "'강'이어도 해외 발령·출국을 확정하지 말고 '직장과 거주 환경이 함께 바뀔 가능성'으로 말할 "
    "것. '이동 신호만'·'직업 신호만'인 해는 국내 이사·국내 직무 변화와 구분할 수 없다고 밝힐 "
    "것. ③ 주재원·발령(조직 인사)·파견·출장(일시)·해외 취업(새 고용)·이민(생활 기반)은 다른 "
    "사건이다 — 사용자가 말한 유형 기준으로 답하고 다른 유형으로 바꿔 서술하지 말 것(특히 "
    "국내 이직 제안·면접·스카우트 시기로 흐르지 말 것). ④ 단계는 제안→발령·계약→출국→현지 "
    "근무→연장·귀국으로 나뉜다 — 신호가 있는 해를 '발령 통보 시점'과 '실제 출국 시점'으로 "
    "나눠 가능성 단계로 말할 것. ⑤ 이동이 성립할 수 있다는 것과 이동 뒤 성과가 좋다는 것은 "
    "다른 판정이다 — 용신·희신 오행이라는 이유만으로 해외 근무 성과를 좋게 평가하지 말고, 그 "
    "해의 용신 정렬은 '기반'으로만 쓸 것. ⑥ 십성 힌트는 '어떤 경로(조직 "
    "인사/실무/계약/문서)로 움직임이 올 수 있는지'의 서술 힌트로만 쓸 것."
)
