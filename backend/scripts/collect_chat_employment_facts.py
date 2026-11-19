"""채팅 질문 입력에서 입사·퇴사 사실을 우회 수집한다 — 기본은 읽기 전용, `--load` 로 원장 적재.

SSOT: doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §8.

배경(2026-11-18 데굴님): 재직 기간·입사 시점 대조를 다른 사람 이력으로 검증하려면 입사+퇴사
시점이 필요한데, 원장에는 데굴님 외 퇴사 기록이 없다. 이력 입력을 따로 요청하지 않고 **AI 채팅
상담에 사용자가 스스로 적은 문장**에서 모은다("3은 AI채팅상담의 질문 입력 내용을 바탕으로 우회
수집").

하는 일:
- `chat_messages`(role='user')를 `chat_threads`와 묶어 읽는다(대상 subject_id·계정은 스레드 기준).
- 절(문장부호·쉼표 경계) 단위로 **본인의 완료형 보고**만 고른다 — 판별은 운영 감지기를 그대로
  쓴다(`career_fact_parser.parse_career_fact` 의 JOINED·EXIT_COMPLETED hard fact,
  `job_change_report.is_job_change_report`, `job_separation.is_job_separation`). 가정·계획·부정·
  제3자 문장은 그 감지기와 같은 가드로 뺀다(사용자가 말한 사실만 — 추론 없음).
- 절에 적힌 때 표현을 **메시지 작성일 기준**으로 날짜로 옮긴다(연·월·일 정밀도). 때 표현이
  없으면 날짜 없이 남긴다(집계만, 대조에는 쓰지 않는다).
- 날짜가 있으면 절기월 라벨(`employment_history.luck_month_label`)을 붙인다.

기본 실행은 DB 를 쓰지 않는다. 결과는 검토용 JSONL(`--out`, 기본 var/ 아래 — git 비추적)과 요약
수치다. 계정은 해시로만 남기고 회사명은 뽑지 않는다(인용은 절 80자 이내).

원장 적재(`--load`, 2026-11-18 데굴님 "원장에 적재만 하고 채팅에서의 추가 액션은 없이 가자"):
`subject_life_events` 에 소스 `chat_statement` 로 넣는다. 이 소스는 **적재만** 한다 — 개인 시그니처·
코호트 집계에서 빠지므로 점수·풀이·채팅 동작은 바뀌지 않는다(`SCORING_EXCLUDED_SOURCES`). 적재 조건:
- 때가 일·월 정밀도(연 단위·때 없음은 절기월을 정할 수 없어 뺀다 — 추측 금지)
- 대상 확정: 스레드에 묶인 명식(subject_id)으로만 정한다. 이름(별명)으로는 정하지 않는다
  (2026-11-18 데굴님 "동명인 경우도 많을 수 있으니 기본적으로는 사주 자체로 구분") — 별명은
  표시용이라 '본인' 같은 일반 이름·동명이 흔하다. 명식 연결이 없는 스레드(2026-10-24 이전
  대화)에는 출생 정보·간지가 남아 있지 않아 어느 명식인지 가릴 수 없으므로 싣지 않는다
- 그 명식이 **본인 명식**(kind='self')일 때만 — 동반자 명식 스레드의 1인칭 문장은 말한 사람과
  명식 주인이 다를 수 있어 싣지 않는다(대상 우선 확정 원칙)
- 정본(직장 이력 `employment_history`)에 같은 달의 입사·퇴사·전환 행이 없을 때만
행 id 는 대상·종류·때로 정해져 다시 돌려도 중복되지 않는다. 인용문·회사명은 원장에 싣지 않는다.

사용법:
    python scripts/collect_chat_employment_facts.py [--out 경로] [--since YYYY-MM-DD] [--load]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from saju_engines.career_fact_parser import parse_career_fact
from saju_engines.employment_history import (
    CHAT_FACT_EVENT_KEY,
    MonthFingerprintResolver,
    chat_statement_row,
    luck_month_label,
)
from saju_engines.job_change_report import is_job_change_report
from saju_engines.job_separation import is_job_separation
from saju_shared_types.career_commands import CareerFactType
from saju_shared_types.life_event import LifeEventRow, LifeEventSource
from saju_shared_types.subject import SubjectRecord

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_KST = ZoneInfo("Asia/Seoul")
_MAX_QUOTE = 80
_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n,]+")
#: 직장 이탈 완료형·가정형·제3자 — `user_facts` 의 직장 이탈 슬롯 가드와 같은 원칙(본인 완료형만).
_SEPARATION_DONE_RE = re.compile(
    r"받았|당했|됐|되었|했어|했고|했는데|했습니다|들었|잘렸|짤렸|잘림|짤림|쫓겨났|나가라고"
)
_HYPOTHETICAL_RE = re.compile(
    r"당할까|될까|당하면|되면|하려는데|하려고|려면|소문|가능성|걱정|두려|으면|다면|을까|할까|ㄹ까"
)
_NEGATED_RE = re.compile(r"(?:안|못)\s*(?:했|옮|들어|갔|왔|뒀)|아직\s*(?:이직|옮|입사|퇴사)")
_THIRD_PARTY_RE = re.compile(
    r"(?:남편|아내|와이프|신랑|친구|동생|언니|누나|형|오빠|엄마|아빠|어머니|아버지|부모님|동료"
    r"|지인|딸|아들|직원|부하|팀원|후배|선배|남자\s*친구|여자\s*친구|남친|여친|애인)"
    r"(?:이|가|은|는|도|을|를)?\s"
)
_ENTRY_WORD_RE = re.compile(r"입사|취업|취직|첫\s*출근|새\s*(?:회사|직장)|합류")
#: 완료형 바로 뒤의 가정·소원 꼬리 — "해고당했으면"·"잘렸다면"은 보고가 아니다. 같은 절의 뒤쪽
#: 질문("…당했는데 다시 취직할 수 있을까")은 보고를 지우지 않는다.
_HYPOTHETICAL_TAIL_RE = re.compile(r"^\s*(?:으면|다면|을까|더라면|더라도)")
#: 재직 기간 진술 — "일한 지 3개월 됐어"·"입사한 지 2년" → 작성일에서 거꾸로 센 입사 때.
_TENURE_RE = re.compile(
    r"(?:일한|다닌|근무한|입사한|취업한|취직한)\s*지\s*(\d{1,2})(?:\s*[-~]\s*\d{1,2})?\s*(년|개월|달)"
)
_MOVE_WORD_RE = re.compile(r"이직|전직|(?:회사|직장)\s*(?:을|를)?\s*옮")

# ── 때 표현(메시지 작성일 기준) ──────────────────────────────────────────────
_YMD_RE = re.compile(r"((?:19|20)\d{2})\s*년\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?")
_YY_M_RE = re.compile(r"(?<!\d)(\d{2})\s*년\s*(\d{1,2})\s*월")
_Y_ONLY_RE = re.compile(r"((?:19|20)\d{2})\s*년(?!\s*\d{1,2}\s*월)")
_REL_YEAR_RE = re.compile(
    r"(재작년|작년|지난\s*해|올해|금년)(?:\s*(\d{1,2})\s*월)?(?:\s*(\d{1,2})\s*일)?"
)
_YEARS_AGO_RE = re.compile(r"(\d{1,2})\s*년\s*전")
_MONTHS_AGO_RE = re.compile(r"(\d{1,2})\s*(?:개월|달)\s*전")
_REL_MONTH_RE = re.compile(r"(지난\s*달|저번\s*달|이번\s*달|이달)(?:\s*(\d{1,2})\s*일)?")
_REL_DAY_RE = re.compile(r"(오늘|어제|그저께|방금|아까)")
_REL_WEEK_RE = re.compile(r"(이번\s*주|지난\s*주|저번\s*주)")
_BARE_MD_RE = re.compile(r"(?<![\d년])\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?")
_REL_YEAR_OFFSET = {"재작년": -2, "작년": -1, "올해": 0, "금년": 0}


@dataclass
class ResolvedDate:
    """때 표현 해석 결과 — 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' 와 정밀도."""

    text: str
    precision: str  # day | month | year


