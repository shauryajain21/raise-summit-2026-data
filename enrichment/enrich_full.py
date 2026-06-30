#!/usr/bin/env python3
"""Enrich ALL RAISE Summit 2026 registrants via Linkup structured search.

One structured-output search per person (depth=standard) returns the full
schema in a single call. Rate-limited to <=22 QPS (under Linkup's 25 cap),
concurrent, resumable (skips registrant_ids already in the output CSV).
"""
import csv, json, os, sys, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(__file__)
IN_CSV = os.environ.get("ENRICH_IN", os.path.join(ROOT, "..", "data", "raise_registrants.csv"))
OUT_CSV = os.environ.get("ENRICH_OUT", os.path.join(ROOT, "raise_enrichment_full.csv"))
KEY = open(os.path.expanduser("~/.linkup/config")).read().strip().split("=", 1)[1]

QPS = 22
WORKERS = 120
RETRIES = 4

SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "linkedin_url": {"type": "string", "description": "LinkedIn profile URL of the person, or empty string if not confidently found"},
        "person_info": {"type": "string", "description": "2-3 sentences on the person's role and career background"},
        "homepage_url": {"type": "string", "description": "the company's official website URL"},
        "company_info": {"type": "string", "description": "2-3 sentences on what the company does"},
        "company_goals": {"type": "string", "description": "2-3 sentences on what the company is building/selling and working toward, and who it serves"},
        "total_funding": {"type": "string", "description": "total funding raised, or 'Public company'/'Government body'/'Unknown'"},
        "latest_round": {"type": "string", "description": "most recent round type, amount, date, or empty"},
        "key_investors": {"type": "string", "description": "notable investors, comma separated, or empty"},
    },
    "required": ["linkedin_url", "person_info", "homepage_url", "company_info",
                 "company_goals", "total_funding", "latest_round", "key_investors"],
})

OUT_COLS = ["registrant_id", "first_name", "last_name", "company_title", "company_name",
            "industry", "linkedin_url", "person_info", "homepage_url", "company_info",
            "company_goals", "total_funding", "latest_round", "key_investors", "status"]


class RateLimiter:
    def __init__(self, rate):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            sleep = max(0.0, self.next - now)
            self.next = max(now, self.next) + self.interval
        if sleep:
            time.sleep(sleep)


limiter = RateLimiter(QPS)
write_lock = threading.Lock()
counter = {"done": 0, "ok": 0, "err": 0}


def query(person):
    first, last = person["first_name"].strip(), person["last_name"].strip()
    title, company = person["company_title"].strip(), person["company_name"].strip()
    q = (f"Find the LinkedIn profile and career background of {first} {last}, "
         f"{title} at {company}. Also: what {company} does, its official homepage URL, "
         f"what it is building and working toward and who it serves, and how much funding "
         f"{company} has raised (total, latest round, key investors).")
    body = json.dumps({"q": q, "depth": "standard", "outputType": "structured",
                       "structuredOutputSchema": SCHEMA}).encode()
    for attempt in range(RETRIES):
        limiter.wait()
        try:
            req = urllib.request.Request("https://api.linkup.so/v1/search", data=body,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()), "ok"
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            return {}, f"http_{e.code}"
        except Exception as e:
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            return {}, f"err_{type(e).__name__}"
    return {}, "err_exhausted"


def enrich(person, writer, fh):
    data, status = query(person)
    row = {
        "registrant_id": person["registrant_id"], "first_name": person["first_name"],
        "last_name": person["last_name"], "company_title": person["company_title"],
        "company_name": person["company_name"], "industry": person["industry"],
        "linkedin_url": data.get("linkedin_url", ""), "person_info": data.get("person_info", ""),
        "homepage_url": data.get("homepage_url", ""), "company_info": data.get("company_info", ""),
        "company_goals": data.get("company_goals", ""), "total_funding": data.get("total_funding", ""),
        "latest_round": data.get("latest_round", ""), "key_investors": data.get("key_investors", ""),
        "status": status,
    }
    with write_lock:
        writer.writerow(row)
        fh.flush()
        counter["done"] += 1
        counter["ok" if status == "ok" else "err"] += 1
        if counter["done"] % 100 == 0:
            print(f"{counter['done']} done ({counter['ok']} ok, {counter['err']} err)", flush=True)


def main():
    people = list(csv.DictReader(open(IN_CSV, encoding="utf-8")))
    done_ids = set()
    if os.path.exists(OUT_CSV):
        for r in csv.DictReader(open(OUT_CSV, encoding="utf-8")):
            done_ids.add(r["registrant_id"])
    todo = [p for p in people if p["registrant_id"] not in done_ids]
    print(f"total {len(people)} | already done {len(done_ids)} | to do {len(todo)}", flush=True)

    new_file = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=OUT_COLS)
    if new_file:
        writer.writeheader(); fh.flush()

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for p in todo:
            ex.submit(enrich, p, writer, fh)
    fh.close()
    dt = time.monotonic() - t0
    print(f"\nDONE: {counter['done']} processed in {dt:.0f}s | ok {counter['ok']} | err {counter['err']}", flush=True)


if __name__ == "__main__":
    main()
