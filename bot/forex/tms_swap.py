"""Parser for OANDA TMS Brokers `Table of Swap Points` documents.

These are broker-native financing RATE schedules for the EU/TMS division: each
document prints a validity interval and, per instrument, an annualised long and
short rate. They are NOT realized financing - reconstructing an actual debit or
credit additionally requires the days-charged calendar, which TMS does not
publish (see the Terms and Conditions of brokerage services).

The parser is fail-closed by design: a block it cannot fully align raises
`TmsParseError` rather than silently dropping instruments. A silent omission
would look exactly like an instrument that was not quoted that week.

Symbol/rate pairing is NOT decided here. `parse_swap_document` cross-checks this
flattened parse against `bot.forex.tms_layout`, which establishes the association
from PDF layout geometry, and refuses on any disagreement. Text order alone can
silently mispair (two symbol columns landing adjacently merge into one run), so
the geometric corroboration is what makes the output trustworthy.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class TmsParseError(Exception):
    """The document does not match a layout this parser fully understands."""


class TmsDuplicateConflict(Exception):
    """Two documents claim the same validity interval with different content."""


@dataclass(frozen=True)
class SwapRow:
    instrument: str
    long_pct: float
    short_pct: float


@dataclass(frozen=True)
class SwapSchedule:
    valid_from: dt.date
    valid_to: dt.date
    units: str
    rows: Tuple[SwapRow, ...]
    source_url: Optional[str] = None
    sha256: Optional[str] = None

    @property
    def by_instrument(self) -> Dict[str, SwapRow]:
        return {r.instrument: r for r in self.rows}


# English and Polish editions of the same document carry the same table under a
# different validity caption.
_HEADER = re.compile(
    r"(?:Valid\s+from|Obowiązuje\s+w\s+dniach)\s*"
    r"(\d{4})\.(\d{2})\.(\d{2})\s*\D{1,4}?\s*(\d{4})\.(\d{2})\.(\d{2})"
)
# Units are established POSITIVELY from the preamble. Absence of evidence is not
# evidence of the legacy edition: `units` scales every rate, so an undetermined
# preamble raises rather than defaulting.
_PER_ANNUM = re.compile(r"per\s+annum|w\s+skali\s+roku", re.IGNORECASE)
_LEGACY_UNITS = re.compile(r"percentage\s+points|punktach\s+procentowych", re.IGNORECASE)
# Published spreadsheet errors (EN and PL locales): the rate simply is not in the
# document and must never be inferred.
_SPREADSHEET_ERROR = re.compile(
    r"#(VALUE|REF|N/A|N/D|DIV/0|DZIEL/0|NAME|NAZWA|NUM|LICZBA|NULL|SPILL|CALC|ARG|ADR)[!?]",
    re.IGNORECASE,
)
# Instrument symbols are upper-case with an optional lower-case account/section
# suffix (.pro/.std/.stp/.cash). The upper-case base is what keeps prose lines
# such as "Instrument" or "Long swap" out of the instrument runs.
_INSTRUMENT = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{1,14}(?:\.[a-z]{2,5})?$")
_PERCENT = re.compile(r"^-?\d+[.,]\d+%$")
_CAPTION_LONG = re.compile(r"^(?:long swap|długa pozycja)$", re.IGNORECASE)
_CAPTION_SHORT = re.compile(r"^(?:short swap|krótka pozycja)$", re.IGNORECASE)
# Signatures of the equities/ETF table, which carries a third column ("additional
# cost of keeping a short position open") and must never be read as long/short
# pairs. The cut is only accepted when the discarded tail really is that table.
_EQUITIES_SIGNATURE = re.compile(
    r"Equities|Additional cost|Dodatkowy koszt|_CFD\.", re.IGNORECASE
)
# How far into the discarded tail the equities signature must appear. Scanning to
# EOF would be satisfied by any document that has an equities table anywhere,
# which is all of them - it would not test that the cut is at its start.
_BOUNDARY_LOOKAHEAD_LINES = 8
# The FOREX/indices/crypto table ends where the equities table begins; that one
# carries a third column and must not be parsed as long/short pairs. The `Symbol`
# column header is the reliable boundary: in the 2023 layout the "Equities CFD'S"
# caption floats *inside* the crypto value block, so cutting there would truncate
# a legitimate long/short run.
_SECTION_END = re.compile(r"^[ 	]*Symbol[ 	]*$", re.MULTILINE)
_SECTION_END_FALLBACK = re.compile(r"^[ 	]*Equities.*$", re.MULTILINE)


def _percent(token: str) -> float:
    return float(token[:-1].replace(",", "."))


def _runs(lines: Sequence[str]) -> List[Tuple[str, List[str]]]:
    """Group lines into instrument runs, value runs and column captions.

    Captions are kept (rather than ignored) because they are the only evidence
    that a document orders its values as [all longs][all shorts]; that evidence
    is what licenses splitting an uncaptioned continuation block in half.
    """
    out: List[Tuple[str, List[str]]] = []
    current: List[str] = []
    kind: Optional[str] = None

    def flush() -> None:
        nonlocal current, kind
        if current:
            out.append((kind, current))
        current = []
        kind = None

    for line in lines:
        if _CAPTION_LONG.match(line):
            flush()
            out.append(("CAP_L", [line]))
            continue
        if _CAPTION_SHORT.match(line):
            flush()
            out.append(("CAP_S", [line]))
            continue
        if _INSTRUMENT.match(line):
            this = "I"
        elif _PERCENT.match(line):
            this = "P"
        else:
            this = None
        if this is not None and this == kind:
            current.append(line)
            continue
        flush()
        if this:
            current = [line]
            kind = this
    flush()
    return out


def parse_swap_schedule(
    text: str, *, source_url: Optional[str] = None, sha256: Optional[str] = None
) -> SwapSchedule:
    """Parse the FLATTENED TEXT layer. NOT authoritative for symbol/rate pairing.

    Its pairing follows token order and can be silently wrong. Callers ingesting
    real documents must use `parse_swap_document`, which corroborates every row
    against layout geometry. This function is exposed for text-layer unit tests
    and as an implementation detail of `parse_swap_document`.
    """
    text = text.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))
    text = text.replace(chr(12), chr(10))  # form feed = page break, not a glued line
    headers = list(_HEADER.finditer(text))
    if not headers:
        raise TmsParseError("no 'Valid from <date> - <date>' validity header found")
    intervals = {h.groups() for h in headers}
    if len(intervals) > 1:
        raise TmsParseError(
            f"{len(intervals)} conflicting validity headers in one document; refusing to stamp "
            "rows with a guessed week"
        )
    header = headers[0]
    g = [int(x) for x in header.groups()]
    valid_from = dt.date(g[0], g[1], g[2])
    valid_to = dt.date(g[3], g[4], g[5])
    if valid_to < valid_from:
        raise TmsParseError(f"validity interval ends before it starts: {valid_from}..{valid_to}")

    # The preamble is everything from the header up to the first data value.
    preamble = text[header.start():]
    for m in re.finditer(r"^-?\d+[.,]\d+%$", preamble, re.MULTILINE):
        preamble = preamble[: m.start()]
        break
    per_annum = bool(_PER_ANNUM.search(preamble))
    legacy = bool(_LEGACY_UNITS.search(preamble))
    if per_annum:
        units = "percent_per_annum"
    elif legacy:
        units = "percentage_points"
    else:
        raise TmsParseError(
            "cannot establish units from the preamble: neither an annualised marker "
            "('per annum' / 'w skali roku') nor a legacy one ('percentage points' / "
            "'punktach procentowych') is present"
        )

    body = text[header.end():]

    # Scan for published spreadsheet errors across the WHOLE body, before any
    # truncation, so a bad cell below the section cut cannot hide.
    bad_cell = _SPREADSHEET_ERROR.search(body)
    if bad_cell is not None:
        raise TmsParseError(
            f"published spreadsheet error {bad_cell.group(0)!r}: the affected rate is not "
            "present in the document and must not be inferred"
        )

    boundaries = list(_SECTION_END.finditer(body))
    if len(boundaries) > 1:
        raise TmsParseError(
            f"{len(boundaries)} 'Symbol' section boundaries found; the equities boundary is "
            "ambiguous and the table would be truncated at a guess"
        )
    end = boundaries[0] if boundaries else _SECTION_END_FALLBACK.search(body)
    if end is not None:
        tail_lines = [ln for ln in body[end.start():].split("\n") if ln.strip()]
        window = "\n".join(tail_lines[:_BOUNDARY_LOOKAHEAD_LINES])
        if not _EQUITIES_SIGNATURE.search(window):
            raise TmsParseError(
                f"unexpected section boundary {tail_lines[0]!r}: the equities table does not "
                f"start within {_BOUNDARY_LOOKAHEAD_LINES} lines of the cut"
            )
        body = body[: end.start()]

    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    runs = _runs(lines)

    # --- structural integrity checks, independent of any value ----------------
    # (2) Caption completeness: a block carrying one column caption but not the
    #     other is a broken block, not a legitimate uncaptioned continuation.
    for i, (kind, _) in enumerate(runs):
        if kind == "CAP_L" and not any(k == "CAP_S" for k, _ in runs[i + 1: i + 4]):
            raise TmsParseError(
                "long-column caption without a matching short-column caption: the block is "
                "truncated and its values cannot be assigned"
            )
        if kind == "CAP_S" and not any(k == "CAP_L" for k, _ in runs[max(0, i - 3): i]):
            raise TmsParseError(
                "short-column caption without a matching long-column caption: the block is "
                "truncated and its values cannot be assigned"
            )
    # (3) Adjacent instrument runs mean one symbol column was split or lost; the
    #     boundary between them is not recoverable from structure.
    for i in range(1, len(runs)):
        if runs[i][0] == "I" and runs[i - 1][0] == "I":
            raise TmsParseError(
                f"adjacent instrument runs ({runs[i - 1][1][-1]!r} then {runs[i][1][0]!r}) with "
                "no values between them: the symbol column boundary is not recoverable"
            )

    rows: List[SwapRow] = []
    values: Dict[str, Tuple[float, float]] = {}
    consumed: set = set()
    convention_established = False

    def run_at(idx: int) -> Tuple[Optional[str], List[str]]:
        return runs[idx] if 0 <= idx < len(runs) else (None, [])

    for i, (kind, items) in enumerate(runs):
        if kind != "I":
            continue
        k = len(items)
        j = i + 1
        captioned = run_at(j)[0] == "CAP_L"
        if captioned:
            j += 1
        first = run_at(j)
        j2 = j + 1
        if run_at(j2)[0] == "CAP_S":
            captioned = True
            j2 += 1
        second = run_at(j2)

        if first[0] == "P" and len(first[1]) == k and second[0] == "P" and len(second[1]) == k:
            longs, shorts = first[1], second[1]
            consumed.update({j, j2})
            convention_established = convention_established or captioned
        elif first[0] == "P" and len(first[1]) == 2 * k:
            if not convention_established:
                raise TmsParseError(
                    f"refusing to split an uncaptioned {2 * k}-value block for {k} instrument(s) "
                    f"starting at {items[0]!r}: no captioned block has established the "
                    "[all longs][all shorts] convention in this document"
                )
            longs, shorts = first[1][:k], first[1][k:]
            consumed.add(j)
        else:
            raise TmsParseError(
                f"cannot align {k} instrument(s) starting at {items[0]!r} with a long/short "
                f"value block (next run: {first[0]}x{len(first[1])})"
            )

        for idx, instrument in enumerate(items):
            pair = (_percent(longs[idx]), _percent(shorts[idx]))
            prior = values.get(instrument)
            if prior is None:
                values[instrument] = pair
                rows.append(SwapRow(instrument, pair[0], pair[1]))
            elif prior != pair:
                raise TmsParseError(
                    f"conflicting duplicate rows for {instrument!r}: {prior} vs {pair}"
                )

    unclaimed = [i for i, (kind, _) in enumerate(runs) if kind == "P" and i not in consumed]
    if unclaimed:
        first_unclaimed = runs[unclaimed[0]][1]
        raise TmsParseError(
            f"{len(unclaimed)} unclaimed value run(s) with no owning instrument column; "
            f"first is {len(first_unclaimed)} value(s) starting {first_unclaimed[0]!r} "
            "(orphan values mean a symbol column was lost)"
        )

    # Final grid invariant. Entailed by the per-block alignment plus the
    # unclaimed-run check, so it is an assertion rather than live coverage: it has
    # never been observed to fire. Kept so no future code path can bypass it.
    n_instruments = sum(len(v) for k, v in runs if k == "I")
    n_values = sum(len(v) for k, v in runs if k == "P")
    if n_values != 2 * n_instruments:
        raise TmsParseError(
            f"value conservation failed: {n_instruments} instrument(s) require "
            f"{2 * n_instruments} value(s) but the table has {n_values}"
        )

    if not rows:
        raise TmsParseError("no instrument rows parsed")

    return SwapSchedule(
        valid_from=valid_from,
        valid_to=valid_to,
        units=units,
        rows=tuple(rows),
        source_url=source_url,
        sha256=sha256,
    )


def resolve_duplicates(
    schedules: Iterable[SwapSchedule],
) -> Dict[Tuple[dt.date, dt.date], SwapSchedule]:
    """Key schedules by validity interval; identical duplicates collapse, conflicts raise."""
    out: Dict[Tuple[dt.date, dt.date], SwapSchedule] = {}
    for s in schedules:
        key = (s.valid_from, s.valid_to)
        prior = out.get(key)
        if prior is None:
            out[key] = s
            continue
        if prior.rows != s.rows or prior.units != s.units:
            raise TmsDuplicateConflict(
                f"conflicting documents for {key[0]}..{key[1]}: "
                f"{prior.source_url or prior.sha256} vs {s.source_url or s.sha256}"
            )
    return out


def require_layout_agreement(text_rows, layout_rows) -> None:
    """Refuse unless the flattened-text pairing matches the coordinate-anchored one.

    The text layer cannot establish symbol/rate association on its own: its
    pairing follows token order, so a reordered extraction yields wrong pairs
    that look entirely normal. Geometry is the independent authority; this gate
    is what stops the text parser deciding a pairing by itself.
    """
    from_text = {r.instrument: (r.long_pct, r.short_pct) for r in text_rows}
    from_layout = {r.instrument: (r.long_pct, r.short_pct) for r in layout_rows}
    mismatched = sorted(
        k for k in set(from_text) | set(from_layout) if from_text.get(k) != from_layout.get(k)
    )
    if mismatched:
        example = mismatched[0]
        raise TmsParseError(
            f"text and layout extractions disagree for {len(mismatched)} instrument(s); "
            f"e.g. {example!r}: text={from_text.get(example)} layout={from_layout.get(example)}"
        )


def parse_swap_document(
    data: bytes, *, source_url: Optional[str] = None, sha256: Optional[str] = None
) -> SwapSchedule:
    """Parse a swap-point PDF, with symbol/rate pairing corroborated by geometry."""
    import io as _io

    from pdfminer.high_level import extract_text as _extract_text

    from bot.forex.tms_layout import rows_from_tokens, tokens_from_pdf

    schedule = parse_swap_schedule(
        _extract_text(_io.BytesIO(data)), source_url=source_url, sha256=sha256
    )
    require_layout_agreement(schedule.rows, rows_from_tokens(tokens_from_pdf(data)))
    return schedule