@dataclass
class ChatEmploymentFact:
    """채팅에서 사용자가 말한 입사·퇴사 사실 1건."""

    subject_id: str | None
    owner_key: str            # 계정 해시(앞 12자)
    subject_label: str | None  # 표시용 별명 — 대상 식별에는 쓰지 않는다
    kind: str                 # entry | exit | move(같은 때의 퇴사+입사)
    exit_reason: str | None   # 퇴사 계열 중 해고·권고사직 등 = involuntary
    date: str | None
    precision: str | None
    luck_month_label: str | None
    quote: str
    message_id: int
    said_on: str              # 메시지 작성일(KST)
    thread_key: str = ""      # 스레드 해시(앞 12자) — 명식 연결 없는 스레드의 묶음 단위


def _load_env() -> None:
    """루트 .env → 환경 변수(이미 설정된 키는 유지)."""
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _valid(y: int, m: int, d: int | None = None) -> bool:
    try:
        date(y, m, d or 1)
    except ValueError:
        return False
    return True


def _shift_month(day: date, months: int) -> tuple[int, int]:
    idx = day.year * 12 + (day.month - 1) + months
    return idx // 12, idx % 12 + 1


def resolve_stated_date(clause: str, said_on: date) -> ResolvedDate | None:
    """절의 때 표현을 메시지 작성일 기준으로 옮긴다. 표현이 없거나 미래면 None.

    완료형 보고의 때이므로 연도 없는 'M월'은 작성일 이전의 가장 가까운 그 달로 읽는다.
    """
    out: ResolvedDate | None = None
    if m := _TENURE_RE.search(clause):
        n = int(m.group(1))
        if m.group(2) == "년":
            out = ResolvedDate(str(said_on.year - n), "year")
        else:
            y, mo = _shift_month(said_on, -n)
            out = ResolvedDate(f"{y}-{mo:02d}", "month")
    elif m := _YMD_RE.search(clause):
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else None
        if _valid(y, mo, d):
            out = ResolvedDate(
                f"{y}-{mo:02d}-{d:02d}" if d else f"{y}-{mo:02d}", "day" if d else "month",
            )
    elif m := _YY_M_RE.search(clause):
        y, mo = 2000 + int(m.group(1)), int(m.group(2))
        if _valid(y, mo):
            out = ResolvedDate(f"{y}-{mo:02d}", "month")
    elif m := _REL_YEAR_RE.search(clause):
        word = re.sub(r"\s+", "", m.group(1)).replace("지난해", "작년")
        y = said_on.year + _REL_YEAR_OFFSET[word]
        rel_mo = int(m.group(2)) if m.group(2) else None
        d = int(m.group(3)) if m.group(3) and rel_mo else None
        if rel_mo is None:
            out = ResolvedDate(str(y), "year")
        elif _valid(y, rel_mo, d):
            out = ResolvedDate(
                f"{y}-{rel_mo:02d}-{d:02d}" if d else f"{y}-{rel_mo:02d}",
                "day" if d else "month",
            )
    elif m := _Y_ONLY_RE.search(clause):
        out = ResolvedDate(m.group(1), "year")
    elif m := _YEARS_AGO_RE.search(clause):
        out = ResolvedDate(str(said_on.year - int(m.group(1))), "year")
    elif m := _MONTHS_AGO_RE.search(clause):
        y, mo = _shift_month(said_on, -int(m.group(1)))
        out = ResolvedDate(f"{y}-{mo:02d}", "month")
    elif m := _REL_MONTH_RE.search(clause):
        back = -1 if re.sub(r"\s+", "", m.group(1)) in ("지난달", "저번달") else 0
        y, mo = _shift_month(said_on, back)
        d = int(m.group(2)) if m.group(2) else None
        if _valid(y, mo, d):
            out = ResolvedDate(
                f"{y}-{mo:02d}-{d:02d}" if d else f"{y}-{mo:02d}", "day" if d else "month",
            )
    elif m := _REL_DAY_RE.search(clause):
        back = {"어제": 1, "그저께": 2}.get(m.group(1), 0)
        out = ResolvedDate((said_on - timedelta(days=back)).isoformat(), "day")
    elif m := _REL_WEEK_RE.search(clause):
        ref = said_on - timedelta(days=7 if "이번" not in m.group(1) else 0)
        out = ResolvedDate(f"{ref.year}-{ref.month:02d}", "month")
    elif m := _BARE_MD_RE.search(clause):
        mo = int(m.group(1))
        d = int(m.group(2)) if m.group(2) else None
        if 1 <= mo <= 12:
            y = said_on.year if (mo, d or 1) <= (said_on.month, said_on.day) else said_on.year - 1
            if _valid(y, mo, d):
                out = ResolvedDate(
                    f"{y}-{mo:02d}-{d:02d}" if d else f"{y}-{mo:02d}", "day" if d else "month",
                )
    if out is None:
        return None
    # 미래 때 표현은 완료형 보고의 때가 아니다(예정·계획 문장의 잔여) — 버린다.
    limit = {
        "day": said_on.isoformat(), "month": said_on.strftime("%Y-%m"), "year": str(said_on.year),
    }[out.precision]
    return out if out.text <= limit else None


