"""오늘의 운세 스레드(Threads) 업로드용 텍스트 export (2026-07-23 데굴님 지시).

보드 생성·교정 저장 시마다 리포 최상위에 고정 파일명으로 갱신한다. 최상단에
대상 날짜를 기록해 어느 날짜의 내용인지 확인할 수 있게 한다. 커밋 제외 대상
(.gitignore 등재) — 실패해도 서비스 흐름을 막지 않는다(로그만).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from saju_shared_types.daily_fortune import DailyFortuneBoard, DailyIljuFortune

logger = logging.getLogger(__name__)

# 리포 최상위 고정 파일명 — 날짜가 바뀌어도 같은 파일을 덮어쓴다.
_REPO_ROOT = Path(__file__).resolve().parents[5]
THREADS_EXPORT_PATH = _REPO_ROOT / "오늘의운세.txt"

_KST = ZoneInfo("Asia/Seoul")

#: 스레드 게시분이 익일자로 넘어가는 시각(KST, 2026-08-05 데굴님 지시).
#: 이 시각부터 파일은 **내일 보드**를 담는다 — 사용자 API 노출(00:00)과는 별개다.
THREADS_PUBLISH_HOUR = 21

_MEDALS = ("🥇", "🥈", "🥉", "🏅", "🏅")
_SLOT_LABEL = {"good": "좋은 흐름", "caution": "주의", "support": "도움"}

# 천간 그룹 정렬 — 화면(StemTabs)과 동일한 갑→계 순서·라벨. 그룹 내부는
# 보드 순서(60갑자 순)를 유지한다(탭 안 표시 순서와 동일).
_STEM_ORDER = ("갑", "을", "병", "정", "무", "기", "경", "신", "임", "계")
_STEM_LABEL = {
    "갑": "갑목",
    "을": "을목",
    "병": "병화",
    "정": "정화",
    "무": "무토",
    "기": "기토",
    "경": "경금",
    "신": "신금",
    "임": "임수",
    "계": "계수",
}


def threads_publish_date(now: datetime | None = None) -> date:
    """이 순간 스레드 파일이 담아야 할 날짜 — `THREADS_PUBLISH_HOUR` 부터 익일이다.

    사용자 API 노출 기준일(`daily_fortune_service.kst_today`)과 **의도적으로 다르다.**
    파일은 미리 만들어 저녁에 올리고, 서비스 화면은 자정에 넘어간다(2026-08-05 확정).
    노출 기준일까지 같이 옮기면 21시에 접속한 사용자가 내일 운세를 오늘 것으로 보게 된다.

    허용 날짜는 어느 순간에도 **정확히 하나**다. 경계를 옮길 뿐 가드를 넓히지 않는다 —
    임의 날짜 보드가 파일을 덮는 것(2026-08-01 사고)은 그대로 막힌다.
    """
    now = now or datetime.now(_KST)
    if now.hour >= THREADS_PUBLISH_HOUR:
        return (now + timedelta(days=1)).date()
    return now.date()


def render_threads_text(board: DailyFortuneBoard) -> str:
    """보드 → 스레드 업로드용 본문. 최상단에 대상 날짜를 명시한다."""
    ko_by_ilju = {f.ilju: f.ilju_ko for f in board.fortunes}
    lines: list[str] = [
        f"[오늘의 운세 — {board.fortune_date.isoformat()} {board.weekday_ko}]",
        f"(생성 버전: {board.content_version} / 교정: {board.polish_status})",
        "",
    ]
    # 3분야 TOP5 — 화면(Top5Strip)과 동일한 분야·표기 순서(금전·연애·좋은소식).
    top5_sections = (
        ("💰 오늘 금전 운 좋은 일주 TOP5", board.top5.money),
        ("💗 오늘 연애 운 좋은 일주 TOP5", board.top5.love),
        ("💌 오늘 좋은소식이 들려올 일주 TOP5", board.top5.news),
    )
    for title, iljus in top5_sections:
        lines.append(title)
        for i, ilju in enumerate(iljus[:5]):
            medal = _MEDALS[i] if i < len(_MEDALS) else "•"
            lines.append(f"{medal} {i + 1}. {ko_by_ilju.get(ilju, ilju)}일주")
        lines.append("")
    def _fortune_block(f: DailyIljuFortune) -> list[str]:
        block = [f"■ {f.ilju_ko}일주", f"{f.headline}"]
        for ev in f.events:
            label = _SLOT_LABEL.get(ev.slot, ev.slot)
            block.append(f"- {label}: {ev.phrase} ({ev.probability}%)")
        block.append(f"- 행운의 장소: {f.lucky_place.phrase}")
        if f.love_line:  # 일일 연애운 확장(beta)
            block.append(f"- 오늘의 연애: {f.love_line}")
        if f.lotto_phrase:
            block.append(f"- {f.lotto_phrase}")
        block.append("")
        return block

    # 천간 그룹 순서(갑→계)로 정렬 — 그룹 내부는 보드 순서(60갑자 순) 유지.
    by_stem: dict[str, list[DailyIljuFortune]] = {}
    for f in board.fortunes:
        by_stem.setdefault(f.day_stem_ko, []).append(f)
    for stem in _STEM_ORDER:
        group = by_stem.pop(stem, [])
        if not group:
            continue
        lines.append(f"══ {_STEM_LABEL[stem]}({group[0].ilju[0]}) 일주 ══")
        lines.append("")
        for f in group:
            lines.extend(_fortune_block(f))
    # 예상 밖 천간(이론상 없음)이 남으면 누락 없이 말미에 보존한다.
    for group in by_stem.values():
        for f in group:
            lines.extend(_fortune_block(f))
    return "\n".join(lines).rstrip() + "\n"


def write_threads_export(
    board: DailyFortuneBoard, path: Path | None = None,
    *, publish_date: date | None = None,
) -> bool:
    """스레드용 텍스트 파일 갱신(원자적 교체). 실패해도 예외를 전파하지 않는다.

    **게시 기준일 보드일 때만 쓴다.** 이 파일은 날짜가 바뀌어도 같은 경로를 덮어쓰는데,
    `get_board`·`polish_board` 는 임의 날짜로 호출될 수 있다(사전생성·관리자 수동
    실행·과거 재생). 가드가 없으면 그 날짜 보드가 게시분 파일을 덮는다.

    실제로 2026-08-01 00:02 에 8/2 보드가 이 파일을 덮어 토요일에 일요일 운세가
    올라갔다. 가드를 호출부마다 두지 않고 여기 둔 이유는, 새 호출부가 생겼을 때
    빠뜨리면 같은 사고가 반복되기 때문이다.

    기준일은 `threads_publish_date` 다 — 21시부터 익일로 넘어가므로 그 시각 이후에는
    **익일 보드만** 통과하고 당일 보드는 막힌다(21시 이후 lazy 재생성이 파일을 당일자로
    되돌리지 못한다). 어느 순간에도 통과하는 날짜는 하나뿐이다.

    Args:
        board: 기록할 보드.
        path: 대상 경로. None이면 **호출 시점에** `THREADS_EXPORT_PATH` 를 읽는다.
            기본값을 시그니처에 박으면 정의 시점에 고정돼 테스트가 격리할 수 없고,
            실제로 테스트 실행이 운영 파일을 덮었다(2026-08-03 실측).
        publish_date: 게시 기준일(테스트 주입용). None이면 `threads_publish_date()`.

    Returns:
        실제로 파일을 쓴 경우에만 True. 날짜 불일치로 건너뛰면 False.
    """
    target = path if path is not None else THREADS_EXPORT_PATH
    ref = publish_date or threads_publish_date()
    if board.fortune_date != ref:
        logger.info(
            "오늘의 운세 export 건너뜀 — 게시 기준일(%s) 보드가 아니다: %s", ref,
            board.fortune_date,
        )
        return False
    try:
        tmp = target.with_suffix(".txt.tmp")
        tmp.write_text(render_threads_text(board), encoding="utf-8")
        tmp.replace(target)
        return True
    except OSError as exc:
        logger.warning("오늘의 운세 스레드 export 실패 path=%s err=%s", target, exc)
        return False
