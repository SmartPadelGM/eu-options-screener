# EU Options Screener

A free, self-hosted, Finviz-style screener over the ~250 most liquid European
stocks that have listed options, tuned for a retail options trader running the
wheel (cash-secured puts / covered calls) and vertical spreads on DEGIRO.

It answers one question well: *"Which liquid, option-bearing EU underlyings
currently pass my fundamental + technical filters?"* — then hands off to
TradingView (IV / chart) and DEGIRO (option chain) via per-row links.

- **Data**: end-of-day via `yfinance`, refreshed once per trading day by a
  GitHub Actions cron that commits `data/screener_latest.parquet` back to the
  repo (which triggers a Streamlit Cloud redeploy).
- **Universe**: deduplicated union of EURO STOXX 50, AEX, CAC 40, DAX,
  IBEX 35, FTSE MIB, OMX Stockholm 30 and SMI constituents (~230–260 names),
  plus the four tradeable indices (^AEX, ^FCHI, ^GDAXI, ^STOXX50E) flagged
  `is_index=True`.
- **Cost**: €0. No API keys, no credit card.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (source .venv/bin/activate on Unix)
pip install -r requirements.txt

python src/build_universe.py    # scrape + validate -> data/universe.csv (~5 min)
python src/ingest.py            # pull metrics -> data/screener_latest.parquet (~15 min)
streamlit run app/streamlit_app.py
```

## Deploy (once)

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create an app from the
   repo with entry point `app/streamlit_app.py`.
3. Check the **Actions** tab: the `Daily data refresh` workflow runs weekdays
   at ~17:00 UTC (after EU close) and on manual `workflow_dispatch`. Each
   commit of fresh data redeploys the app.

## Quarterly universe refresh

Index constituents drift slowly. Every ~3 months:

```bash
python src/build_universe.py
git add data/universe.csv data/universe_build_log.txt
git commit -m "chore: quarterly universe refresh" && git push
```

The script scrapes the Wikipedia constituent pages, maps local tickers to
yfinance suffixes, **validates every ticker against Yahoo** (invalid guesses
are dropped and logged to `data/universe_build_log.txt`), dedups, and appends
the four index rows. It warns if any anchor ticker (ASML.AS, SAP.DE, MC.PA,
NESN.SW, …) is missing or the count leaves the 230–260 band.

## How the daily ingest stays robust

`yfinance` scrapes Yahoo's unofficial endpoints, so the ingest:

- uses a shared `curl_cffi` browser-impersonating session,
- fetches sequentially with a random 0.5–1.5 s sleep between tickers,
- retries each ticker 3× with exponential backoff,
- **merges instead of overwriting**: a ticker that fails today keeps
  yesterday's row (`last_updated` unchanged) rather than being blanked,
- writes refreshed / stale-kept / dropped counts to `data/ingest_log.txt`,
- never lets a single bad ticker abort the run.

## Known limitations

- **No implied volatility, IV rank, or Greeks.** No free API covers EU IV
  reliably; judge IV in TradingView via the per-row chart link.
- yfinance data quality varies for some EU names; occasional stale or missing
  fields are expected and handled by stale-keep. In the UI, a missing value
  never fails a filter unless you enable the "exclude missing" toggle.
- "Offers liquid options" is inferred from index membership, not live option
  volume — verify the actual chain in DEGIRO before trading.
- Universe changes are picked up only when you re-run `build_universe.py`.
- Cross-currency comparability (SEK/CHF/DKK names) uses a **static FX table**
  in `src/config.py` for the EUR-normalized `dollar_volume_eur` /
  `market_cap_eur` sort columns — refresh it by hand occasionally.
- `debt_to_equity` follows Yahoo's percent convention (150 = 1.5× equity).
- Index options (^AEX, ^FCHI, ^GDAXI, ^STOXX50E) are cash-settled and
  European-style: relevant for spreads only, the wheel does not apply.
- TradingView symbols for the four indices are best-effort mappings.
