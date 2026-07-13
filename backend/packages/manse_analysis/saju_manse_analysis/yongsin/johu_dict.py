"""궁통보감 조후용신표 로더 — 컴파일 스냅샷 우선, 원본 폴백, 부재 시 None(graceful).

일간×월지 → canonical climate need 셀(primary/secondary/avoid/climate_axis).
천간 단위인 것이 핵심(壬≠癸 — 2026-07-13 데굴님 감수 P4·확정). reviewed:true 는
'canonical 필요기운 검토 완료'만 의미하며 최종 용신 확정·작동성·타 축 우선을 뜻하지
않는다. 사전이 없으면 호출부는 기존 한습/조열 하드코딩 동작으로 폴백(fresh-clone graceful).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
_COMPILED_DEFAULT = _BACKEND / "compiled"
_DICTS_DEFAULT = _BACKEND / "dictionaries"
JOHU_YONGSIN_VERSION = "0.2.0"

# 셀 구조: {"primary": [천간], "secondary": [...], "avoid": [...], "climate_axis": str}
JohuCell = dict[str, object]


@lru_cache(maxsize=4)
def load_johu_table(
    compiled_dir: Path = _COMPILED_DEFAULT, dictionaries_dir: Path = _DICTS_DEFAULT
) -> dict[str, dict[str, JohuCell]] | None:
    """조후용신표 entries(일간→월지→셀). 스냅샷·원본 모두 없으면 None."""
    snapshot = compiled_dir / f"johu_yongsin_v{JOHU_YONGSIN_VERSION}.json"
    source = dictionaries_dir / "johu_yongsin.json"
    for path in (snapshot, source):
        if path.exists():
            raw = json.loads(path.read_text("utf-8"))
            return raw.get("entries")
    return None
