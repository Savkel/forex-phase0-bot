"""Tests for the OANDA TMS swap-point schedule parser.

The parser consumes the *text* of a published `Table of Swap Points` PDF (a
broker-native financing RATE schedule, not realized financing) and must fail
closed: any layout it does not fully understand raises rather than silently
dropping rows.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from bot.forex.tms_swap import (
    SwapSchedule,
    TmsDuplicateConflict,
    TmsParseError,
    parse_swap_schedule,
    resolve_duplicates,
)

FIXTURES = Path(__file__).parent / "fixtures" / "tms"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- validity interval -------------------------------------------------------

def test_parses_validity_interval_from_per_annum_header():
    s = parse_swap_schedule(_fixture("schedule_2026_07_27.txt"))
    assert s.valid_from == dt.date(2026, 7, 27)
    assert s.valid_to == dt.date(2026, 8, 2)


def test_parses_validity_interval_from_legacy_header():
    s = parse_swap_schedule(_fixture("schedule_2023_05_15.txt"))
    assert s.valid_from == dt.date(2023, 5, 15)
    assert s.valid_to == dt.date(2023, 5, 21)


def test_parses_validity_interval_longer_than_one_week():
    s = parse_swap_schedule(_fixture("schedule_2025_12_22.txt"))
    assert s.valid_from == dt.date(2025, 12, 22)
    assert s.valid_to == dt.date(2026, 1, 4)


def test_missing_validity_header_raises():
    with pytest.raises(TmsParseError):
        parse_swap_schedule("Swap Points Table\n\nEURUSD.pro\n\nLong swap\n1.00%\n")


# --- units -------------------------------------------------------------------

def test_units_per_annum_detected():
    assert parse_swap_schedule(_fixture("schedule_2026_07_27.txt")).units == "percent_per_annum"


def test_units_legacy_percentage_points_detected():
    assert parse_swap_schedule(_fixture("schedule_2023_05_15.txt")).units == "percentage_points"


# --- rows --------------------------------------------------------------------

def test_extracts_long_and_short_rates():
    rows = parse_swap_schedule(_fixture("schedule_2026_07_27.txt")).by_instrument
    assert rows["EURUSD.pro"].long_pct == pytest.approx(-2.41)
    assert rows["EURUSD.pro"].short_pct == pytest.approx(0.44)


def test_parses_continuation_block_that_has_no_column_headers():
    rows = parse_swap_schedule(_fixture("schedule_2026_07_27.txt")).by_instrument
    assert rows["NZDUSD.pro"].long_pct == pytest.approx(-2.10)
    assert rows["NZDUSD.pro"].short_pct == pytest.approx(0.14)


def test_preserves_account_variant_suffixes_exactly():
    rows = parse_swap_schedule(_fixture("schedule_2023_05_15.txt")).by_instrument
    for symbol in ("EURUSD", "EURUSD.pro", "EURUSD.std", "EURUSD.stp"):
        assert symbol in rows
    assert rows["EURUSD"].long_pct == pytest.approx(-3.40)
    assert rows["EURUSD.pro"].long_pct == pytest.approx(-2.80)


def test_stops_before_the_equities_section():
    rows = parse_swap_schedule(_fixture("schedule_2026_07_27.txt")).by_instrument
    assert not [k for k in rows if "_CFD." in k]


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("schedule_2023_05_15.txt", 132),
        ("schedule_2025_12_22.txt", 70),
        ("schedule_2026_07_27.txt", 64),
    ],
)
def test_row_count_is_pinned_per_fixture(fixture, expected):
    """A silently truncated block would change these counts."""
    assert len(parse_swap_schedule(_fixture(fixture)).rows) == expected


def test_pins_interior_and_tail_of_the_merged_value_block():
    rows = parse_swap_schedule(_fixture("schedule_2026_07_27.txt")).by_instrument
    assert rows["USDTRY.pro"].long_pct == pytest.approx(-50.22)
    assert rows["USDTRY.pro"].short_pct == pytest.approx(19.97)
    assert rows["USDZAR.pro"].long_pct == pytest.approx(-5.57)
    assert rows["USDZAR.pro"].short_pct == pytest.approx(0.71)


def test_crlf_input_parses_identically_to_lf():
    text = _fixture("schedule_2026_07_27.txt")
    assert parse_swap_schedule(text.replace("\n", "\r\n")).rows == parse_swap_schedule(text).rows


# --- fail-closed -------------------------------------------------------------

_HEAD = (
    "Swap Points Table\n\nValid from 2024.01.08 – 2024.01.14 Published swap points are\n"
    "calculated in percentage points per annum.\n\n"
)
_CAPTIONED = "Instrument\nEURUSD.pro\nGBPUSD.pro\n\nLong swap\n1.00%\n2.00%\n\nShort swap\n-1.00%\n-2.00%\n\n"


def test_mismatched_block_lengths_raise_rather_than_truncate():
    text = (
        _HEAD + "Instrument\nEURUSD.pro\nGBPUSD.pro\n\n"
        "Long swap\n1.00%\n2.00%\n\nShort swap\n-1.00%\n"
    )
    with pytest.raises(TmsParseError, match="align"):
        parse_swap_schedule(text)


def test_surplus_values_raise_rather_than_being_truncated():
    text = _HEAD + _CAPTIONED + "USDJPY.pro\nUSDCHF.pro\n\n3.00%\n4.00%\n-3.00%\n-4.00%\n5.00%\n"
    with pytest.raises(TmsParseError, match="align"):
        parse_swap_schedule(text)


def test_value_block_with_no_owning_instrument_run_raises():
    """A lost symbol column must fail closed, not yield a short schedule."""
    text = _HEAD + _CAPTIONED + "Long swap\n3.00%\n4.00%\n\nShort swap\n-3.00%\n-4.00%\n"
    with pytest.raises(TmsParseError, match="unclaimed|orphan"):
        parse_swap_schedule(text)


def test_uncaptioned_merged_block_without_an_established_convention_raises():
    """The [k longs][k shorts] split is only safe once a captioned block proves the layout."""
    text = _HEAD + "Instrument\nEURUSD.pro\nGBPUSD.pro\n\n1.00%\n2.00%\n-1.00%\n-2.00%\n"
    with pytest.raises(TmsParseError, match="convention"):
        parse_swap_schedule(text)


def test_duplicate_instrument_with_conflicting_values_raises():
    text = _HEAD + _CAPTIONED + "Instrument\nEURUSD.pro\n\nLong swap\n9.00%\n\nShort swap\n-9.00%\n"
    with pytest.raises(TmsParseError, match="conflicting"):
        parse_swap_schedule(text)


def test_duplicate_instrument_with_identical_values_is_collapsed():
    text = _HEAD + _CAPTIONED + "Instrument\nEURUSD.pro\n\nLong swap\n1.00%\n\nShort swap\n-1.00%\n"
    s = parse_swap_schedule(text)
    assert [r.instrument for r in s.rows] == ["EURUSD.pro", "GBPUSD.pro"]


def test_section_boundary_without_an_equities_table_raises():
    text = _HEAD + _CAPTIONED + "Symbol\n\nUSDJPY.pro\n\nLong swap\n1.00%\n\nShort swap\n-1.00%\n"
    with pytest.raises(TmsParseError, match="boundary"):
        parse_swap_schedule(text)


def test_schedule_with_no_parsable_rows_raises():
    text = (
        "Swap Points Table\n\nValid from 2024.01.08 – 2024.01.14 Published swap points are\n"
        "calculated in percentage points per annum.\n\nInstrument\n\n"
    )
    with pytest.raises(TmsParseError):
        parse_swap_schedule(text)


# --- provenance --------------------------------------------------------------

def test_records_source_url_and_sha256():
    s = parse_swap_schedule(
        _fixture("schedule_2026_07_27.txt"), source_url="https://example/x.pdf", sha256="ab" * 32
    )
    assert s.source_url == "https://example/x.pdf"
    assert s.sha256 == "ab" * 32


# --- duplicates --------------------------------------------------------------

def _schedule(valid_from: dt.date, sha: str, rows) -> SwapSchedule:
    return SwapSchedule(
        valid_from=valid_from,
        valid_to=valid_from + dt.timedelta(days=6),
        units="percent_per_annum",
        rows=tuple(rows),
        source_url=None,
        sha256=sha,
    )


def test_identical_duplicates_resolve_to_one_schedule():
    text = _fixture("schedule_2026_07_27.txt")
    a = parse_swap_schedule(text, source_url="a.pdf", sha256="11" * 32)
    b = parse_swap_schedule(text, source_url="b.pdf", sha256="11" * 32)
    resolved = resolve_duplicates([a, b])
    assert len(resolved) == 1


def test_conflicting_duplicates_raise():
    a = parse_swap_schedule(_fixture("schedule_2026_07_27.txt"), sha256="11" * 32)
    b = parse_swap_schedule(_fixture("schedule_2026_07_27.txt"), sha256="22" * 32)
    b = SwapSchedule(
        valid_from=b.valid_from,
        valid_to=b.valid_to,
        units=b.units,
        rows=b.rows[:-1],
        source_url=b.source_url,
        sha256=b.sha256,
    )
    with pytest.raises(TmsDuplicateConflict):
        resolve_duplicates([a, b])
