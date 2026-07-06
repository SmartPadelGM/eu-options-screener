"""Daily ingest: read universe.csv, pull metrics per ticker from yfinance with
retries/backoff, merge with the previous snapshot (stale-keep failures), and
write data/screener_latest.parquet plus a run summary to data/ingest_log.txt.

A single bad ticker must never abort the run.
"""

import argparse
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

import config
import metrics

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover
    curl_requests = None


def make_session():
    """Shared browser-impersonating session; None lets yfinance use its own."""
    if curl_requests is None:
        return None
    try:
        return curl_requests.Session(impersonate="chrome")
    except Exception:
        return None


def fetch_one(ticker: str, session) -> dict | None:
    """One ticker -> raw metric dict, with retries + exponential backoff.
    Returns None when the ticker could not be refreshed."""
    last_exc = None
    for attempt in range(config.MAX_RETRIES):
        try:
            t = yf.Ticker(ticker, session=session)
            info = t.info or {}
            try:
                hist = t.history(period="2mo")
            except Exception:
                hist = None
            row = metrics.extract_raw_metrics(info, hist)
            if row["price"] is None:
                raise ValueError("no price in info or history")
            return row
        except Exception as exc:
            last_exc = exc
            time.sleep(config.BACKOFF_BASE_S * (2 ** attempt))
    print(f"  FAIL {ticker}: {type(last_exc).__name__}: {last_exc}", flush=True)
    return None


def run(universe_path: Path, out_path: Path, log_path: Path) -> int:
    started = datetime.now(timezone.utc)
    universe = pd.read_csv(universe_path, keep_default_na=False, dtype=str)
    universe["is_index"] = universe["is_index"].str.lower() == "true"
    session = make_session()
    today = started.date().isoformat()

    refreshed_rows: list[dict] = []
    failed: list[str] = []

    for i, urow in enumerate(universe.itertuples(index=False), 1):
        row = fetch_one(urow.ticker, session)
        if row is None:
            failed.append(urow.ticker)
        else:
            row.update({
                "ticker": urow.ticker,
                "name": urow.name,
                "country": urow.country or row.get("country") or "",
                "exchange_suffix": urow.exchange_suffix,
                "degiro_venue": urow.degiro_venue,
                "index_membership": urow.index_membership,
                "is_index": bool(urow.is_index),
                "last_updated": today,
            })
            refreshed_rows.append(row)
        if i % 25 == 0:
            print(f"  progress {i}/{len(universe)} "
                  f"(refreshed {len(refreshed_rows)}, failed {len(failed)})", flush=True)
        time.sleep(random.uniform(*config.SLEEP_RANGE_S))

    new_df = pd.DataFrame(refreshed_rows)
    if not new_df.empty:
        new_df["dividend_yield"] = metrics.normalize_dividend_yield(new_df["dividend_yield"])
        new_df = metrics.add_computed_fields(new_df)

    # Merge, don't overwrite: stale-keep previous rows for tickers that failed
    # today (or were skipped), as long as they are still in the universe.
    stale_kept: list[str] = []
    dropped: list[str] = []
    prev = pd.read_parquet(out_path) if out_path.exists() else None
    universe_set = set(universe["ticker"])
    refreshed_set = set(new_df["ticker"]) if not new_df.empty else set()

    if prev is not None:
        keep_mask = prev["ticker"].isin(universe_set - refreshed_set)
        kept_df = prev[keep_mask]
        stale_kept = sorted(kept_df["ticker"])
        final = pd.concat([new_df, kept_df], ignore_index=True)
    else:
        final = new_df
    dropped = sorted(universe_set - set(final["ticker"]) if not final.empty else universe_set)

    if final.empty:
        print("FATAL: nothing refreshed and no previous snapshot", flush=True)
        return 1

    for col in metrics.SNAPSHOT_COLUMNS:
        if col not in final.columns:
            final[col] = None
    final = final[metrics.SNAPSHOT_COLUMNS]
    final = final.sort_values("dollar_volume_eur", ascending=False, na_position="last")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(out_path, index=False)

    summary = [
        f"Ingest run {started.isoformat(timespec='seconds')}",
        f"  universe: {len(universe)}",
        f"  refreshed: {len(refreshed_rows)}",
        f"  stale-kept (failed today, kept previous row): {len(stale_kept)} {stale_kept}",
        f"  dropped (failed, no previous row): {len(dropped)} {dropped}",
        f"  snapshot rows: {len(final)} -> {out_path}",
    ]
    print("\n".join(summary), flush=True)
    log_path.write_text("\n".join(summary) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--universe", type=Path, default=config.UNIVERSE_CSV)
    p.add_argument("--out", type=Path, default=config.SNAPSHOT_PARQUET)
    p.add_argument("--log", type=Path, default=config.INGEST_LOG)
    a = p.parse_args()
    return run(a.universe, a.out, a.log)


if __name__ == "__main__":
    sys.exit(main())
