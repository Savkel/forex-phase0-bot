"""Explicitly authorized acquisition of only the Cabinet Office holiday source.

No price, strategy, or other external data is accessed. Existing snapshots are
never overwritten. Reproduction after acquisition uses build_tokyo_calendar.py.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
PAGE = "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html"
CSV = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"


class OfficialOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl not in (PAGE, CSV):
            raise ValueError("Redirect outside the two authorized source URLs")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SourceLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(urljoin(PAGE, href))


def main():
    raw_dir = ROOT / "data/japan_calendar/raw"
    manifest_path = ROOT / "provenance/tokyo_calendar_source.json"
    paths = (raw_dir / "cao_gaiyou.html", raw_dir / "syukujitsu.csv")
    if any(p.exists() for p in (*paths, manifest_path)):
        raise FileExistsError("Preserve existing snapshots; acquisition cannot overwrite")
    opener = build_opener(OfficialOnly())

    def fetch(url):
        if url not in (PAGE, CSV) or urlparse(url).hostname != "www8.cao.go.jp":
            raise ValueError("Unauthorized URL")
        with opener.open(Request(url, headers={"User-Agent": "TokyoCalendarResearch/1.0"}), timeout=30) as response:
            if response.geturl() != url or response.status != 200:
                raise ValueError("Unexpected final URL/status")
            body = response.read()
            return body, {
                "url": url, "final_url": response.geturl(),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "sha256": sha256(body).hexdigest(), "bytes": len(body),
                "http_status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "last_modified": response.headers.get("Last-Modified"),
            }

    page, page_meta = fetch(PAGE)
    parser = SourceLinks()
    text = page.decode("utf-8")
    parser.feed(text)
    if CSV not in parser.links or "1955" not in text or "2027" not in text:
        raise ValueError("Official page does not establish the requested linked coverage")
    raw, csv_meta = fetch(CSV)
    # Validate response structure before saving, without transforming source bytes.
    if raw.decode("cp932").splitlines()[0] != "国民の祝日・休日月日,国民の祝日・休日名称":
        raise ValueError("Unexpected Cabinet Office CSV header")
    raw_dir.mkdir(parents=True, exist_ok=True)
    for path, body, meta in zip(paths, (page, raw), (page_meta, csv_meta)):
        with path.open("xb") as handle:
            handle.write(body)
        meta["path"] = path.relative_to(ROOT).as_posix()
    manifest = {
        "schema_version": 1, "gate": "TOKYO_FIX_CALENDAR_ACQUISITION",
        "source_identity": "Cabinet Office, Government of Japan, national holidays CSV",
        "official_page": page_meta, "raw_csv": csv_meta,
        "official_page_links_csv": True, "advertised_coverage_years": [1955, 2027],
        "closure_rule_authority": "User-specified Bank of Japan office-closure rule: weekends, Cabinet Office listed holidays, December 31 through January 3. No BOJ fetch performed.",
        "scope": "Calendar only; no price or strategy data accessed.",
    }
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(csv_meta, ensure_ascii=True))


if __name__ == "__main__":
    main()
