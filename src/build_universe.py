"""Build data/universe.csv: scrape index constituents from Wikipedia, map to
yfinance tickers, validate every ticker against Yahoo, dedup, and append the
four tradeable index instruments.

Run manually ~quarterly:  python src/build_universe.py
Options:
  --no-validate   skip the yfinance validation pass (offline/dev only)
"""

import argparse
import random
import re
import sys
import time
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

import config

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover
    curl_requests = None

TICKER_COL_RE = re.compile(r"ticker|symbol", re.I)
NAME_COL_RE = re.compile(r"company|name|constituent|corporation", re.I)
EXCHANGE_COL_RE = re.compile(r"listing|exchange|country|registered|office|location", re.I)

log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    log_lines.append(msg)


def get_session():
    if curl_requests is not None:
        return curl_requests.Session(impersonate="chrome")
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    return s


def fetch_tables(session, url: str) -> list[pd.DataFrame]:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def clean_cell(val) -> str:
    if pd.isna(val):
        return ""
    s = str(val)
    s = re.sub(r"\[[^\]]*\]", "", s)  # strip footnote markers like [a], [1]
    return s.strip()


def find_constituent_table(tables: list[pd.DataFrame], min_rows: int = 15):
    """Pick the table that looks like a constituents list: has a ticker-ish
    column and enough rows. Returns (df, ticker_col, name_col, exchange_col)."""
    best = None
    for df in tables:
        cols = [str(c) for c in df.columns]
        # flatten MultiIndex headers
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = [" ".join(str(x) for x in tup).strip() for tup in df.columns]
            cols = list(df.columns)
        tick_cols = [c for c in cols if TICKER_COL_RE.search(str(c))]
        if not tick_cols or len(df) < min_rows:
            continue
        name_cols = [
            c for c in cols
            if NAME_COL_RE.search(str(c)) and "corporate" not in str(c).lower()
        ]
        exch_cols = [c for c in cols if EXCHANGE_COL_RE.search(str(c))]
        cand = (df, tick_cols[0], name_cols[0] if name_cols else None,
                exch_cols[0] if exch_cols else None)
        # prefer the largest plausible table
        if best is None or len(df) > len(best[0]):
            best = cand
    return best


def infer_suffix_from_exchange(text: str) -> str | None:
    low = text.lower()
    for kw, suffix in config.EXCHANGE_KEYWORD_TO_SUFFIX.items():
        if kw in low:
            return suffix
    return None


def to_yf_ticker(raw: str, default_suffix: str | None, exchange_text: str) -> str | None:
    """Map a Wikipedia ticker cell to a yfinance ticker, or None if unmappable."""
    t = clean_cell(raw).upper()
    if not t:
        return None
    # already has a known suffix (e.g. "ABI.BR")
    for suffix in config.SUFFIX_TO_COUNTRY:
        if t.endswith(suffix):
            local = t[: -len(suffix)]
            return local.replace(" ", "-") + suffix
    # strip a leading exchange prefix like "BME:" if present
    if ":" in t:
        t = t.split(":")[-1].strip()
    suffix = default_suffix or infer_suffix_from_exchange(exchange_text)
    if suffix is None:
        return None
    return t.replace(" ", "-") + suffix


def apply_overrides(ticker: str) -> str:
    return config.TICKER_OVERRIDES.get(ticker, ticker)


def scrape_index(session, source: dict) -> list[dict]:
    label, url = source["label"], source["url"]
    tables = fetch_tables(session, url)
    picked = find_constituent_table(tables)
    if picked is None:
        log(f"ERROR [{label}] no constituents table found at {url}")
        return []
    df, tick_col, name_col, exch_col = picked
    log(f"[{label}] table with {len(df)} rows; ticker col='{tick_col}', "
        f"name col='{name_col}', exchange col='{exch_col}'")
    rows = []
    for _, r in df.iterrows():
        exchange_text = clean_cell(r[exch_col]) if exch_col else ""
        yft = to_yf_ticker(r[tick_col], source["default_suffix"], exchange_text)
        if yft is None:
            log(f"  WARN [{label}] unmappable ticker cell: {clean_cell(r[tick_col])!r} "
                f"(exchange text {exchange_text!r})")
            continue
        rows.append({
            "ticker": apply_overrides(yft),
            "name": clean_cell(r[name_col]) if name_col else yft,
            "index_label": label,
        })
    return rows


