"""CareerMobilityModifier (Phase 6c) — 직업운 결과 길흉의 구조·맥락 보정.

career_mobility 자료 9-6·13-1·12를 favorability 채널(contributions['fav_adj'])과 reason_code로만
반영한다. 사건 종류·표시 점수(activation)는 바꾸지 않는다("사건 형성도 ≠ 길흉", 절대원칙 3·4).

- 특수직군 충형 길화(9-6): 의료·군경·법무·공직 등 긴장·통제 직군에서 충(沖)·형(刑)이
  활성되면 시험·승진·승급으로 길화 → favorability 가점.
- 천충지충 퇴직 리스크(13-1): 천간충 + 지지충 동시 + 관성(직업 축) 활성 → 이직 후보를
  퇴직·강제 이동 리스크로 분기 → favorability 감점 + CAREER_EXIT_RISK 태그(단정 금지).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from saju_shared_types.event_engine import EventCandidateV2, TenGod

_OFFICER = {TenGod.ZHENGGUAN, TenGod.QISHA}  # 관성(직업 축)


@dataclass
class CareerMobilityContext:
    """그 시점의 관계·구조·맥락(엔진이 채움 — 미입력은 보정 없음)."""

    present_gods: set[TenGod] = field(default_factory=set)
    activation_kinds: set[str] = field(default_factory=set)  # 'HAP'|'CHUNG'|'HYEONG'|'PA'|'HAE'
    stem_clash: bool = False  # 그 시점 천간충(운 천간 vs 원국 천간)
    branch_clash: bool = False  # 그 시점 지지충
    occupation_category: str | None = None  # O01~O18


class CareerMobilityModifier:
    """특수직군 충형 길화 + 천충지충 퇴직 리스크를 favorability로 보정한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """career_mobility_outcome.json을 로드해 규칙 파라미터를 읽는다."""
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "career_mobility_outcome.json").read_text(
                encoding="utf-8"
            )
        )
        soc = raw["special_occupation_clash"]
        self._soc_categories: set[str] = set(soc["occupation_categories"])
        self._soc_targets: set[str] = set(soc["target_events"])
        self._soc_kinds: set[str] = set(soc["trigger_kinds"])
        self._soc_delta: float = float(soc["fav_delta"])
        exit_ = raw["career_exit_double_clash"]
        self._exit_target: str = exit_["target_event"]
        self._exit_delta: float = float(exit_["fav_delta"])

    def apply(
        self, candidates: list[EventCandidateV2], ctx: CareerMobilityContext
    ) -> list[EventCandidateV2]:
        """직업운 후보에 특수직군 길화·퇴직 리스크 favorability 보정을 적용한다."""
        special = (
            ctx.occupation_category in self._soc_categories
            and bool(ctx.activation_kinds & self._soc_kinds)
        )
        double_clash_officer = (
            ctx.stem_clash and ctx.branch_clash and bool(ctx.present_gods & _OFFICER)
        )
        if not (special or double_clash_officer):
            return candidates

        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            delta = 0.0
            reasons = [*c.reason_codes]
            if special and ek in self._soc_targets:
                delta += self._soc_delta
                reasons.append("CAREER_SPECIAL_OCC_CLASH_BOOST")
            if double_clash_officer and ek == self._exit_target:
                delta += self._exit_delta
                reasons.append("CAREER_EXIT_RISK")
            if delta == 0.0:
                out.append(c)
                continue
            prev = c.contributions.get("fav_adj", 0.0)
            out.append(c.model_copy(update={
                "reason_codes": reasons,
                "contributions": {**c.contributions, "fav_adj": prev + delta},
            }))
        return out
