from datetime import datetime, timezone
from bot.forex.cost_model import CostModel, spread_frac, rollovers_in, swap_frac

def _ms(y, m, d, h):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp() * 1000)

def test_spread_frac_is_full_spread_over_mid():
    # bid 1.0000, ask 1.0002 -> spread 0.0002, mid 1.0001
    f = spread_frac(1.0000, 1.0002, spread_mult=1.0)
    assert abs(f - (0.0002 / 1.0001)) < 1e-12

def test_spread_mult_widens_linearly():
    base = spread_frac(1.0000, 1.0002, 1.0)
    assert abs(spread_frac(1.0000, 1.0002, 1.5) - 1.5 * base) < 1e-12

def test_rollovers_counts_one_per_day_crossing():
    # interval covering exactly one 21:00 rollover
    t0 = _ms(2026, 6, 1, 20); t1 = _ms(2026, 6, 1, 23)
    rolls = rollovers_in(t0, t1, 21)
    assert len(rolls) == 1 and rolls[0].hour == 21

def test_wednesday_rollover_is_tripled():
    cost = CostModel(pip=0.0001, long_swap_pips=1.0, short_swap_pips=1.0,
                     rollover_hour_utc=21, spread_mult=1.0, swap_mult=1.0)
    # 2026-06-03 is a Wednesday
    wed = swap_frac(cost, side=1, mid=1.0, t0_ms=_ms(2026,6,3,20), t1_ms=_ms(2026,6,3,23))
    thu = swap_frac(cost, side=1, mid=1.0, t0_ms=_ms(2026,6,4,20), t1_ms=_ms(2026,6,4,23))
    assert abs(wed - 3 * thu) < 1e-12

def test_swap_mult_scales_cost():
    c1 = CostModel(0.0001, 1.0, 1.0, 21, 1.0, 1.0)
    c2 = CostModel(0.0001, 1.0, 1.0, 21, 1.0, 2.0)
    a = swap_frac(c1, 1, 1.0, _ms(2026,6,4,20), _ms(2026,6,4,23))
    b = swap_frac(c2, 1, 1.0, _ms(2026,6,4,20), _ms(2026,6,4,23))
    assert abs(b - 2 * a) < 1e-12

def test_no_rollover_means_zero_swap():
    # interval entirely before the 21:00 rollover crosses nothing
    cost = CostModel(pip=0.0001, long_swap_pips=1.0, short_swap_pips=1.0, rollover_hour_utc=21)
    assert rollovers_in(_ms(2026,6,4,10), _ms(2026,6,4,12), 21) == []
    assert swap_frac(cost, side=1, mid=1.0, t0_ms=_ms(2026,6,4,10), t1_ms=_ms(2026,6,4,12)) == 0.0

def test_swap_distinguishes_long_and_short_sign():
    # long pays (positive pips), short earns (negative pips): different sign & magnitude
    cost = CostModel(pip=0.0001, long_swap_pips=2.0, short_swap_pips=-1.0, rollover_hour_utc=21)
    t0, t1 = _ms(2026,6,4,20), _ms(2026,6,4,23)   # one Thursday rollover (not Wed -> x1)
    long_swap = swap_frac(cost, side=1, mid=1.0, t0_ms=t0, t1_ms=t1)
    short_swap = swap_frac(cost, side=-1, mid=1.0, t0_ms=t0, t1_ms=t1)
    assert long_swap > 0          # long pays
    assert short_swap < 0         # short earns (credit)
    assert long_swap != short_swap

def test_full_week_charges_seven_weighted_units_not_nine():
    # FX value-date convention: rollovers land on business days only, and the Wednesday
    # rollover carries the weekend value date (x3). A continuously held position over a
    # normal Mon->Mon week therefore pays 5 rollovers = 4*1 + 3 = 7.0 weighted units.
    # Charging Sat + Sun as well (9.0 units) double-counts the weekend the x3 already covers.
    cost = CostModel(pip=0.0001, long_swap_pips=1.0, short_swap_pips=1.0, rollover_hour_utc=21)
    t0, t1 = _ms(2026, 6, 1, 0), _ms(2026, 6, 8, 0)      # 2026-06-01 is a Monday
    rolls = rollovers_in(t0, t1, 21)
    assert [r.weekday() for r in rolls] == [0, 1, 2, 3, 4]   # Mon..Fri only; no Sat(5)/Sun(6)
    per_night = 1.0 * 0.0001 / 1.0
    assert abs(swap_frac(cost, 1, 1.0, t0, t1) - 7.0 * per_night) < 1e-15

