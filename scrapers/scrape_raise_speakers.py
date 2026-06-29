#!/usr/bin/env python3
import os
"""Scrape all RAISE Summit 2026 speakers (~372) from Brella."""
import csv, json, sys, time, urllib.parse, urllib.request

EVENT = "raisesummit2026"
PAGE_SIZE = 120
OUT = "raise_speakers.csv"

HEADERS = {
    "accept": "application/vnd.brella.v4+json",
    "access-token": os.environ["BRELLA_ACCESS_TOKEN"],
    "brella-organization-slug": "raisesummit",
    "client": os.environ["BRELLA_CLIENT"],
    "origin": "https://raisesummit.brella.io",
    "referer": "https://raisesummit.brella.io/",
    "uid": os.environ.get("BRELLA_UID", ""),
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def fetch(page):
    qs = urllib.parse.urlencode({"page[size]": PAGE_SIZE, "page[number]": page})
    url = f"https://api.brella.io/api/events/{EVENT}/speakers?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def flatten_bio(bio):
    if not isinstance(bio, dict):
        return (bio or "")
    blocks = bio.get("blocks", [])
    return " ".join(b.get("text", "") for b in blocks).replace("\n", " ").strip()


def main():
    rows, page, total_pages = [], 1, None
    while True:
        d = fetch(page)
        total_pages = d["meta"]["total_pages"]
        for s in d["data"]:
            a = s["attributes"]
            rows.append({
                "first_name": a.get("first-name", ""),
                "last_name": a.get("last-name", ""),
                "job_title": a.get("job-title", ""),
                "company_name": a.get("company-name", ""),
                "honorific": a.get("honorific") or "",
                "bio": flatten_bio(a.get("bio")),
                "photo_url": a.get("photo-url", ""),
                "speaker_id": s["id"],
            })
        print(f"page {page}/{total_pages}  rows: {len(rows)}", file=sys.stderr)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.4)

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} speakers -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
