"""Pillar (원국) schemas (codex spec §5.2, extended with weight + ten god)."""

from __future__ import annotations

from pydantic import BaseModel


class HiddenStem(BaseModel):
    stem: str
    element: str
    type: str  # main / middle / residual
    weight: float
    ten_god: str


class Pillar(BaseModel):
    stem: str
    branch: str
    ganji: str

    stem_element: str
    branch_element: str
    stem_yinyang: str
    branch_yinyang: str

    stem_ten_god: str
    branch_main_ten_god: str

    twelve_unseong: str
    hidden_stems: list[HiddenStem]
    naeum: str | None = None
    gongmang_hit: bool = False
    palace: str | None = None


class FourPillarsResult(BaseModel):
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar | None = None

    day_master: str
    gongmang_branches: list[str] = []
    trace: dict = {}
    warnings: list[str] = []