def test_weekend_only_interval_charges_zero_swap():
    # Sat 2026-06-06 00:00 -> Sun 2026-06-07 23:00 spans the Sat and Sun 21:00 instants
    # and nothing else: no value date rolls over a weekend, so the charge is exactly zero.
    cost = CostModel(pip=0.0001, long_swap_pips=1.0, short_swap_pips=-1.0, rollover_hour_utc=21)
    t0, t1 = _ms(2026, 6, 6, 0), _ms(2026, 6, 7, 23)
    assert rollovers_in(t0, t1, 21) == []
    assert swap_frac(cost, 1, 1.0, t0, t1) == 0.0
    assert swap_frac(cost, -1, 1.0, t0, t1) == 0.0

def test_wednesday_still_counts_triple_inside_a_full_week():
    # Guards the x3 against a weekend filter that removes it too: of the 7.0 weekly units,
    # exactly 3.0 come from the single Wednesday rollover.
    cost = CostModel(pip=0.0001, long_swap_pips=1.0, short_swap_pips=1.0, rollover_hour_utc=21)
    per_night = 1.0 * 0.0001 / 1.0
    week = swap_frac(cost, 1, 1.0, _ms(2026, 6, 1, 0), _ms(2026, 6, 8, 0))
    wed_only = swap_frac(cost, 1, 1.0, _ms(2026, 6, 3, 20), _ms(2026, 6, 3, 23))
    assert abs(wed_only - 3.0 * per_night) < 1e-15
    assert abs(week - wed_only - 4.0 * per_night) < 1e-15   # the other four nights are x1

def test_long_and_short_use_identical_rollover_counting():
    # Only the pips value may differ between sides; the set of charged rollovers and the
    # Wednesday weighting must be identical, so |units| match exactly over a full week.
    cost = CostModel(pip=0.0001, long_swap_pips=2.0, short_swap_pips=-2.0, rollover_hour_utc=21)
    t0, t1 = _ms(2026, 6, 1, 0), _ms(2026, 6, 8, 0)
    long_units = swap_frac(cost, 1, 1.0, t0, t1) / (2.0 * 0.0001)
    short_units = swap_frac(cost, -1, 1.0, t0, t1) / (-2.0 * 0.0001)
    assert abs(long_units - 7.0) < 1e-12
    assert abs(short_units - 7.0) < 1e-12
    assert abs(long_units - short_units) < 1e-12

def test_interval_boundary_semantics_unchanged_by_weekend_filter():
    # (t0, t1]: a rollover exactly AT t0 is excluded, one exactly AT t1 is included.
    # Verified on a business day so the weekend filter cannot mask the boundary rule.
    assert rollovers_in(_ms(2026, 6, 1, 21), _ms(2026, 6, 2, 20), 21) == []      # at t0 -> excluded
    at_t1 = rollovers_in(_ms(2026, 6, 1, 20), _ms(2026, 6, 1, 21), 21)           # at t1 -> included
    assert len(at_t1) == 1 and at_t1[0].weekday() == 0 and at_t1[0].hour == 21

def test_stress_multipliers_are_monotonic():
    # spread widens monotonically with spread_mult
    s1 = spread_frac(1.0000, 1.0002, 1.0)
    s2 = spread_frac(1.0000, 1.0002, 1.5)
    s3 = spread_frac(1.0000, 1.0002, 2.0)
    assert s1 < s2 < s3
    # swap cost grows monotonically with swap_mult
    base = CostModel(0.0001, 1.0, 1.0, 21, 1.0, 1.0)
    stressed = CostModel(0.0001, 1.0, 1.0, 21, 1.0, 2.0)
    t0, t1 = _ms(2026,6,4,20), _ms(2026,6,4,23)
    assert swap_frac(stressed, 1, 1.0, t0, t1) > swap_frac(base, 1, 1.0, t0, t1)
