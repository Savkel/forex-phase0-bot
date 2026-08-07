"""Coordinate-anchored extraction of TMS swap-point tables.

The flattened text layer discards position, so pairing a symbol with its rates
there rests entirely on token ORDER. Any reordering of the text layer silently
produces wrong pairs that look completely normal. This module establishes the
association independently, from PDF layout geometry:

- row identity comes from y-position, not token order;
- the symbol, long-rate and short-rate columns are anchored by the printed
  column headers and matched by x-overlap;
- anything ambiguous - a row missing a cell, a token overlapping no column or
  two columns, data appearing before any header - raises.

Nothing here inspects a rate's value, sign or magnitude, or looks for a
particular instrument.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class TmsLayoutError(Exception):
    """The page geometry does not determine a symbol/rate association."""


@dataclass(frozen=True)
class Token:
    page: int
    x0: float
    x1: float
    y0: float
    text: str


@dataclass(frozen=True)
class LayoutRow:
    instrument: str
    long_pct: float
    short_pct: float


_INSTRUMENT = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{1,14}(?:\.[a-z]{2,5})?$")
_PERCENT = re.compile(r"^-?\d+[.,]\d+%$")
_H_INSTRUMENT = re.compile(r"^instrument$", re.IGNORECASE)
_H_LONG = re.compile(r"^(?:long swap|długa pozycja)$", re.IGNORECASE)
_H_SHORT = re.compile(r"^(?:short swap|krótka pozycja)$", re.IGNORECASE)
# The equities table repeats a `Symbol` column header at a different x anchor and
# carries a third value column; the FX table ends there.
_H_EQUITIES = re.compile(r"^symbol$", re.IGNORECASE)

_ROW_TOLERANCE = 3.0


def tokens_from_pdf(data: bytes) -> List[Token]:
    """Adapter: pdfminer text lines with their bounding boxes."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer, LTTextLine

    out: List[Token] = []
    for page_no, page in enumerate(extract_pages(io.BytesIO(data), laparams=LAParams())):
        for element in page:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                text = line.get_text().strip()
                if text:
                    out.append(Token(page_no, line.x0, line.x1, line.y0, text))
    return out


def _group_rows(tokens: Sequence[Token]) -> List[List[Token]]:
    ordered = sorted(tokens, key=lambda t: (t.page, -t.y0, t.x0))
    rows: List[List[Token]] = []
    for token in ordered:
        if rows and rows[-1][0].page == token.page and abs(rows[-1][0].y0 - token.y0) <= _ROW_TOLERANCE:
            rows[-1].append(token)
        else:
            rows.append([token])
    return rows


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def rows_from_tokens(tokens: Iterable[Token]) -> List[LayoutRow]:
    """Associate symbols with rates through column geometry. Fail-closed."""
    grouped = _group_rows(list(tokens))
    anchors: Optional[Dict[str, Tuple[float, float]]] = None
    out: List[LayoutRow] = []

    for row in grouped:
        if any(_H_EQUITIES.match(t.text) for t in row):
            break

        header = {}
        for token in row:
            for key, pattern in (("i", _H_INSTRUMENT), ("l", _H_LONG), ("s", _H_SHORT)):
                if pattern.match(token.text):
                    header[key] = (token.x0, token.x1)
        if len(header) == 3:
            anchors = header
            continue
        if header:
            raise TmsLayoutError(
                f"partial column header on page {row[0].page} "
                f"(found {sorted(header)}): column anchors are not determined"
            )

        symbols = [t for t in row if _INSTRUMENT.match(t.text)]
        values = [t for t in row if _PERCENT.match(t.text)]
        if not symbols and not values:
            # A row with nothing recognised is prose - unless it sits inside the
            # data columns, in which case it is a data row whose cells merged or
            # whose formatting is unknown. Skipping it would drop an instrument
            # silently, and the text extraction shares these same predicates, so
            # the cross-check could not catch it either.
            # Spanning two or more data columns is what distinguishes a data row
            # from a single-column section caption such as "Equities CFD'S".
            if anchors is not None:
                spanned = {
                    k
                    for t in row
                    for k in ("i", "l", "s")
                    if _overlap((t.x0, t.x1), anchors[k]) > 0
                }
                if len(spanned) >= 2:
                    raise TmsLayoutError(
                        f"unrecognised token(s) {[t.text for t in row]!r} spanning "
                        f"{len(spanned)} data columns on page {row[0].page}: the row cannot be "
                        "read and must not be skipped"
                    )
            continue
        if anchors is None:
            raise TmsLayoutError(
                f"data row {[t.text for t in row]!r} appears before any column header"
            )

        placed: Dict[str, List[Token]] = {"i": [], "l": [], "s": []}
        for token in symbols + values:
            span = (token.x0, token.x1)
            hits = [k for k in ("i", "l", "s") if _overlap(span, anchors[k]) > 0]
            if len(hits) != 1:
                raise TmsLayoutError(
                    f"token {token.text!r} on page {token.page} overlaps {len(hits)} columns; "
                    "its column assignment is ambiguous"
                )
            placed[hits[0]].append(token)

        if not (len(placed["i"]) == 1 and len(placed["l"]) == 1 and len(placed["s"]) == 1):
            raise TmsLayoutError(
                f"row {[t.text for t in row]!r} on page {row[0].page} does not hold exactly one "
                f"symbol and two rates (got {len(placed['i'])}/{len(placed['l'])}/{len(placed['s'])})"
            )
        symbol = placed["i"][0]
        long_tok, short_tok = placed["l"][0], placed["s"][0]
        if not _INSTRUMENT.match(symbol.text):
            raise TmsLayoutError(f"symbol column holds a non-symbol token {symbol.text!r}")
        if not (_PERCENT.match(long_tok.text) and _PERCENT.match(short_tok.text)):
            raise TmsLayoutError(
                f"rate column holds a non-rate token for {symbol.text!r}"
            )
        out.append(
            LayoutRow(
                symbol.text,
                float(long_tok.text[:-1].replace(",", ".")),
                float(short_tok.text[:-1].replace(",", ".")),
            )
        )

    if not out:
        raise TmsLayoutError("no rows established from layout geometry")
    return out
