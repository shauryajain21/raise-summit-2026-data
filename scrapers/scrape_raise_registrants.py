#!/usr/bin/env python3
import os
"""Scrape ALL RAISE Summit 2026 registrants (~4,403) from Brella.

The /registrants endpoint covers everyone who registered, not just those who
activated networking. Contact fields (email/linkedin) only exist for the subset
who joined networking, so we merge those from raise_attendees.csv when present.
"""
import csv, json, sys, time, urllib.parse, urllib.request

EVENT = "raisesummit2026"
PAGE_SIZE = 120
OUT = "raise_registrants.csv"
ATTENDEE_CSV = "raise_attendees.csv"  # for email/linkedin enrichment

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

REF_TYPES = {"persona", "function", "industry", "attendee-group"}


def fetch(page):
    qs = urllib.parse.urlencode({"page[size]": PAGE_SIZE, "page[number]": page})
    url = f"https://api.brella.io/api/events/{EVENT}/registrants?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def ref_lookup(included):
    out = {}
    for it in included:
        if it["type"] in REF_TYPES:
            a = it["attributes"]
            out[(it["type"], it["id"])] = a.get("name") or a.get("title") or ""
    return out


def rel_name(rec, rel, lookup):
    d = rec.get("relationships", {}).get(rel, {}).get("data")
    return lookup.get((d["type"], d["id"]), "") if d else ""


def load_contacts():
    try:
        rows = list(csv.DictReader(open(ATTENDEE_CSV)))
    except FileNotFoundError:
        return {}
    return {r["attendee_id"]: r for r in rows}


def main():
    contacts = load_contacts()
    rows, page, total_pages = [], 1, None
    while True:
        d = fetch(page)
        total_pages = d["meta"]["total_pages"]
        lookup = ref_lookup(d.get("included", []))
        for rec in d["data"]:
            a = rec["attributes"]
            att = rec.get("relationships", {}).get("attendee", {}).get("data")
            att_id = att["id"] if att else ""
            joined = att_id in contacts
            c = contacts.get(att_id, {})
            rows.append({
                "first_name": a.get("first-name", ""),
                "last_name": a.get("last-name", ""),
                "company_title": a.get("company-title", ""),
                "company_name": a.get("company-name", ""),
                "joined_networking": "yes" if joined else "no",
                "email": c.get("email", ""),
                "linkedin": c.get("linkedin", ""),
                "twitter": c.get("twitter", ""),
                "website": c.get("website", ""),
                "persona": rel_name(rec, "persona", lookup),
                "function": rel_name(rec, "function", lookup),
                "industry": rel_name(rec, "industry", lookup),
                "pitch": c.get("pitch", ""),
                "registrant_id": rec["id"],
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
    j = sum(1 for r in rows if r["joined_networking"] == "yes")
    print(f"\nWrote {len(rows)} registrants -> {OUT}", file=sys.stderr)
    print(f"  joined networking: {j}   not joined: {len(rows)-j}", file=sys.stderr)


if __name__ == "__main__":
    main()
