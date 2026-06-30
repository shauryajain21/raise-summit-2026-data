#!/usr/bin/env python3
"""Funding-recovery pass: dedicated funding search for companies whose funding
came back empty/Unknown in the full enrichment. Deduped by company, anchored on
the known homepage to avoid same-name collisions. Rate-limited, resumable.
"""
import csv, json, os, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(__file__)
FULL = os.path.join(ROOT, "raise_enrichment_full.csv")
OUT = os.path.join(ROOT, "funding_recovery.csv")
KEY = open(os.path.expanduser("~/.linkup/config")).read().strip().split("=", 1)[1]

QPS = 22
WORKERS = 120
RETRIES = 4

SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "total_funding": {"type": "string", "description": "total funding raised to date (e.g. '$45M'), or 'Public company'/'Government body'/'Bootstrapped'/'Unknown'"},
        "latest_round": {"type": "string", "description": "most recent round: type, amount, date, or empty"},
        "valuation": {"type": "string", "description": "last known valuation, or empty"},
        "key_investors": {"type": "string", "description": "notable investors, comma separated, or empty"},
    },
    "required": ["total_funding", "latest_round", "valuation", "key_investors"],
})


class RateLimiter:
    def __init__(self, rate):
        self.interval = 1.0 / rate; self.lock = threading.Lock(); self.next = 0.0
    def wait(self):
        with self.lock:
            now = time.monotonic(); sleep = max(0.0, self.next - now)
            self.next = max(now, self.next) + self.interval
        if sleep: time.sleep(sleep)


limiter = RateLimiter(QPS)
wlock = threading.Lock()
cnt = {"done": 0, "found": 0}


def search(company, homepage):
    anchor = f" The company's website is {homepage}." if homepage else ""
    q = (f"How much venture funding has the company {company} raised?{anchor} "
         f"Give total funding raised to date, the most recent round (type, amount, date), "
         f"last known valuation, and key investors. If {company} is a public company, a "
         f"government body, a non-profit, or bootstrapped with no outside funding, state that.")
    body = json.dumps({"q": q, "depth": "standard", "outputType": "structured",
                       "structuredOutputSchema": SCHEMA}).encode()
    for a in range(RETRIES):
        limiter.wait()
        try:
            req = urllib.request.Request("https://api.linkup.so/v1/search", data=body,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()), "ok"
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < RETRIES - 1:
                time.sleep(2 ** a); continue
            return {}, f"http_{e.code}"
        except Exception as e:
            if a < RETRIES - 1:
                time.sleep(2 ** a); continue
            return {}, f"err_{type(e).__name__}"
    return {}, "err"


def has_value(v):
    v = (v or "").strip().lower()
    return v and v not in ("unknown", "not disclosed", "n/a", "none", "")


def work(company, homepage, writer, fh):
    data, status = search(company, homepage)
    row = {"company_name": company, "total_funding": data.get("total_funding", ""),
           "latest_round": data.get("latest_round", ""), "valuation": data.get("valuation", ""),
           "key_investors": data.get("key_investors", ""), "status": status}
    with wlock:
        writer.writerow(row); fh.flush()
        cnt["done"] += 1
        if has_value(row["total_funding"]): cnt["found"] += 1
        if cnt["done"] % 100 == 0:
            print(f"{cnt['done']} done, {cnt['found']} with a value", flush=True)


def main():
    rows = list(csv.DictReader(open(FULL, encoding="utf-8")))
    # companies needing recovery (empty/unknown), with a representative homepage
    need = {}
    for r in rows:
        c = r["company_name"].strip()
        if not c:
            continue
        if not has_value(r["total_funding"]) and "public" not in r["total_funding"].lower() and "government" not in r["total_funding"].lower():
            k = c.lower()
            if k not in need:
                need[k] = (c, r.get("homepage_url", "").strip())
            elif not need[k][1] and r.get("homepage_url", "").strip():
                need[k] = (c, r.get("homepage_url", "").strip())

    done = set()
    if os.path.exists(OUT):
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            done.add(r["company_name"].strip().lower())
    todo = [(c, hp) for k, (c, hp) in need.items() if k not in done]
    print(f"companies needing recovery: {len(need)} | already done {len(done)} | to do {len(todo)}", flush=True)

    new = not os.path.exists(OUT)
    fh = open(OUT, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=["company_name", "total_funding", "latest_round", "valuation", "key_investors", "status"])
    if new:
        w.writeheader(); fh.flush()
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for c, hp in todo:
            ex.submit(work, c, hp, w, fh)
    fh.close()
    print(f"\nDONE: {cnt['done']} companies in {time.monotonic()-t0:.0f}s | {cnt['found']} now have a value", flush=True)


if __name__ == "__main__":
    main()
