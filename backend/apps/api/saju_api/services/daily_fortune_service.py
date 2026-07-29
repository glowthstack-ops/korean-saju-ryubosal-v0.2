"""일주별 오늘의 운세 — 서비스 계층 (lazy 생성·락·TTL·단건 조회).

엔진(saju_engines.daily_ilju_fortune)은 순수 계산만, 본 모듈이 캐시·락 등
사이드이펙트를 담당한다. 휘발성 원칙: 오늘(및 익일 선생성) 보드만 TTL 캐시,
과거 본문 저장·조회 없음(공개 API 는 today 전용 — 내부 target_date 는
선생성·테스트 용도로만 받는다).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from saju_engines.daily_fortune_cache import DailyFortuneCache
from saju_engines.daily_ilju_fortune import (
    build_day_context,
    compute_board,
    load_daily_dicts_for,
)
from saju_shared_types.constants import BRANCH_KO, STEM_KO
from saju_shared_types.daily_fortune import (
    DailyFortuneBoard,
    DailyFortuneSingle,
    content_version_for,
)

from .daily_beta_registry import (
    BetaDailyPoolRegistry,
    BetaPoolConfig,
    build_registry,
)
from .daily_beta_registry import render as render_beta
from .daily_fortune_export import write_threads_export

_KST = ZoneInfo("Asia/Seoul")

#: 시작 preflight 로 구성되는 불변 registry. 요청마다 파일을 다시 읽지 않는다.
_BETA_REGISTRY: BetaDailyPoolRegistry | None = None


def beta_enabled() -> bool:
    """이 배포가 베타 풀 배포인가 — 계정·헤더가 아니라 **배포 단위**로 정한다."""
    return BetaPoolConfig.from_env().enabled


def beta_preflight() -> BetaDailyPoolRegistry | None:
    """앱 시작 시 1회. 실패하면 예외를 그대로 올려 ready 진입을 막는다.

    검증 실패에 legacy 로 조용히 내려가지 않는다 — 테스터 일부가 legacy 를 보고도
    C10 을 본 것으로 피드백하게 된다.
    """
    global _BETA_REGISTRY
    if not beta_enabled():
        _BETA_REGISTRY = None
        return None
    _BETA_REGISTRY = build_registry()
    return _BETA_REGISTRY


def beta_registry() -> BetaDailyPoolRegistry | None:
    return _BETA_REGISTRY
_GENERATE_LOCK_TTL = 60  # 초 — 엔진 생성은 1초 미만이라 넉넉한 안전 상한
_LOCK_WAIT_RETRIES = 20
_LOCK_WAIT_INTERVAL = 0.25

# 일주 표기 정규화 테이블 — 한자("甲子")·한글("갑자") 모두 수용
_ILJU_ALIASES: dict[str, str] = {}
for _stem, _stem_ko in STEM_KO.items():
    for _branch, _branch_ko in BRANCH_KO.items():
        _hanja = f"{_stem.value}{_branch.value}"
        _ILJU_ALIASES[_hanja] = _hanja
        _ILJU_ALIASES[f"{_stem_ko}{_branch_ko}"] = _hanja


def kst_today() -> date:
    """KST 기준 오늘 날짜 (calendar_service 와 동일 기준)."""
    return datetime.now(_KST).date()


def board_ttl_seconds(d: date) -> int:
    """보드 TTL — 운세 날짜 익일 03:00 KST 까지(자정 경계·시계 오차 안전)."""
    expire_at = datetime(d.year, d.month, d.day, 3, 0, tzinfo=_KST) + timedelta(days=1)
    return max(60, int((expire_at - datetime.now(_KST)).total_seconds()))


def seconds_until_next_midnight(now: datetime | None = None) -> int:
    """HTTP Cache-Control max-age 용 — KST 다음 자정까지 남은 초."""
    now = now or datetime.now(_KST)
    tomorrow = (now + timedelta(days=1)).date()
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=_KST)
    return max(1, int((midnight - now).total_seconds()))


def normalize_ilju(raw: str) -> str | None:
    """일주 표기(한자·한글)를 한자 2자로 정규화 — 무효면 None."""
    return _ILJU_ALIASES.get(raw.strip())


def _generate(d: date) -> DailyFortuneBoard:
    """엔진으로 하루치 보드를 생성한다(결정론 — 경합 중복 생성도 동일 결과).

    사전은 **날짜가 고른다**(OA-6a2) — 과거 날짜는 과거 계약으로 재생돼야 한다.
    """
    return compute_board(build_day_context(d), load_daily_dicts_for(d))


def get_board(
    cache: DailyFortuneCache | None, today: date | None = None
) -> DailyFortuneBoard:
    """오늘자 보드 반환 — 캐시 미스면 생성 락 후 lazy 생성.

    락 미획득 시 짧은 재조회 대기, 최종 실패 시 직접 생성(엔진이 결정론이라
    동시 SET 이 일어나도 값은 동일 — 무해).
    """
    d = today or kst_today()
    registry = beta_registry()
    if registry is not None:
        # 베타 배포 — snapshot 이 선택의 SSOT 다. 캐시·락·lazy 생성을 타지 않는다.
        board, _audit = render_beta(registry, d)
        return board
    if cache is None:                       # legacy 경로는 캐시가 반드시 있어야 한다
        raise RuntimeError("일운 캐시 미설정")
    version = content_version_for(d)
    board = cache.load_board(d, version)
    if board is not None:
        return board

    token = cache.acquire_lock("generate", d, version, _GENERATE_LOCK_TTL)
    if token is not None:
        try:
            board = cache.load_board(d, version)  # 이중 확인
            if board is None:
                board = _generate(d)
                cache.save_board(d, version, board, board_ttl_seconds(d))
                write_threads_export(board)  # 스레드 업로드용 텍스트 갱신
            return board
        finally:
            cache.release_lock("generate", d, version, token)

    for _ in range(_LOCK_WAIT_RETRIES):  # 락 소유자 완료 대기
        time.sleep(_LOCK_WAIT_INTERVAL)
        board = cache.load_board(d, version)
        if board is not None:
            return board
    board = _generate(d)
    cache.save_board(d, version, board, board_ttl_seconds(d))
    write_threads_export(board)  # 스레드 업로드용 텍스트 갱신
    return board


def get_single(
    cache: DailyFortuneCache | None, ilju_raw: str, today: date | None = None
) -> DailyFortuneSingle | None:
    """일주 단건(메인 카드용) — 표기 무효면 None."""
    ilju = normalize_ilju(ilju_raw)
    if ilju is None:
        return None
    board = get_board(cache, today)
    fortune = next(f for f in board.fortunes if f.ilju == ilju)
    return DailyFortuneSingle(
        fortune_date=board.fortune_date,
        weekday=board.weekday,
        weekday_ko=board.weekday_ko,
        fortune=fortune,
    )
