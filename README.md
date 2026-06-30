# RAISE Summit 2026 — Data Extract

Structured data extracted from the [RAISE Summit 2026](https://raisesummit.brella.io) Brella event platform (`api.brella.io`, JSON:API).

> ⚠️ **Private / internal use.** Contains attendee personal data (names, companies, titles, and where public, email/LinkedIn) from an EU event. Handle under GDPR — do not redistribute or use for unsolicited bulk outreach without a lawful basis.

## Datasets (`data/` CSV · `excel/` formatted XLSX)

| Dataset | Rows | Notes |
|---|---:|---|
| **Registrants** | 4,403 | Everyone registered: name, title, company, industry/function/persona. `joined_networking` flag marks the subset who activated Brella. |
| **Attendees** | 1,477 | Networking-active subset — richest contact data (email/LinkedIn/Twitter/website/pitch where the attendee made it public). |
| **Sponsors** | 141 | Exhibitors: level, category, subtitle, booth map link, social, rep count. |
| **Speakers** | 372 | Name, job title, company, full bio. |

Contact fields are **sparse by design** — Brella only exposes email/LinkedIn for people who opted to make them public (≈68 emails, ≈207 LinkedIn among attendees). Names + companies are near-complete and suitable for external enrichment.

## Layout

```
data/                       raw CSV exports
excel/                      formatted workbooks (per-dataset + combined MASTER)
scrapers/                   the paginating scrapers, one per endpoint
make_excel.py               rebuilds excel/ from data/
```

## Re-running the scrapers

The Brella `access-token`/`client` pair is short-lived (a few hours). Grab a fresh
pair from your browser DevTools (any `api.brella.io` request → request headers),
then:

```bash
export BRELLA_ACCESS_TOKEN=...     # 'access-token' header
export BRELLA_CLIENT=...           # 'client' header
export BRELLA_UID=you@example.com  # 'uid' header

python3 scrapers/scrape_raise_registrants.py   # writes raise_registrants.csv
python3 scrapers/scrape_raise_attendees.py
python3 scrapers/scrape_raise_sponsors.py
python3 scrapers/scrape_raise_speakers.py
python3 make_excel.py                           # rebuild formatted workbooks
```

Each scraper paginates at the server cap (120/page) with a polite delay.

## Enrichment (`enrichment/`)

Every person was enriched via one Linkup structured-output search (`depth=standard`) — LinkedIn, person bio, company homepage, what the company does, what it's building, and funding. Built with `enrich_full.py`; `recover_funding.py` does a dedicated second-pass funding search; `build_workbooks.py` produces the formatted Excel and the funding tiering.

| Workbook | Rows | Notes |
|---|---:|---|
| `raise_enrichment_full.xlsx` | 4,403 | all registrants, + `funding_tier` column |
| `raise_speakers_enriched.xlsx` | 372 | speakers |
| `raise_cxo_enriched.xlsx` | 260 | CXO Summit executives (separate gated list, not in the Brella registrant API) |
| `companies_by_funding.xlsx` | 2,672 | unique companies prioritized by funding tier |

**Funding tiers** (capital raised; investors/public/government separated via the company description):
`Tier 0` ≥ $500M · `Tier 1` $100M–$500M · `Tier 2` < $100M · `Tier 3` none/unknown · plus `Public` / `Investor` / `Established` / `Government` / `Non-profit`.

> Caveat: the funding figure is best-effort — for very large/established entities the source sometimes reports valuation, AUM, or revenue rather than capital raised. Tiers are most reliable for the startup/scaleup population.

## Endpoints used

- `GET /api/events/raisesummit2026/registrants` — full 4,403 registrant pool
- `GET /api/events/raisesummit2026/attendees` — networking-active profiles (richest fields)
- `GET /api/events/raisesummit2026/sponsors`
- `GET /api/events/raisesummit2026/speakers`

All accept `page[size]` / `page[number]`; attendees/registrants also accept `search=`.
