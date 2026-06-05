"""manse_calibration skeleton: importable now, implemented in Phase 4."""

from __future__ import annotations

import pytest
import saju_manse_calibration as cal


def test_package_is_skeleton() -> None:
    assert cal.STATUS == "skeleton"


def test_entry_points_exist_but_unimplemented() -> None:
    with pytest.raises(NotImplementedError):
        cal.select_validation_periods(None, None)
    with pytest.raises(NotImplementedError):
        cal.generate_questions([])
    with pytest.raises(NotImplementedError):
        cal.score_feedback("positive", 2)
