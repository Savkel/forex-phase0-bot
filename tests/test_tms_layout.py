"""Tests for coordinate-anchored extraction and the text/layout cross-check.

The flattened text layer cannot be trusted to pair a symbol with its rates: a
reordering of that layer silently produces wrong pairs. These tests pin that the
association comes from geometry and that any disagreement fails closed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.forex.tms_layout import (
    LayoutRow,
    TmsLayoutError,
    Token,
    rows_from_tokens,
)
from bot.forex.tms_swap import SwapRow, TmsParseError, require_layout_agreement

FIXTURES = Path(__file__).parent / "fixtures" / "tms"


def _tokens(name: str = "tokens_2026_07_27.json"):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [Token(page=p, x0=x0, x1=x1, y0=y0, text=t) for p, x0, x1, y0, t in raw]


# --- geometry establishes the association ------------------------------------

def test_layout_rows_match_the_printed_table():
    rows = {r.instrument: r for r in rows_from_tokens(_tokens())}
    assert len(rows) == 64
    assert rows["EURUSD.pro"].long_pct == pytest.approx(-2.41)
    assert rows["EURUSD.pro"].short_pct == pytest.approx(0.44)


def test_layout_supports_a_block_continued_across_a_page_break():
    """NZDUSD.pro is the first row of the headerless continuation on page 2."""
    rows = {r.instrument: r for r in rows_from_tokens(_tokens())}
    assert rows["NZDUSD.pro"].long_pct == pytest.approx(-2.10)
    assert rows["NZDUSD.pro"].short_pct == pytest.approx(0.14)


def test_layout_stops_before_the_equities_table():
    rows = rows_from_tokens(_tokens())
    assert not [r for r in rows if "_CFD." in r.instrument]


def test_row_order_in_the_token_stream_does_not_change_the_pairing():
    """Order is not evidence; geometry is. Shuffling tokens must not move a rate."""
    tokens = _tokens()
    shuffled = tokens[::-1]
    assert rows_from_tokens(shuffled) == rows_from_tokens(tokens)


# --- adversarial geometry ----------------------------------------------------

_ANCHORS = [
    Token(0, 126.0, 179.5, 622.7, "Instrument"),
    Token(0, 253.4, 304.0, 622.7, "Long swap"),
    Token(0, 398.1, 451.8, 622.7, "Short swap"),
]


def _row(y, symbol=("EURUSD.pro", 124.0, 181.6), long=("1.00%", 263.8, 293.9),
         short=("-1.00%", 408.3, 441.8)):
    out = []
    for text, x0, x1 in (symbol, long, short):
        if text is not None:
            out.append(Token(0, x0, x1, y, text))
    return out


def test_well_formed_row_is_accepted():
    assert rows_from_tokens(_ANCHORS + _row(600.0)) == [LayoutRow("EURUSD.pro", 1.0, -1.0)]


def test_row_with_a_missing_symbol_cell_fails_closed():
    with pytest.raises(TmsLayoutError, match="exactly one"):
        rows_from_tokens(_ANCHORS + _row(600.0, symbol=(None, 0, 0)))


def test_row_with_a_missing_rate_cell_fails_closed():
    with pytest.raises(TmsLayoutError, match="exactly one"):
        rows_from_tokens(_ANCHORS + _row(600.0, short=(None, 0, 0)))


def test_merged_row_holding_two_symbols_fails_closed():
    row = _row(600.0) + [Token(0, 124.0, 181.6, 600.0, "GBPUSD.pro")]
    with pytest.raises(TmsLayoutError, match="exactly one"):
        rows_from_tokens(_ANCHORS + row)


def test_rate_shifted_out_of_every_column_fails_closed():
    with pytest.raises(TmsLayoutError, match="overlaps 0 columns"):
        rows_from_tokens(_ANCHORS + _row(600.0, long=("1.00%", 330.0, 360.0)))


def test_rate_straddling_two_columns_fails_closed():
    anchors = [
        Token(0, 126.0, 179.5, 622.7, "Instrument"),
        Token(0, 200.0, 300.0, 622.7, "Long swap"),
        Token(0, 280.0, 380.0, 622.7, "Short swap"),
    ]
    with pytest.raises(TmsLayoutError, match="overlaps 2 columns"):
        rows_from_tokens(anchors + _row(600.0, long=("1.00%", 285.0, 295.0)))


def test_data_before_any_column_header_fails_closed():
    with pytest.raises(TmsLayoutError, match="before any column header"):
        rows_from_tokens(_row(600.0))


def test_partial_column_header_fails_closed():
    with pytest.raises(TmsLayoutError, match="partial column header"):
        rows_from_tokens(_ANCHORS[:2] + _row(600.0))


# --- the cross-check ---------------------------------------------------------

def test_agreement_passes_when_text_and_layout_match():
    text_rows = (SwapRow("EURUSD.pro", 1.0, -1.0), SwapRow("GBPUSD.pro", 2.0, -2.0))
    layout_rows = [LayoutRow("EURUSD.pro", 1.0, -1.0), LayoutRow("GBPUSD.pro", 2.0, -2.0)]
    require_layout_agreement(text_rows, layout_rows)


def test_mispaired_text_rows_are_rejected_by_the_cross_check():
    """The reviewer's I,I,P,P corruption: same symbols, same numbers, wrong pairing."""
    text_rows = (SwapRow("EURUSD.pro", 1.0, 2.0), SwapRow("GBPUSD.pro", -1.0, -2.0))
    layout_rows = [LayoutRow("EURUSD.pro", 1.0, -1.0), LayoutRow("GBPUSD.pro", 2.0, -2.0)]
    with pytest.raises(TmsParseError, match="disagree"):
        require_layout_agreement(text_rows, layout_rows)


