"""Offline, deterministic calendar derivation; no market data or strategy logic."""
import csv
from datetime import date, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
START, END = date(2014, 1, 6), date(2024, 1, 5)
PAGE = "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html"
CSV_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
HEADER = ["国民の祝日・休日月日", "国民の祝日・休日名称"]
# Outcome-independent holiday/calendar checks, including dates on which moved
# holidays must NOT remain. These checks never reference price availability.
HOLIDAYS = (
    "2014-01-13", "2014-05-06", "2015-05-06", "2015-09-22",
    "2016-08-11", "2018-12-24", "2019-04-30", "2019-05-01",
    "2019-05-02", "2019-05-06", "2019-10-22", "2020-02-24",
    "2020-07-23", "2020-07-24", "2020-08-10", "2021-07-22",
    "2021-07-23", "2021-08-08", "2021-08-09", "2023-01-09",
    "2024-01-01",
)
ORDINARY = (
    "2014-01-06", "2015-09-24", "2019-05-07", "2019-12-23",
    "2020-07-20", "2020-08-11", "2020-10-12", "2021-07-19",
    "2021-08-11", "2021-10-11", "2024-01-04", "2024-01-05",
)


def parse_holidays(raw):
    rows = csv.reader(io.StringIO(raw.decode("cp932"), newline=""))
    if next(rows, None) != HEADER:
        raise ValueError("Unexpected source schema")
    holidays = {}
    previous = None
    for row in rows:
        if len(row) != 2 or not row[1].strip():
            raise ValueError("Malformed source record")
        day = date(*map(int, row[0].split("/")))
        if previous is not None and day <= previous:
            raise ValueError("Unsorted or duplicate holiday")
        holidays[day] = row[1]
        previous = day
    if {d.year for d in holidays} != set(range(1955, 2028)):
        raise ValueError("Source must cover every advertised year, 1955-2027")
    if any(date(y, 1, 1) not in holidays for y in range(1955, 2028)):
        raise ValueError("Incomplete yearly source coverage")
    if not (min(holidays) <= START <= END <= max(holidays)):
        raise ValueError("Requested range not covered")
    for value in HOLIDAYS:
        if date.fromisoformat(value) not in holidays:
            raise ValueError(f"Missing ordinary/exceptional holiday: {value}")
    for value in ORDINARY:
        if date.fromisoformat(value) in holidays:
            raise ValueError(f"Unexpected holiday on ordinary/moved-from date: {value}")
    return holidays


def classify(day, holidays):
    reasons = []
    if day.weekday() >= 5:
        reasons.append("weekend")
    if day in holidays:
        reasons.append("cabinet_office_holiday:" + holidays[day])
    if (day.month == 12 and day.day == 31) or (day.month == 1 and day.day <= 3):
        reasons.append("dec31_jan3_closure")
    return not reasons, ";".join(reasons)


def calendar_bytes(holidays):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["jst_date", "eligible", "exclusion_reason"])
    for i in range((END - START).days + 1):
        day = START + timedelta(days=i)
        eligible, reason = classify(day, holidays)
        writer.writerow([day.isoformat(), str(eligible).lower(), reason])
    return output.getvalue().encode("utf-8")


def verified_source():
    manifest = json.loads((ROOT / "provenance/tokyo_calendar_source.json").read_text(encoding="utf-8"))
    payloads = {}
    for key, expected_url, expected_path in (
        ("official_page", PAGE, "data/japan_calendar/raw/cao_gaiyou.html"),
        ("raw_csv", CSV_URL, "data/japan_calendar/raw/syukujitsu.csv"),
    ):
        meta = manifest[key]
        if meta["url"] != expected_url or meta["final_url"] != expected_url or meta["path"] != expected_path or meta["http_status"] != 200:
            raise ValueError("Unexpected provenance identity")
        raw = (ROOT / expected_path).read_bytes()
        if sha256(raw).hexdigest() != meta["sha256"] or len(raw) != meta["bytes"]:
            raise ValueError("Source bytes differ from acquisition provenance")
        payloads[key] = raw

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            href = dict(attrs).get("href")
            if tag == "a" and href:
                self.urls.append(urljoin(PAGE, href))

    parser = Links()
    parser.feed(payloads["official_page"].decode("utf-8"))
    if CSV_URL not in parser.urls:
        raise ValueError("Preserved official page does not link CSV")
    return manifest, payloads["raw_csv"]


def save_new_or_identical(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Refusing to replace differing artifact: {path}")
    else:
        with path.open("xb") as handle:
            handle.write(payload)


def main():
    manifest, raw = verified_source()
    holidays = parse_holidays(raw)
    derived = calendar_bytes(holidays)
    rows = list(csv.DictReader(io.StringIO(derived.decode("utf-8"))))
    expected_rows = (END - START).days + 1
    if len(rows) != expected_rows or rows[0]["jst_date"] != START.isoformat() or rows[-1]["jst_date"] != END.isoformat():
        raise ValueError("Derived calendar has incorrect bounds or length")
    output = ROOT / "data/japan_calendar/tokyo_eligible_days_20140106_20240105.csv"
    report = {
        "schema_version": 1, "status": "TOKYO_FIX_CALENDAR_READY",
        "timezone": "Asia/Tokyo (JST, UTC+09:00; no DST)",
        "start_inclusive": START.isoformat(), "end_inclusive": END.isoformat(),
        "rule": "Monday-Friday AND absent from official CSV AND outside December 31-January 3",
        "reason_order": ["weekend", "cabinet_office_holiday:<original source name>", "dec31_jan3_closure"],
        "source_sha256": sha256(raw).hexdigest(),
        "source_retrieved_at_utc": manifest["raw_csv"]["retrieved_at_utc"],
        "source_date_min": min(holidays).isoformat(), "source_date_max": max(holidays).isoformat(),
        "source_rows": len(holidays),
        "source_holidays_per_year": {str(y): sum(d.year == y for d in holidays) for y in range(1955, 2028)},
        "days": len(rows), "eligible_days": sum(r["eligible"] == "true" for r in rows),
        "excluded_days": sum(r["eligible"] == "false" for r in rows),
        "calendar_path": output.relative_to(ROOT).as_posix(),
        "calendar_sha256": sha256(derived).hexdigest(),
        "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "known_holiday_checks": list(HOLIDAYS), "known_ordinary_checks": list(ORDINARY),
        "scope": "Retrospective business-day calendar only, not evidence of actual fixing publication, price availability, or trading permission. No strategy, prices, or sealed data accessed.",
        "vintage_note": "Official 2026 source snapshot of historical legal holidays; not a historical publication-time/vintage archive.",
        "reproduce": "python -B scripts/build_tokyo_calendar.py",
    }
    report_bytes = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    save_new_or_identical(output, derived)
    save_new_or_identical(ROOT / "data/japan_calendar/verification.json", report_bytes)
    print(json.dumps({k: report[k] for k in ("status", "days", "eligible_days", "excluded_days", "source_sha256", "calendar_sha256")}))


if __name__ == "__main__":
    main()
