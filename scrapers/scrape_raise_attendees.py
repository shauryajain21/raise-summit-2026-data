#!/usr/bin/env python3
"""Scrape RAISE Summit 2026 attendee directory from Brella's JSON:API.

Rides an authenticated session's API calls (auth headers below). The access
token is short-lived; if you get 401s, re-grab a fresh `access-token`/`client`
pair from DevTools and update the headers.
"""
import csv
import os
import sys
import time
import urllib.parse
import urllib.request
import json

EVENT = "raisesummit2026"
PAGE_SIZE = 120  # server caps here
OUT = "raise_attendees.csv"

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
    url = f"https://api.brella.io/api/events/{EVENT}/attendees?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def index_included(included, lookups):
    """Build {(type,id): display_name} for reference types."""
    out = {}
    for item in included:
        t = item["type"]
        if t in lookups:
            attrs = item["attributes"]
            name = attrs.get("name") or attrs.get("title") or ""
            out[(t, item["id"])] = name
        elif t == "user":
            out[("user", item["id"])] = item["attributes"]
    return out


def rel_name(att, rel, lookup):
    d = att["relationships"].get(rel, {}).get("data")
    if not d:
        return ""
    return lookup.get((d["type"], d["id"]), "")


def main():
    rows = []
    page = 1
    total_pages = None
    while True:
        d = fetch(page)
        meta = d["meta"]
        total_pages = meta["total_pages"]
        lookup = index_included(
            d.get("included", []),
            {"persona", "function", "industry", "interest", "attendee-group"},
        )
        for a in d["data"]:
            att = a["attributes"]
            uid = a["relationships"].get("user", {}).get("data", {})
            user = lookup.get(("user", uid.get("id"))) if uid else None
            user = user if isinstance(user, dict) else {}
            rows.append({
                "first_name": att.get("first-name", ""),
                "last_name": att.get("last-name", ""),
                "company_title": att.get("company-title", ""),
                "company_name": att.get("company-name", ""),
                "email": user.get("email", ""),
                "linkedin": user.get("linkedin", ""),
                "twitter": user.get("twitter", ""),
                "website": user.get("website", ""),
                "persona": rel_name(a, "persona", lookup),
                "function": rel_name(a, "function", lookup),
                "industry": rel_name(a, "industry", lookup),
                "group": rel_name(a, "group", lookup),
                "status": att.get("status", ""),
                "joined_at": att.get("joined-at", ""),
                "pitch": (att.get("pitch") or "").replace("\n", " ").strip(),
                "attendee_id": a["id"],
            })
        print(f"page {page}/{total_pages}  total rows: {len(rows)}", file=sys.stderr)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)  # be polite

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} attendees -> {OUT}", file=sys.stderr)
    with_email = sum(1 for r in rows if r["email"])
    with_li = sum(1 for r in rows if r["linkedin"])
    print(f"  with email: {with_email}   with linkedin: {with_li}", file=sys.stderr)


if __name__ == "__main__":
    main()
