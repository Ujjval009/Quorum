# Data

Local data artifacts for development live here.

- `downloads/` holds raw SEC EDGAR 10-K HTML filings, grouped by year.
- Downloaded payloads are gitignored because the corpus can get large.
- Manifest at `downloads/manifest.json` — lists ticker, year, report_date, local_path for each filing.
- 25 filings total: AAPL, MSFT, NVDA, AMZN, GOOGL (2021–2025).
- Ingest with: `cd backend && uv run python scripts/ingest_html.py`
