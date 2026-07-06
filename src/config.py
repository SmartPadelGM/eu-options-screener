"""Central configuration: paths, suffix/venue maps, index sources, tuning knobs."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

UNIVERSE_CSV = DATA_DIR / "universe.csv"
SNAPSHOT_PARQUET = DATA_DIR / "screener_latest.parquet"
INGEST_LOG = DATA_DIR / "ingest_log.txt"
UNIVERSE_BUILD_LOG = DATA_DIR / "universe_build_log.txt"

# ---------------------------------------------------------------------------
# Exchange suffix maps (yfinance suffix -> metadata)
# ---------------------------------------------------------------------------

SUFFIX_TO_COUNTRY = {
    ".AS": "Netherlands",
    ".PA": "France",
    ".BR": "Belgium",
    ".DE": "Germany",
    ".MC": "Spain",
    ".MI": "Italy",
    ".ST": "Sweden",
    ".SW": "Switzerland",
    ".HE": "Finland",
    ".CO": "Denmark",
}

# Where the *options* on this underlying trade, for DEGIRO routing context.
SUFFIX_TO_DEGIRO_VENUE = {
    ".AS": "Euronext",
    ".PA": "Euronext",
    ".BR": "Euronext",
    ".DE": "Eurex",
    ".SW": "Eurex",
    ".HE": "Eurex",
    ".CO": "Eurex",
    ".MI": "IDEM",           # also mirrored on Eurex for many names
    ".MC": "MEFF",           # also mirrored on Eurex for many names
    ".ST": "Eurex / Nasdaq Nordic",
}

# TradingView exchange prefixes for chart deep links.
SUFFIX_TO_TV_PREFIX = {
    ".AS": "EURONEXT",
    ".PA": "EURONEXT",
    ".BR": "EURONEXT",
    ".DE": "XETR",
    ".MC": "BME",
    ".MI": "MIL",
    ".ST": "OMXSTO",
    ".SW": "SIX",
    ".HE": "OMXHEX",
    ".CO": "OMXCOP",
}

# Best-effort TradingView symbols for the four tradeable indices.
TV_INDEX_SYMBOLS = {
    "^AEX": "EURONEXT:AEX",
    "^FCHI": "EURONEXT:PX1",
    "^GDAXI": "XETR:DAX",
    "^STOXX50E": "TVC:SX5E",
}

# Static FX to EUR, used ONLY to make dollar_volume / market_cap comparable
# across currencies for sorting and filtering. Refresh occasionally by hand.
FX_TO_EUR = {
    "EUR": 1.0,
    "CHF": 1.06,
    "SEK": 0.088,
    "DKK": 0.134,
    "NOK": 0.085,
    "USD": 0.90,
    "GBp": 0.0117,
}

# ---------------------------------------------------------------------------
# Universe sources (Wikipedia constituent pages)
# ---------------------------------------------------------------------------
# default_suffix=None means the page mixes exchanges (EURO STOXX 50) and the
# suffix must be inferred per row from an exchange/country-ish column.

INDEX_SOURCES = [
    {
        "label": "EURO STOXX 50",
        "url": "https://en.wikipedia.org/wiki/EURO_STOXX_50",
        "default_suffix": None,
    },
    {
        "label": "AEX",
        "url": "https://en.wikipedia.org/wiki/AEX_index",
        "default_suffix": ".AS",
    },
    {
        "label": "CAC 40",
        "url": "https://en.wikipedia.org/wiki/CAC_40",
        "default_suffix": ".PA",
    },
    {
        "label": "DAX",
        "url": "https://en.wikipedia.org/wiki/DAX",
        "default_suffix": ".DE",
    },
    {
        "label": "IBEX 35",
        "url": "https://en.wikipedia.org/wiki/IBEX_35",
        "default_suffix": ".MC",
    },
    {
        "label": "FTSE MIB",
        "url": "https://en.wikipedia.org/wiki/FTSE_MIB",
        "default_suffix": ".MI",
    },
    {
        "label": "OMX Stockholm 30",
        "url": "https://en.wikipedia.org/wiki/OMX_Stockholm_30",
        "default_suffix": ".ST",
    },
    {
        "label": "SMI",
        "url": "https://en.wikipedia.org/wiki/Swiss_Market_Index",
        "default_suffix": ".SW",
    },
]

# Keyword -> suffix, used to infer the exchange for EURO STOXX 50 rows from
# whatever exchange/listing/country column the Wikipedia table offers.
EXCHANGE_KEYWORD_TO_SUFFIX = {
    "amsterdam": ".AS",
    "netherlands": ".AS",
    "paris": ".PA",
    "france": ".PA",
    "brussels": ".BR",
    "belgium": ".BR",
    "frankfurt": ".DE",
    "xetra": ".DE",
    "germany": ".DE",
    "madrid": ".MC",
    "spain": ".MC",
    "milan": ".MI",
    "borsa italiana": ".MI",
    "italy": ".MI",
    "stockholm": ".ST",
    "sweden": ".ST",
    "zurich": ".SW",
    "six": ".SW",
    "switzerland": ".SW",
    "helsinki": ".HE",
    "finland": ".HE",
    "copenhagen": ".CO",
    "denmark": ".CO",
    "dublin": ".AS",
    "ireland": ".AS",
    "luxembourg": ".PA",
}

# Manual fixes for Wikipedia ticker cells that don't map cleanly to Yahoo
# (applied after suffix mapping). Extend when the build log shows drops.
TICKER_OVERRIDES = {
    # Yahoo renamed Roche's Genussschein ROG.SW -> ROP.SW ("ROCHE PS")
    "ROG.SW": "ROP.SW",
}

# The four tradeable index instruments, added as their own rows.
INDEX_INSTRUMENTS = [
    {
        "ticker": "^AEX",
        "name": "AEX Index",
        "country": "Netherlands",
        "degiro_venue": "Euronext Amsterdam",
    },
    {
        "ticker": "^FCHI",
        "name": "CAC 40 Index",
        "country": "France",
        "degiro_venue": "Euronext Paris",
    },
    {
        "ticker": "^GDAXI",
        "name": "DAX Index",
        "country": "Germany",
        "degiro_venue": "Eurex",
    },
    {
        "ticker": "^STOXX50E",
        "name": "EURO STOXX 50 Index",
        "country": "Europe",
        "degiro_venue": "Eurex",
    },
]

INDEX_NOTE = (
    "Index options: cash-settled, European-style. No share assignment, "
    "so the wheel does not apply - spreads only."
)

# Sanity anchors: a correct universe build must contain all of these.
ANCHOR_TICKERS = [
    "ASML.AS", "ADYEN.AS", "INGA.AS", "PRX.AS", "HEIA.AS",
    "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "BNP.PA", "SU.PA",
    "ABI.BR",
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "BAS.DE", "BMW.DE",
    "VOW3.DE", "MBG.DE", "IFX.DE",
    "ITX.MC", "SAN.MC", "IBE.MC",
    "ISP.MI", "ENEL.MI", "ENI.MI", "UCG.MI",
    "NESN.SW", "NOVN.SW",
    "ROP.SW",   # Roche Genussschein; Yahoo renamed ROG.SW -> ROP.SW

    "INVE-B.ST",
]

# ---------------------------------------------------------------------------
# Ingest tuning
# ---------------------------------------------------------------------------

SLEEP_RANGE_S = (0.5, 1.5)      # random sleep between tickers
MAX_RETRIES = 3                 # per-ticker retries
BACKOFF_BASE_S = 1.5            # exponential backoff base (1.5, 3, 6 ...)
VALIDATE_SLEEP_RANGE_S = (0.2, 0.6)
MAX_UNIVERSE_STOCKS = 280       # trim to top 250 by dollar volume above this
TRIM_TO = 250
