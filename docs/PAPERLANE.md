# Paperlane: interface and venue discovery

The application is now branded Paperlane. Its midnight navy, electric blue and coral interface replaces the previous ivory/green design. The hero contains three dimensional book-like blocks with pointer tilt, gentle vertical motion, a pause control and reduced-motion support. The orbit and manuscript-stack visual have been removed.

## Venue explorer

The directory is available without uploading a manuscript, once the private session initializes. Search venue titles, publishers and subjects; use list or card layouts and server-side pagination. Completed manuscripts retain the separate relevance-ranked recommendation mode. Both paths share the same strict eligibility and fee filters.

- Fee status: any, free to publish (reported), paid, or not verified.
- Maximum advertised APC with an explicit currency. Unknown amounts and other currencies are excluded; no exchange rates are inferred. Reported free venues fit any nonnegative budget. A maximum APC is not a cap on other charges or taxes.
- Existing venue type, coverage year, open access, Medline and active-status filters remain available.

## Price provenance

`datasets/venue_fees.json` is derived from the [DOAJ public journal CSV](https://doaj.org/docs/journal-csv), fetched on 3 November 2026. It contains 36,087 normalized ISSN keys; three ambiguous keys are excluded. The public CSV may lag live DOAJ records by up to 30 days, and individual journal records can be older.

Fees are joined to the 48,151-record venue dataset by exact print/electronic ISSN, never fuzzy title similarity. Conflicting matches become unknown. At this import, 4,384 venues have explicitly reported no APC and no other fees, 5,004 have reported charges, and 38,763 remain unknown. These counts include inactive venues; the default active filter reduces them.

The fee panel displays original-currency advertised APC amounts, additional-fee flags, record update date, retrieval date, and DOAJ/publisher policy links. It is not a personalized invoice: taxes, article type, waivers and institutional agreements can change the amount payable. Open access alone never implies free publication. Conference registration fees and hybrid publication routes generally remain unknown in this source.

Refresh with `python scripts/refresh_venue_fees.py`, then rebuild/restart the Flask service to reload its cached venue database. The importer validates the schema and uses an atomic snapshot replacement; download/schema failures preserve the previous snapshot. No manuscript or user data is sent to DOAJ. For a previously downloaded file, use `--csv path/to/doaj.csv`; the timestamp records import time.

## API

`POST /api/venues` proxies to the private Flask `/venues` endpoint with the existing internal authentication. Its JSON body accepts validated venue preferences plus `query` (up to 200 characters), `page` (1–10,000), and `page_size` (1–50; default 12). Response fields are `venues`, `total`, `page`, `page_size`, and `pages`. It performs directory browsing only and does not consume an analysis quota. `/api/recommend` still requires an owned completed analysis.

New fields shared by directory and recommendations: `fee_status`, nullable `max_apc`, and three-letter uppercase `currency`. No billing or payment collection is implemented.