def classify_clause(clause: str) -> tuple[str, str | None] | None:
    """절이 본인의 완료형 입사·퇴사 보고면 (kind, exit_reason), 아니면 None."""
    if _THIRD_PARTY_RE.search(clause) or _NEGATED_RE.search(clause):
        return None
    if is_job_separation(clause):
        return ("exit", "involuntary") if _separation_reported(clause) else None
    if _TENURE_RE.search(clause):
        return "entry", None
    if _HYPOTHETICAL_RE.search(clause):
        return None
    fact = parse_career_fact(clause)
    if fact.is_transition_eligible:
        if fact.fact_type is CareerFactType.EXIT_COMPLETED:
            return "exit", None
        if fact.fact_type is CareerFactType.JOINED:
            return "entry", None
    if is_job_change_report(clause):
        if _MOVE_WORD_RE.search(clause):
            return "move", None
        if _ENTRY_WORD_RE.search(clause):
            return "entry", None
    return None


def _separation_reported(clause: str) -> bool:
    """직장 이탈 어휘 바로 뒤에 완료형이 붙고, 그 뒤가 가정·소원 꼬리가 아닌가."""
    from saju_engines.job_separation import JOB_SEPARATION_RE

    for m in JOB_SEPARATION_RE.finditer(clause):
        window = clause[m.end(): m.end() + 10]
        done = _SEPARATION_DONE_RE.search(window)
        if done is None:
            continue
        between = window[: done.start()]
        tail = clause[m.end() + done.end():]
        if _HYPOTHETICAL_RE.search(between) or _HYPOTHETICAL_TAIL_RE.match(tail):
            continue
        return True
    return False


