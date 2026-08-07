"""Parser for OANDA TMS Brokers `Table of Swap Points` documents.

These are broker-native financing RATE schedules for the EU/TMS division: each
document prints a validity interval and, per instrument, an annualised long and
short rate. They are NOT realized financing - reconstructing an actual debit or
credit additionally requires the days-charged calendar, which TMS does not
publish (see the Terms and Conditions of brokerage services).

The parser is fail-closed by design: a block it cannot fully align raises
`TmsParseError` rather than silently dropping instruments. A silent omission
would look exactly like an instrument that was not quoted that week.
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


_HEADER = re.compile(
    r"Valid\s+from\s*(\d{4})\.(\d{2})\.(\d{2})\s*\D{1,4}?\s*(\d{4})\.(\d{2})\.(\d{2})"
)
# Instrument symbols are upper-case with an optional lower-case account/section
# suffix (.pro/.std/.stp/.cash). The upper-case base is what keeps prose lines
# such as "Instrument" or "Long swap" out of the instrument runs.
_INSTRUMENT = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{1,14}(?:\.[a-z]{2,5})?$")
_PERCENT = re.compile(r"^-?\d+[.,]\d+%$")
_CAPTION_LONG = re.compile(r"^long swap$", re.IGNORECASE)
_CAPTION_SHORT = re.compile(r"^short swap$", re.IGNORECASE)
# Signatures of the equities/ETF table, which carries a third column ("additional
# cost of keeping a short position open") and must never be read as long/short
# pairs. The cut is only accepted when the discarded tail really is that table.
_EQUITIES_SIGNATURE = re.compile(r"Equities|Additional cost|_CFD\.", re.IGNORECASE)
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
    text = text.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))
    header = _HEADER.search(text)
    if header is None:
        raise TmsParseError("no 'Valid from <date> - <date>' header found")
    g = [int(x) for x in header.groups()]
    valid_from = dt.date(g[0], g[1], g[2])
    valid_to = dt.date(g[3], g[4], g[5])
    if valid_to < valid_from:
        raise TmsParseError(f"validity interval ends before it starts: {valid_from}..{valid_to}")

    units = "percent_per_annum" if "per annum" in text[: header.end() + 200] else "percentage_points"

    body = text[header.end():]
    end = _SECTION_END.search(body) or _SECTION_END_FALLBACK.search(body)
    if end is not None:
        tail = body[end.start():]
        if not _EQUITIES_SIGNATURE.search(tail):
            raise TmsParseError(
                f"unexpected section boundary {tail.splitlines()[0]!r}: the discarded tail does "
                "not look like the equities table"
            )
        body = body[: end.start()]

    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    runs = _runs(lines)

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
