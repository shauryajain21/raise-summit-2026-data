#!/usr/bin/env python3
import os
"""Scrape all RAISE Summit 2026 sponsors/exhibitors (~141) from Brella."""
import csv, json, sys, time, urllib.parse, urllib.request

EVENT = "raisesummit2026"
PAGE_SIZE = 120
OUT = "raise_sponsors.csv"

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
    url = f"https://api.brella.io/api/events/{EVENT}/sponsors?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def cat_lookup(included):
    out = {}
    for it in included:
        if it["type"] in ("sponsor-category", "category"):
            out[it["id"]] = it["attributes"].get("name", "")
    return out


def main():
    rows, page, total_pages = [], 1, None
    while True:
        d = fetch(page)
        total_pages = d["meta"]["total_pages"]
        cats = cat_lookup(d.get("included", []))
        for s in d["data"]:
            a = s["attributes"]
            cat = s.get("relationships", {}).get("category", {}).get("data")
            reps = s.get("relationships", {}).get("attendees", {}).get("data") or []
            rows.append({
                "name": a.get("name", ""),
                "level": a.get("level", ""),
                "category": cats.get(cat["id"], "") if cat else "",
                "subtitle": (a.get("subtitle") or "").strip(),
                "cta_text": a.get("cta-text", ""),
                "social": a.get("instagram", ""),
                "map_link": a.get("map-link", ""),
                "logo_url": a.get("logo-url", ""),
                "num_reps": len(reps),
                "active": a.get("active", ""),
                "sponsor_id": s["id"],
            })
        print(f"page {page}/{total_pages}  rows: {len(rows)}", file=sys.stderr)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.4)

    rows.sort(key=lambda r: (r["level"] or "zz", r["name"].lower()))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} sponsors -> {OUT}", file=sys.stderr)
    import collections
    print("  by level:", dict(collections.Counter(r["level"] for r in rows)), file=sys.stderr)


if __name__ == "__main__":
    main()