ExtractedFact = tuple[str, str | None, ResolvedDate | None, str]
"""(kind, exit_reason, 날짜, 인용 절)."""


def extract_facts(text: str, said_on: date) -> list[ExtractedFact]:
    """메시지 본문 → [(kind, exit_reason, 날짜, 인용 절)]. 절마다 한 건."""
    out: list[ExtractedFact] = []
    for raw in _CLAUSE_SPLIT_RE.split(text or ""):
        clause = raw.strip()
        if len(clause) < 4:
            continue
        hit = classify_clause(clause)
        if hit is None:
            continue
        out.append((hit[0], hit[1], resolve_stated_date(clause, said_on), clause[:_MAX_QUOTE]))
    return out


def collect(dsn: str, since: date | None) -> list[ChatEmploymentFact]:
    """DB 의 사용자 메시지를 훑어 사실 목록을 만든다(같은 대상·종류·날짜는 처음 말한 것만)."""
    return collect_with_owners(dsn, since)[0]


def collect_with_owners(
    dsn: str, since: date | None,
) -> tuple[list[ChatEmploymentFact], dict[int, str]]:
    """`collect` + 메시지 번호 → 계정 id(적재용 — JSONL 에는 해시만 남긴다)."""
    owners: dict[int, str] = {}
    sql = (
        "SELECT m.id, m.text, m.created_at, t.owner_id, t.subject_id, t.subject_label, "
        "t.thread_id "
        "FROM chat_messages m JOIN chat_threads t USING (thread_id) "
        "WHERE m.role = 'user' ORDER BY m.created_at, m.id"
    )
    facts: list[ChatEmploymentFact] = []
    seen: set[tuple[str, str, str]] = set()
    with psycopg.connect(dsn) as conn:
        for mid, text, created_at, owner_id, subject_id, subject_label, thread_id in (
            conn.execute(sql)
        ):
            said_on = _as_kst_date(created_at)
            if since is not None and said_on < since:
                continue
            owner_key = hashlib.sha256(str(owner_id).encode("utf-8")).hexdigest()[:12]
            thread_key = hashlib.sha256(str(thread_id).encode("utf-8")).hexdigest()[:12]
            for kind, reason, resolved, quote in extract_facts(text, said_on):
                who = _who(subject_id, thread_key)
                key = (who, kind, resolved.text if resolved else f"undated:{mid}")
                if key in seen:
                    continue
                seen.add(key)
                label = None
                if resolved is not None and resolved.precision in ("day", "month"):
                    rep = (
                        date.fromisoformat(resolved.text) if resolved.precision == "day"
                        else date(int(resolved.text[:4]), int(resolved.text[5:7]), 15)
                    )
                    label = luck_month_label(rep)
                owners[int(mid)] = str(owner_id)
                facts.append(ChatEmploymentFact(
                    subject_id=subject_id, owner_key=owner_key, subject_label=subject_label,
                    kind=kind, exit_reason=reason,
                    date=resolved.text if resolved else None,
                    precision=resolved.precision if resolved else None,
                    luck_month_label=label, quote=quote, message_id=int(mid),
                    said_on=said_on.isoformat(), thread_key=thread_key,
                ))
    return facts, owners