def test_merged_symbol_runs_mispair_in_text_and_are_caught_by_geometry():
    """End-to-end reproduction of the reviewer's I,I,P,P corruption.

    Two blocks whose symbol columns land adjacently merge into one instrument run
    and one 2k value run. The text parser splits that run in half and pairs every
    symbol with another symbol's rate - silently, with the row count unchanged.
    Geometry disagrees, so the document is refused.
    """
    from bot.forex.tms_swap import parse_swap_schedule

    corrupted_text = (
        "Swap Points Table\n\nValid from 2024.01.08 – 2024.01.14 Published swap points are\n"
        "calculated in percentage points per annum.\n\n"
        # a captioned block first, which is what establishes the split convention
        "Instrument\nZZZUSD.pro\n\nLong swap\n9.00%\n\nShort swap\n-9.00%\n\n"
        # then the two merged blocks: one symbol run, one 2k value run
        "AAAUSD.pro\nBBBUSD.pro\nCCCUSD.pro\nDDDUSD.pro\n\n"
        "1.00%\n2.00%\n-1.00%\n-2.00%\n3.00%\n4.00%\n-3.00%\n-4.00%\n"
    )
    text_rows = parse_swap_schedule(corrupted_text).rows
    # The corruption is silent in the text layer: rows parse, numbers look normal.
    by_symbol = {r.instrument: (r.long_pct, r.short_pct) for r in text_rows}
    assert by_symbol["AAAUSD.pro"] == (1.00, 3.00)  # truth is (1.00, -1.00)

    truth = [
        LayoutRow("ZZZUSD.pro", 9.00, -9.00),
        LayoutRow("AAAUSD.pro", 1.00, -1.00),
        LayoutRow("BBBUSD.pro", 2.00, -2.00),
        LayoutRow("CCCUSD.pro", 3.00, -3.00),
        LayoutRow("DDDUSD.pro", 4.00, -4.00),
    ]
    with pytest.raises(TmsParseError, match="disagree"):
        require_layout_agreement(text_rows, truth)


def test_symbol_present_in_only_one_extraction_is_rejected():
    text_rows = (SwapRow("EURUSD.pro", 1.0, -1.0), SwapRow("GBPUSD.pro", 2.0, -2.0))
    layout_rows = [LayoutRow("EURUSD.pro", 1.0, -1.0)]
    with pytest.raises(TmsParseError, match="disagree"):
        require_layout_agreement(text_rows, layout_rows)


# --- wiring: the gate must actually run on real PDF bytes --------------------

def _mini_pdf(rows) -> bytes:
    """A minimal one-page PDF laying out a swap table at explicit coordinates."""
    def esc(s):
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    ops = ["BT", "/F1 9 Tf"]
    for x, y, text in rows:
        ops.append(f"1 0 0 1 {x} {y} Tm ({esc(text)}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n".encode()
        + b"%%EOF\n"
    )
    return bytes(out)


_PDF_ROWS = [
    (120, 700, "Swap Points Table"),
    (120, 680, "Valid from 2024.01.08 - 2024.01.14 Published swap points are"),
    (120, 665, "calculated in percentage points per annum."),
    # captions staggered by 1pt so pdfminer keeps each with its own column
    (120, 640, "Instrument"), (260, 639, "Long swap"), (400, 638, "Short swap"),
    (120, 620, "AAAUSD.pro"), (265, 620, "1.00%"), (405, 620, "-1.00%"),
    (120, 600, "BBBUSD.pro"), (265, 600, "2.00%"), (405, 600, "-2.00%"),
]


def test_parse_swap_document_runs_end_to_end_over_real_pdf_bytes():
    from bot.forex.tms_swap import parse_swap_document

    schedule = parse_swap_document(_mini_pdf(_PDF_ROWS))
    rows = {r.instrument: (r.long_pct, r.short_pct) for r in schedule.rows}
    assert rows == {"AAAUSD.pro": (1.0, -1.0), "BBBUSD.pro": (2.0, -2.0)}


def test_parse_swap_document_raises_when_layout_contradicts_text(monkeypatch):
    """Proves the gate is wired in, not merely defined."""
    import bot.forex.tms_swap as mod

    monkeypatch.setattr(
        "bot.forex.tms_layout.rows_from_tokens",
        lambda tokens: [LayoutRow("AAAUSD.pro", 9.0, -9.0), LayoutRow("BBBUSD.pro", 2.0, -2.0)],
    )
    with pytest.raises(TmsParseError, match="disagree"):
        mod.parse_swap_document(_mini_pdf(_PDF_ROWS))


def test_rows_closer_than_the_row_tolerance_are_not_merged():
    """Pins row identity: adjacent printed rows must stay separate."""
    tokens = _ANCHORS + _row(600.0) + [
        Token(0, 124.0, 181.6, 586.0, "GBPUSD.pro"),
        Token(0, 263.8, 293.9, 586.0, "2.00%"),
        Token(0, 408.3, 441.8, 586.0, "-2.00%"),
    ]
    assert rows_from_tokens(tokens) == [
        LayoutRow("EURUSD.pro", 1.0, -1.0),
        LayoutRow("GBPUSD.pro", 2.0, -2.0),
    ]


def test_unrecognised_cells_spanning_data_columns_fail_closed():
    """A merged/odd-format data row must not be silently skipped by BOTH extractions."""
    merged = [Token(0, 124.0, 441.8, 600.0, "EURUSD.pro 1.00% -1.00%")]
    with pytest.raises(TmsLayoutError, match="must not be skipped"):
        rows_from_tokens(_ANCHORS + merged)
