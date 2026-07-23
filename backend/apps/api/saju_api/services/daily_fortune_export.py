"""오늘의 운세 스레드(Threads) 업로드용 텍스트 export (2026-07-23 데굴님 지시).

보드 생성·교정 저장 시마다 리포 최상위에 고정 파일명으로 갱신한다. 최상단에
대상 날짜를 기록해 어느 날짜의 내용인지 확인할 수 있게 한다. 커밋 제외 대상
(.gitignore 등재) — 실패해도 서비스 흐름을 막지 않는다(로그만).
"""

from __future__ import annotations

import logging
from pathlib import Path

from saju_shared_types.daily_fortune import DailyFortuneBoard

logger = logging.getLogger(__name__)

# 리포 최상위 고정 파일명 — 날짜가 바뀌어도 같은 파일을 덮어쓴다.
_REPO_ROOT = Path(__file__).resolve().parents[5]
THREADS_EXPORT_PATH = _REPO_ROOT / "오늘의운세.txt"

_MEDALS = ("🥇", "🥈", "🥉", "🏅", "🏅")
_SLOT_LABEL = {"good": "좋은 흐름", "caution": "주의", "support": "도움"}


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
    for f in board.fortunes:
        lines.append(f"■ {f.ilju_ko}일주")
        lines.append(f"{f.headline}")
        for ev in f.events:
            label = _SLOT_LABEL.get(ev.slot, ev.slot)
            lines.append(f"- {label}: {ev.phrase} ({ev.probability}%)")
        lines.append(f"- 행운의 장소: {f.lucky_place.phrase}")
        if f.lotto_phrase:
            lines.append(f"- {f.lotto_phrase}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_threads_export(
    board: DailyFortuneBoard, path: Path = THREADS_EXPORT_PATH
) -> bool:
    """스레드용 텍스트 파일 갱신(원자적 교체). 실패해도 예외를 전파하지 않는다."""
    try:
        tmp = path.with_suffix(".txt.tmp")
        tmp.write_text(render_threads_text(board), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError as exc:
        logger.warning("오늘의 운세 스레드 export 실패 path=%s err=%s", path, exc)
        return False