SKIP_NO_DATE = "때 없음·연 단위(절기월 미정)"
SKIP_NO_SUBJECT = "대상 미확정"
SKIP_NOT_SELF = "본인 명식 아님(동반자 스레드)"
SKIP_CANONICAL = "정본 이력에 같은 달 기록 있음"
#: 정본 이력에서 같은 달이면 겹친다고 보는 사건 키(입사·퇴사·전환).
_CANONICAL_KEYS = frozenset({"job_gain", "resignation", "career_change"})


def resolve_fact_subject(
    fact: ChatEmploymentFact, owner_subjects: list[SubjectRecord],
) -> SubjectRecord | None:
    """사실의 대상 명식 — 스레드에 묶인 명식(subject_id)으로만 정한다.

    이름(별명)으로는 정하지 않는다: 별명은 표시용이라 '본인' 같은 일반 이름·동명이 흔하다
    (2026-11-18 데굴님 "동명인 경우도 많을 수 있으니 기본적으로는 사주 자체로 구분"). 명식 연결이
    없는 스레드는 출생 정보·간지가 남아 있지 않아 가릴 수 없으므로 None — 계정에 본인 명식이
    하나뿐이어도 추측하지 않는다. subject_id 가 그 계정 명식이 아니어도 None.
    """
    if not fact.subject_id:
        return None
    return next((s for s in owner_subjects if s.subject_id == fact.subject_id), None)


def plan_load(
    facts: list[ChatEmploymentFact],
    owners: dict[int, str],
    subjects_of: Callable[[str], list[SubjectRecord]],
    signature_of: Callable[[SubjectRecord], list[LifeEventRow]],
) -> tuple[list[tuple[ChatEmploymentFact, SubjectRecord]], Counter[str]]:
    """적재 대상과 제외 사유 집계 — 조건은 모듈 docstring '원장 적재' 절.

    Args:
        facts: 수집된 사실.
        owners: 메시지 번호 → 계정 id.
        subjects_of: 계정 id → 그 계정의 명식 목록.
        signature_of: 명식 → 원장 행 전체(정본 겹침 판정용).
    """
    planned: list[tuple[ChatEmploymentFact, SubjectRecord]] = []
    skipped: Counter[str] = Counter()
    for f in facts:
        dated = f.date is not None and f.precision in ("day", "month")
        if f.kind not in CHAT_FACT_EVENT_KEY or not dated:
            skipped[SKIP_NO_DATE] += 1
            continue
        owner = owners.get(f.message_id)
        rec = resolve_fact_subject(f, subjects_of(owner)) if owner else None
        if rec is None:
            skipped[SKIP_NO_SUBJECT] += 1
            continue
        if rec.kind != "self":
            skipped[SKIP_NOT_SELF] += 1
            continue
        canonical = {
            r.period for r in signature_of(rec)
            if r.source is LifeEventSource.EMPLOYMENT_HISTORY and r.event_key in _CANONICAL_KEYS
        }
        if f.luck_month_label in canonical:
            skipped[SKIP_CANONICAL] += 1
            continue
        planned.append((f, rec))
    return planned, skipped


