"""Focused, offline validation of the acquired official calendar only."""
import csv
from datetime import date, timedelta
from hashlib import sha256
import io
from pathlib import Path

import pytest

from scripts.build_tokyo_calendar import (
    END, HOLIDAYS, ORDINARY, ROOT, START, calendar_bytes, classify,
    parse_holidays, save_new_or_identical, verified_source,
)


@pytest.fixture(scope="module")
def official():
    manifest, raw = verified_source()
    return manifest, raw, parse_holidays(raw)


@pytest.mark.parametrize("value", HOLIDAYS)
def test_ordinary_substitute_and_exceptional_holidays(official, value):
    day = date.fromisoformat(value)
    assert day in official[2]
    eligible, reason = classify(day, official[2])
    assert not eligible
    assert "cabinet_office_holiday:" in reason


@pytest.mark.parametrize("value", ORDINARY)
def test_ordinary_and_moved_from_dates_remain_eligible(official, value):
    assert classify(date.fromisoformat(value), official[2]) == (True, "")


@pytest.mark.parametrize("value", ["2014-12-31", "2015-01-02", "2024-01-02", "2024-01-03"])
def test_bank_year_end_closures_not_in_national_holiday_csv(official, value):
    day = date.fromisoformat(value)
    assert day not in official[2]
    assert classify(day, official[2]) == (False, "dec31_jan3_closure")


def test_weekend_and_overlapping_exclusion_reasons(official):
    assert classify(date(2023, 12, 30), official[2]) == (False, "weekend")
    assert classify(date(2023, 12, 31), official[2]) == (False, "weekend;dec31_jan3_closure")
    eligible, reason = classify(date(2023, 1, 1), official[2])
    assert not eligible
    assert reason.split(";")[0] == "weekend"
    assert "cabinet_office_holiday:" in reason
    assert reason.endswith("dec31_jan3_closure")


def test_full_contiguous_range_and_independent_rule(official):
    rows = list(csv.DictReader(io.StringIO(calendar_bytes(official[2]).decode("utf-8"))))
    assert len(rows) == (END - START).days + 1 == 3652
    for offset, row in enumerate(rows):
        day = START + timedelta(days=offset)
        assert row["jst_date"] == day.isoformat()
        expected = day.weekday() < 5 and day not in official[2] and (day.month, day.day) not in {(12, 31), (1, 1), (1, 2), (1, 3)}
        assert row["eligible"] == str(expected).lower()
        assert bool(row["exclusion_reason"]) == (not expected)


def test_source_identity_coverage_and_reproducibility(official):
    manifest, raw, holidays = official
    assert sha256(raw).hexdigest() == manifest["raw_csv"]["sha256"]
    assert min(holidays) == date(1955, 1, 1)
    assert max(holidays) == date(2027, 11, 23)
    generated = calendar_bytes(holidays)
    assert generated == calendar_bytes(dict(reversed(list(holidays.items()))))
    assert generated == (ROOT / "data/japan_calendar/tokyo_eligible_days_20140106_20240105.csv").read_bytes()


def test_source_rejects_missing_exception_and_duplicate(official):
    lines = official[1].decode("cp932").splitlines()
    missing = "\n".join(s for s in lines if not s.startswith("2019/5/1,"))
    with pytest.raises(ValueError, match="Missing ordinary/exceptional"):
        parse_holidays(missing.encode("cp932"))
    duplicated = "\n".join([*lines[:2], lines[1], *lines[2:]])
    with pytest.raises(ValueError, match="duplicate"):
        parse_holidays(duplicated.encode("cp932"))
    incomplete = "\n".join(s for s in lines if not s.startswith("2027/"))
    with pytest.raises(ValueError, match="every advertised year"):
        parse_holidays(incomplete.encode("cp932"))


def test_existing_artifacts_cannot_be_replaced(tmp_path):
    path = tmp_path / "calendar.csv"
    save_new_or_identical(path, b"original")
    save_new_or_identical(path, b"original")
    with pytest.raises(ValueError, match="Refusing"):
        save_new_or_identical(path, b"changed")
    assert path.read_bytes() == b"original"
