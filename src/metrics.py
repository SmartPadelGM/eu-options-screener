"""Field mapping yfinance -> screener columns, unit normalization, and
computed/derived fields. All values are nullable: NULL means "data
unavailable", never "fails filter"."""

import math

import pandas as pd

import config

# Fractions from yfinance that we store as whole-number percentages.
FRACTION_TO_PCT_FIELDS = [
    "roe", "roa", "gross_margin", "operating_margin", "net_margin",
    "earnings_growth", "revenue_growth",
]

SNAPSHOT_COLUMNS = [
    # identity
    "ticker", "name", "sector", "industry", "country", "currency",
    "exchange_suffix", "degiro_venue", "index_membership", "is_index",
    "notes", "last_updated",
    # valuation
    "market_cap", "pe_trailing", "pe_forward", "price_to_book",
    "ev_to_ebitda", "peg", "dividend_yield",
    # profitability
    "roe", "roa", "gross_margin", "operating_margin", "net_margin",
    # growth
    "earnings_growth", "revenue_growth",
    # balance sheet
    "debt_to_equity", "current_ratio", "quick_ratio",
    # price / technical
    "price", "beta", "avg_volume", "sma20", "sma50", "sma200",
    "week52_high", "week52_low",
    # computed
    "dollar_volume", "dollar_volume_eur", "market_cap_eur",
    "pct_from_52w_high", "pct_from_52w_low",
    "price_vs_sma20", "price_vs_sma50", "price_vs_sma200",
    "tradingview_url", "degiro_note",
]


def _num(info: dict, *keys):
    """First numeric value among info[keys], else None."""
    for k in keys:
        v = info.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            return float(v)
    return None


def extract_raw_metrics(info: dict, history: pd.DataFrame | None) -> dict:
    """Map a yfinance .info dict (+ recent history for SMA20) to raw columns.
    Percent-like fractions are converted here; dividend_yield is left RAW and
    normalized batch-wise (see normalize_dividend_yield)."""
    row = {
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": info.get("currency"),
        "market_cap": _num(info, "marketCap"),
        "pe_trailing": _num(info, "trailingPE"),
        "pe_forward": _num(info, "forwardPE"),
        "price_to_book": _num(info, "priceToBook"),
        "ev_to_ebitda": _num(info, "enterpriseToEbitda"),
        "peg": _num(info, "trailingPegRatio", "pegRatio"),
        "dividend_yield": _num(info, "dividendYield"),
        "roe": _num(info, "returnOnEquity"),
        "roa": _num(info, "returnOnAssets"),
        "gross_margin": _num(info, "grossMargins"),
        "operating_margin": _num(info, "operatingMargins"),
        "net_margin": _num(info, "profitMargins"),
        "earnings_growth": _num(info, "earningsGrowth", "earningsQuarterlyGrowth"),
        "revenue_growth": _num(info, "revenueGrowth"),
        "debt_to_equity": _num(info, "debtToEquity"),   # Yahoo convention: percent
        "current_ratio": _num(info, "currentRatio"),
        "quick_ratio": _num(info, "quickRatio"),
        "price": _num(info, "currentPrice", "regularMarketPrice",
                      "regularMarketPreviousClose"),
        "beta": _num(info, "beta"),
        "avg_volume": _num(info, "averageVolume", "averageVolume10days"),
        "week52_high": _num(info, "fiftyTwoWeekHigh"),
        "week52_low": _num(info, "fiftyTwoWeekLow"),
        "sma50": _num(info, "fiftyDayAverage"),
        "sma200": _num(info, "twoHundredDayAverage"),
        "sma20": None,
    }
    if history is not None and not history.empty and "Close" in history:
        closes = history["Close"].dropna().tail(20)
        if len(closes) >= 15:
            row["sma20"] = float(closes.mean())
        if row["price"] is None and len(closes):
            row["price"] = float(closes.iloc[-1])

    for f in FRACTION_TO_PCT_FIELDS:
        if row[f] is not None:
            row[f] = row[f] * 100.0
    return row


def normalize_dividend_yield(series: pd.Series) -> pd.Series:
    """yfinance returns dividendYield as a fraction (0.034) or a percent (3.4)
    depending on version. Decide the unit once per batch (median > 1 => the
    batch is already in percent) and store consistently as percent."""
    vals = series.dropna()
    if vals.empty:
        return series
    if vals.median() > 1.0:
        return series
    return series * 100.0


def _tv_url(ticker: str, suffix: str, is_index: bool) -> str | None:
    if is_index:
        sym = config.TV_INDEX_SYMBOLS.get(ticker)
        return f"https://www.tradingview.com/chart/?symbol={sym}" if sym else None
    prefix = config.SUFFIX_TO_TV_PREFIX.get(suffix)
    if not prefix:
        return None
    local = ticker[: -len(suffix)] if suffix and ticker.endswith(suffix) else ticker
    local = local.replace("-", "_")  # TradingView uses INVE_B, not INVE-B
    return f"https://www.tradingview.com/chart/?symbol={prefix}:{local}"


def add_computed_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Derive dollar volume, EUR-normalized sizes, 52w distances, MA flags,
    and the deep-link/note columns. Mutates and returns df."""
    fx = df["currency"].map(config.FX_TO_EUR).fillna(1.0)

    df["dollar_volume"] = df["avg_volume"] * df["price"]
    df["dollar_volume_eur"] = df["dollar_volume"] * fx
    df["market_cap_eur"] = df["market_cap"] * fx

    df["pct_from_52w_high"] = (df["price"] / df["week52_high"] - 1.0) * 100.0
    df["pct_from_52w_low"] = (df["price"] / df["week52_low"] - 1.0) * 100.0

    for n in (20, 50, 200):
        price, sma = df["price"], df[f"sma{n}"]
        flag = pd.Series(pd.NA, index=df.index, dtype="boolean")
        both = price.notna() & sma.notna()
        flag[both] = price[both] > sma[both]
        df[f"price_vs_sma{n}"] = flag

    df["tradingview_url"] = [
        _tv_url(t, s if isinstance(s, str) else "", bool(ix))
        for t, s, ix in zip(df["ticker"], df["exchange_suffix"], df["is_index"])
    ]
    df["degiro_note"] = [
        (f"{config.INDEX_NOTE} Trades via {venue}." if ix
         else f"Options trade on {venue}.")
        for venue, ix in zip(df["degiro_venue"], df["is_index"])
    ]
    df["notes"] = [config.INDEX_NOTE if ix else "" for ix in df["is_index"]]
    return df