def load_into_ledger(
    facts: list[ChatEmploymentFact], owners: dict[int, str],
) -> tuple[int, Counter[str]]:
    """수집 사실을 원장에 적재한다(소스 chat_statement). (적재 행 수, 제외 사유 집계) 반환.

    절기월·월운 지문·글자는 직장 이력 적재와 같은 resolver 로 엔진이 계산한다. 마이그레이션(소스
    제약 추가)은 멱등이라 매번 적용한다.
    """
    from saju_api.services.manse_service import calculate
    from saju_engines.employment_history import make_month_fingerprint_resolver
    from saju_engines.event_engine_v2 import EventEngineV2
    from saju_engines.life_event_store import LifeEventStore
    from saju_engines.reality_calibration import pillars_signature
    from saju_engines.subject_store import SubjectStore

    subjects, store = SubjectStore(), LifeEventStore()
    store.migrate()
    cache: dict[str, list[SubjectRecord]] = {}

    def subjects_of(owner: str) -> list[SubjectRecord]:
        if owner not in cache:
            cache[owner] = subjects.list_all(owner)
        return cache[owner]

    planned, skipped = plan_load(
        facts, owners, subjects_of,
        lambda rec: store.subject_signature(rec.owner_id, rec.subject_id, include_unverified=True),
    )
    engine = EventEngineV2(_BACKEND / "dictionaries")
    rows: list[LifeEventRow] = []
    for f, rec in planned:
        resolver: MonthFingerprintResolver = make_month_fingerprint_resolver(
            rec.birth, engine, calculate,
        )
        row = chat_statement_row(
            kind=f.kind, stated_date=f.date or "", precision=f.precision or "",
            exit_reason=f.exit_reason, message_id=f.message_id,
            subject_id=rec.subject_id, owner_id=rec.owner_id,
            pillars_sig=pillars_signature(calculate(rec.birth)), month_fp=resolver,
        )
        if row is not None:
            rows.append(row)
    return store.append_rows(rows), skipped


def _who(subject_id: str | None, thread_key: str) -> str:
    """사실 묶음 단위 — 명식(subject_id), 명식 연결이 없으면 스레드. 별명으로 묶지 않는다."""
    return subject_id or f"thread:{thread_key}"


def _as_kst_date(created_at: datetime) -> date:
    return created_at.astimezone(_KST).date()


def summarize(facts: list[ChatEmploymentFact]) -> str:
    """요약 수치 — 종류×정밀도, 대상 수, 재직 기간을 낼 수 있는 대상 수."""
    by = Counter((f.kind, f.precision or "undated") for f in facts)
    who = lambda f: _who(f.subject_id, f.thread_key)  # noqa: E731
    dated: dict[str, set[str]] = {}
    for f in facts:
        if f.date is not None:
            kinds = {"entry", "exit"} if f.kind == "move" else {f.kind}
            dated.setdefault(who(f), set()).update(kinds)
    tenure_capable = sum(1 for kinds in dated.values() if {"entry", "exit"} <= kinds)
    lines = [
        f"사실 {len(facts)}건 · 대상 {len({who(f) for f in facts})}명"
        f"(subject_id 묶인 대상 {len({f.subject_id for f in facts if f.subject_id})}명)",
        "종류×정밀도: " + ", ".join(f"{k}/{p} {n}" for (k, p), n in sorted(by.items())),
        f"날짜 있는 사실이 있는 대상 {len(dated)}명 · 입사·퇴사 둘 다 날짜가 있는 대상 "
        f"{tenure_capable}명(재직 기간 산출 가능 후보)",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None, help="검토용 JSONL 경로(없으면 요약만)")
    ap.add_argument("--since", type=date.fromisoformat, default=None, help="이 날짜 이후 메시지만")
    ap.add_argument(
        "--load", action="store_true",
        help="원장(subject_life_events, 소스 chat_statement)에 적재 — 점수·풀이에는 쓰이지 않는다",
    )
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정", file=sys.stderr)
        return 2
    facts, owners = collect_with_owners(dsn, args.since)
    print(summarize(facts))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for f in facts:
                fh.write(json.dumps(asdict(f), ensure_ascii=False) + "\n")
        print(f"[ok] {args.out} ({len(facts)}행)")
    if args.load:
        stored, skipped = load_into_ledger(facts, owners)
        print(f"[load] 원장 적재 {stored}행(소스 chat_statement, 점수 미반영)")
        for reason, n in sorted(skipped.items()):
            print(f"[load] 제외 {n}건 — {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