def validate_tickers(session, tickers: list[str]) -> dict[str, bool]:
    """True if yfinance returns a price for the ticker."""
    import yfinance as yf

    results: dict[str, bool] = {}
    for i, tkr in enumerate(tickers, 1):
        ok = False
        for attempt in range(2):
            try:
                t = yf.Ticker(tkr, session=session)
                price = None
                try:
                    price = t.fast_info["lastPrice"]
                except Exception:
                    pass
                if price is None:
                    info = t.info or {}
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                if price is not None and not pd.isna(price):
                    ok = True
                    break
            except Exception as exc:
                if attempt == 0:
                    time.sleep(2.0)
                else:
                    log(f"  validate error {tkr}: {type(exc).__name__}: {exc}")
        results[tkr] = ok
        if not ok:
            log(f"  DROP {tkr}: no price from yfinance")
        if i % 25 == 0:
            log(f"  validated {i}/{len(tickers)}")
        time.sleep(random.uniform(*config.VALIDATE_SLEEP_RANGE_S))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    session = get_session()
    log(f"Universe build started {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    all_rows: list[dict] = []
    for source in config.INDEX_SOURCES:
        try:
            all_rows.extend(scrape_index(session, source))
        except Exception as exc:
            log(f"ERROR [{source['label']}] scrape failed: {type(exc).__name__}: {exc}")
        time.sleep(1.0)

    if not all_rows:
        log("FATAL: no constituents scraped at all")
        return 1

    # Dedup on yfinance ticker, aggregating index membership.
    by_ticker: dict[str, dict] = {}
    for r in all_rows:
        cur = by_ticker.get(r["ticker"])
        if cur is None:
            by_ticker[r["ticker"]] = {
                "ticker": r["ticker"],
                "name": r["name"],
                "indices": [r["index_label"]],
            }
        else:
            if r["index_label"] not in cur["indices"]:
                cur["indices"].append(r["index_label"])
            # prefer the longer (usually fuller) company name
            if len(r["name"]) > len(cur["name"]):
                cur["name"] = r["name"]

    tickers = sorted(by_ticker)
    log(f"Scraped {len(all_rows)} rows -> {len(tickers)} unique tickers before validation")

    if args.no_validate:
        valid = {t: True for t in tickers}
    else:
        valid = validate_tickers(session, tickers)

    kept = [t for t in tickers if valid[t]]
    dropped = [t for t in tickers if not valid[t]]
    log(f"Validation: kept {len(kept)}, dropped {len(dropped)} {dropped}")

    records = []
    for t in kept:
        suffix = "." + t.rsplit(".", 1)[-1]
        meta = by_ticker[t]
        records.append({
            "ticker": t,
            "name": meta["name"],
            "country": config.SUFFIX_TO_COUNTRY.get(suffix, ""),
            "exchange_suffix": suffix,
            "degiro_venue": config.SUFFIX_TO_DEGIRO_VENUE.get(suffix, ""),
            "index_membership": ", ".join(meta["indices"]),
            "is_index": False,
        })

    # Trim if implausibly large (union should land ~230-260).
    if len(records) > config.MAX_UNIVERSE_STOCKS:
        log(f"Universe {len(records)} > {config.MAX_UNIVERSE_STOCKS}; trimming to "
            f"top {config.TRIM_TO} by 20d average dollar volume")
        import yfinance as yf

        dv = {}
        for rec in records:
            try:
                h = yf.Ticker(rec["ticker"], session=session).history(period="1mo")
                dv[rec["ticker"]] = float((h["Close"] * h["Volume"]).tail(20).mean())
            except Exception:
                dv[rec["ticker"]] = 0.0
            time.sleep(random.uniform(*config.VALIDATE_SLEEP_RANGE_S))
        records.sort(key=lambda r: dv.get(r["ticker"], 0.0), reverse=True)
        records = records[: config.TRIM_TO]
        records.sort(key=lambda r: r["ticker"])

    n_stocks = len(records)

    for inst in config.INDEX_INSTRUMENTS:
        records.append({
            "ticker": inst["ticker"],
            "name": inst["name"],
            "country": inst["country"],
            "exchange_suffix": "",
            "degiro_venue": inst["degiro_venue"],
            "index_membership": "",
            "is_index": True,
        })

    df = pd.DataFrame.from_records(records)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.UNIVERSE_CSV, index=False)
    log(f"Wrote {config.UNIVERSE_CSV}: {n_stocks} stocks + "
        f"{len(config.INDEX_INSTRUMENTS)} index rows")

    missing_anchors = [a for a in config.ANCHOR_TICKERS if a not in set(df["ticker"])]
    if missing_anchors:
        log(f"WARN: missing anchor tickers: {missing_anchors}")
    else:
        log(f"All {len(config.ANCHOR_TICKERS)} anchor tickers present")
    if not 230 <= n_stocks <= 260:
        log(f"WARN: stock count {n_stocks} outside expected 230-260 range")

    config.UNIVERSE_BUILD_LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return 0 if not missing_anchors else 2


if __name__ == "__main__":
    sys.exit(main())
