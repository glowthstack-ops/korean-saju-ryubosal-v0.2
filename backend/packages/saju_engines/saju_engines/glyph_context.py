"""글자 컨텍스트 — 운 기간 라벨('YYYY'/'YYYY-MM') → 세운·월운 글자와 원국 재현(복음) 자리.

직장 이력 캘리브레이션 P1(EMPLOYMENT_HISTORY_CALIBRATION.md §3-1). 십성 그룹 지문이 뭉개는 글자
반복(亥 4건 vs 子 0건)을 구분하기 위해 후보·원장 행 양쪽 지문에 같은 규칙으로 글자를 붙인다.
모든 글자는 만세력 결과(ManseV2Result)에서 읽는다 — 손 계산 없음.

전월 글자는 **넣지 않는다**: 절기월은 순환하므로 직전 달의 간지는 당월 간지로 결정된다(亥월의
전월은 언제나 戌월). 정보가 0이고 중복 가산만 되므로, '움직이는 달 = 성사 달 − 1'은 P2 서술에서만
쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.life_event import SignalFingerprint
from saju_shared_types.manse_result import ManseV2Result

from .luck_structure_tags import luck_structure_tags, natal_structure_profile
from .pattern_transit import LuckGlyph, daewoon_ganji_by_year
from .structure_patterns import detect_structure_patterns

#: 원국 자리 키 — natal_echo 표기('wolwoon_branch=month_branch')에 쓴다.
NATAL_POSITIONS: tuple[str, ...] = (
    "year_stem", "year_branch", "month_stem", "month_branch",
    "day_stem", "day_branch", "hour_stem", "hour_branch",
)


@dataclass(frozen=True)
class GlyphContext:
    """원국 글자 + 라벨별 세운·월운 글자(한 ManseV2Result 에서 추출)."""

    natal: dict[str, str] = field(default_factory=dict)        # NATAL_POSITIONS → 글자
    sewoon: dict[str, tuple[str, str]] = field(default_factory=dict)   # 'YYYY' → (천간, 지지)
    wolwoon: dict[str, tuple[str, str]] = field(default_factory=dict)  # 'YYYY-MM' → (천간, 지지)
    # 확장 차원(2026-11-18, `extended=True` 일 때만 채움 — 기본은 비어 있어 기존 동작과 같다).
    daewoon: dict[str, tuple[str, str]] = field(default_factory=dict)  # 'YYYY' → 관할 대운 글자
    structure: dict[str, list[str]] = field(default_factory=dict)      # 라벨 → 구조 태그(접두 포함)

    @classmethod
    def from_result(cls, result: ManseV2Result, *, extended: bool = False) -> GlyphContext:
        """만세력 결과의 원국·대운표 세운·월운 목록에서 글자 표를 만든다.

        `extended=True` 면 관할 대운 글자와 운 구조 태그(대운·세운·월운 층별, 직전 층 대비)도
        채운다. 구조 태그는 세운 전 연도 × 패턴 상태 평가라 비용이 있어 측정·적재에서만 켠다.
        """
        natal: dict[str, str] = {}
        p = result.pillars
        if p is not None:
            for name in ("year", "month", "day", "hour"):
                pillar = getattr(p, name, None)
                if pillar is None:
                    continue
                natal[f"{name}_stem"] = pillar.stem
                natal[f"{name}_branch"] = pillar.branch
        sewoon: dict[str, tuple[str, str]] = {}
        wolwoon: dict[str, tuple[str, str]] = {}
        lc = result.luck_cycles
        if lc is not None:
            for dw in lc.daewoon_table:
                for sw in dw.sewoon:
                    sewoon.setdefault(sw.label[:4], (sw.stem, sw.branch))
            for m in lc.monthly_luck:
                wolwoon.setdefault(m.label[:7], (m.stem, m.branch))
        if not extended:
            return cls(natal=natal, sewoon=sewoon, wolwoon=wolwoon)
        daewoon = {str(y): (g[0], g[1]) for y, g in daewoon_ganji_by_year(result).items()}
        structure = _structure_tags(result, daewoon, sewoon, wolwoon)
        return cls(
            natal=natal, sewoon=sewoon, wolwoon=wolwoon, daewoon=daewoon, structure=structure,
        )

    def glyphs_for(self, period: str) -> dict[str, str]:
        """기간 라벨의 글자. 'YYYY-MM'은 월운 두 칸 + 관할 세운 두 칸, 'YYYY'는 세운 두 칸.

        1월 라벨(丑월)은 전년 세운 관할이다(절기년). 모르는 라벨은 빈 dict(규칙 11 — 미입력 무해).
        """
        out: dict[str, str] = {}
        if len(period) >= 7 and period[4] == "-":
            year = int(period[:4]) - (1 if period[5:7] == "01" else 0)
            wm = self.wolwoon.get(period[:7])
            if wm:
                out["wolwoon_stem"], out["wolwoon_branch"] = wm
        else:
            try:
                year = int(period[:4])
            except ValueError:
                return out
        sw = self.sewoon.get(str(year))
        if sw:
            out["sewoon_stem"], out["sewoon_branch"] = sw
        dw = self.daewoon.get(str(year))
        if dw:
            out["daewoon_stem"], out["daewoon_branch"] = dw
        return out

    def natal_echo(self, glyphs: dict[str, str]) -> list[str]:
        """운 글자가 원국 같은 종류(천간↔천간, 지지↔지지) 자리와 같으면 'luck=natal' 표기."""
        out: list[str] = []
        for lk, g in glyphs.items():
            kind = "stem" if lk.endswith("_stem") else "branch"
            for nk in NATAL_POSITIONS:
                if nk.endswith(kind) and self.natal.get(nk) == g:
                    out.append(f"{lk}={nk}")
        return out

    def with_glyphs(self, fp: SignalFingerprint, period: str) -> SignalFingerprint:
        """지문에 글자·원국 재현을 채운 복사본(이미 있으면 덮어쓴다)."""
        glyphs = self.glyphs_for(period)
        if not glyphs:
            return fp
        update: dict[str, object] = {"glyphs": glyphs, "natal_echo": self.natal_echo(glyphs)}
        month_level = len(period) >= 7 and period[4] == "-"
        tags = self.structure.get(period[:7] if month_level else period[:4])
        if tags is not None:
            update["structure"] = tags
        return fp.model_copy(update=update)


def _label_year(label: str) -> int:
    """라벨의 관할 세운 연도 — 1월 라벨(丑월)은 전년(절기년)."""
    return int(label[:4]) - (1 if len(label) >= 7 and label[5:7] == "01" else 0)


def _structure_tags(
    result: ManseV2Result,
    daewoon: dict[str, tuple[str, str]],
    sewoon: dict[str, tuple[str, str]],
    wolwoon: dict[str, tuple[str, str]],
) -> dict[str, list[str]]:
    """라벨별 구조 태그 — 'YYYY'는 대운·세운 층, 'YYYY-MM'은 대운·세운·월운 층(접두 dw:/sw:/wm:)."""
    natal_patterns = detect_structure_patterns(result)
    profile = natal_structure_profile(result, natal_patterns)
    if profile is None:
        return {}
    year_tags: dict[str, list[str]] = {}

    def _year(y: str) -> list[str]:
        if y in year_tags:
            return year_tags[y]
        stack: list[LuckGlyph] = []
        tags: list[str] = []
        dw = daewoon.get(y)
        if dw:
            stack.append(LuckGlyph("daewoon", dw[0], dw[1]))
            tags += [f"dw:{t}" for t in luck_structure_tags(result, profile, natal_patterns, stack)]
        sw = sewoon.get(y)
        if sw:
            stack = [*stack, LuckGlyph("year", sw[0], sw[1])]
            tags += [f"sw:{t}" for t in luck_structure_tags(result, profile, natal_patterns, stack)]
        year_tags[y] = tags
        return tags

    out: dict[str, list[str]] = {}
    # 세운 전 연도를 미리 돌지 않는다 — 월운이 있는 해와 그 앞뒤로 쓰이는 연도만 필요 시 계산한다.
    for label, (ms, mb) in wolwoon.items():
        y = str(_label_year(label))
        stack = []
        if daewoon.get(y):
            stack.append(LuckGlyph("daewoon", *daewoon[y]))
        if sewoon.get(y):
            stack.append(LuckGlyph("year", *sewoon[y]))
        stack.append(LuckGlyph("month", ms, mb))
        month_tags = [
            f"wm:{t}" for t in luck_structure_tags(result, profile, natal_patterns, stack)
        ]
        out[label] = [*_year(y), *month_tags]
        out.setdefault(y, _year(y))
    return out
