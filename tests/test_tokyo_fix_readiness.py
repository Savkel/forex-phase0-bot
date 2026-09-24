"""Synthetic seal/timestamp checks only. Never open real price caches."""
from datetime import date
from io import BytesIO

import pytest

from bot.forex.tokyo_fix_readiness import (
    IntegrityError, L, U, STEP, REQUIRED, extract_stream, calendar_dates,
    scheduled_windows, support_check, iso, verify_bindings,
)

HEADER = (','.join(REQUIRED) + '\r\n').encode()


class SealGuard(BytesIO):
    def __init__(self, data, forbidden):
        super().__init__(data)
        self.forbidden = forbidden

    def read(self, size=-1):
        assert size == 1, 'prefetch or unbounded request'
        assert self.tell() + size <= self.forbidden, 'sealed price access attempted'
        return super().read(size)


def row(stamp):
    return f'{stamp},SYNTHETIC_NOT_PARSED,1,1,1,1,2,2,2,2,1,True\r\n'.encode()


def test_seal_guard_stops_after_first_excluded_timestamp_delimiter():
    prefix = HEADER + row(L - STEP) + row(L) + row(U - STEP) + f'{U},'.encode()
    output = BytesIO()
    stream = SealGuard(prefix + b'FORBIDDEN_PRICE_BYTES\n', len(prefix))
    result = extract_stream(stream, output)
    assert output.getvalue() == HEADER + row(L) + row(U - STEP)
    assert stream.tell() == len(prefix)
    assert result['row_count'] == 2 and result['stop_timestamp_ms'] == U
    assert result['first_ms'] == L and result['last_ms'] == U - STEP


def test_extraction_is_byte_identical_and_deterministic():
    data = HEADER + row(L) + row(L + STEP)
    a, b = BytesIO(), BytesIO()
    assert extract_stream(BytesIO(data), a) == extract_stream(BytesIO(data), b)
    assert a.getvalue() == b.getvalue() == data


@pytest.mark.parametrize('data', [
    HEADER + row(L) + row(L), HEADER + row(L + STEP) + row(L),
    HEADER + b'not_a_timestamp,anything\n', HEADER + f'{L}\n'.encode(),
    HEADER + f'{L},unterminated'.encode(), b'time,open_time\n',
])
def test_fail_closed_bad_schema_order_and_records(data):
    with pytest.raises(IntegrityError):
        extract_stream(BytesIO(data), BytesIO())


def test_calendar_hashes_and_exact_boundary_exclusion():
    assert len(verify_bindings()) == 10
    dates = calendar_dates()
    assert len(dates['eligible_dates']) == 2445
    assert dates['eligible_dates'][0] == '2014-01-07'
    assert dates['eligible_dates'][-1] == '2024-01-05'
    assert dates['boundary_exclusions'][0]['jst_date'] == '2014-01-06'


@pytest.mark.parametrize('day,entry,end', [
    ('2014-01-07', '2014-01-06T22:15:00Z', '2014-01-07T21:45:00Z'),
    ('2014-07-07', '2014-07-06T21:15:00Z', '2014-07-07T20:45:00Z'),
    ('2024-01-05', '2024-01-04T22:15:00Z', '2024-01-05T21:45:00Z'),
    # Sunday DST transitions: preceding and current rollovers convert independently.
    ('2020-03-08', '2020-03-07T22:15:00Z', '2020-03-08T20:45:00Z'),
    ('2020-11-01', '2020-10-31T21:15:00Z', '2020-11-01T21:45:00Z'),
])
def test_independent_dst_boundary_examples(day, entry, end):
    start, finish = scheduled_windows(date.fromisoformat(day))['passive']
    assert (iso(start), iso(finish)) == (entry, end)


def test_three_windows_have_equal_duration_and_fixed_jst_utc_mapping():
    windows = scheduled_windows(date(2020, 7, 6))
    expected = {'primary': ('2020-07-06T00:00:00Z', '2020-07-06T00:45:00Z'),
                'early': ('2020-07-05T22:30:00Z', '2020-07-05T23:15:00Z'),
                'late': ('2020-07-06T01:30:00Z', '2020-07-06T02:15:00Z')}
    for role, (entry, end) in expected.items():
        a, b = windows[role]
        assert b - a == 3 * STEP
        assert (iso(a), iso(b)) == (entry, end)


def test_missing_bar_fails_without_dropping_or_delaying():
    label = '2020-07-06'
    windows = scheduled_windows(date.fromisoformat(label))
    stamps = {s for a, b in windows.values() for s in range(a - STEP, b + STEP, STEP)}
    assert support_check(stamps, [label])['support_ready']
    stamps.remove(windows['primary'][0] + STEP)
    result = support_check(stamps, [label])
    assert not result['support_ready']
    assert any(m['role'] == 'primary' and m['kind'] == 'INTERMEDIATE' for m in result['missing'])
