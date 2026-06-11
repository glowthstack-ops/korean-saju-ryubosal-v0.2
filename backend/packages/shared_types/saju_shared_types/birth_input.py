"""Input schemas (codex spec §3)."""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TimeCalculationOptions(BaseModel):
    apply_true_solar_time: bool = True
    apply_daylight_saving: bool = True
    apply_longitude_correction: bool = True
    apply_equation_of_time: bool = True

    day_boundary_rule: Literal["23:00", "00:00"] = "23:00"
    ja_hour_rule: Literal["standard_zi", "early_late_zi", "none"] = "standard_zi"

    compare_standard_and_true_solar: bool = True


class BirthInput(BaseModel):
    calendar_type: Literal["solar", "lunar"] = "solar"
    is_leap_month: bool | None = None

    birth_date: date
    birth_time: time | None = None
    birth_time_unknown: bool = False

    birth_place_name: str
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None  # IANA tz, e.g. "Asia/Seoul"

    gender: Literal["male", "female", "unknown"] | None = None
    daewoon_direction_basis: Literal["gender_yinyang", "manual"] = "gender_yinyang"
    manual_daewoon_direction: Literal["forward", "backward"] | None = None

    # Optional anchor for current-age-dependent luck (세운/월운/일운). When omitted
    # the engine stays fully deterministic and returns only the 대운 table.
    reference_date: date | None = None

    time_options: TimeCalculationOptions = Field(default_factory=TimeCalculationOptions)

    # Twin/minute adjustment. ``twin_shift`` is a minute offset applied to the
    # calculation basis only; omitted/zero keeps the original chart exactly.
    chart_variant: Literal["original", "twin_adjusted"] = "original"
    twin_shift: int = 0

    @model_validator(mode="after")
    def _check_lunar(self) -> BirthInput:
        if self.calendar_type == "lunar" and self.is_leap_month is None:
            # Leap-month ambiguity must be resolved before lunar conversion.
            self.is_leap_month = False
        return self
