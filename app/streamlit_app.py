"""EU Options Screener - Finviz-style daily screener over ~250 liquid,
option-bearing European underlyings. Data: end-of-day snapshot refreshed by CI.

Filtering rule: a NULL never fails a numeric filter unless the user opts in
via the "exclude missing" toggle.
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import presets as P

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "screener_latest.parquet"

st.set_page_config(page_title="EU Options Screener", page_icon="🎯", layout="wide")


@st.cache_data(ttl=3600)
def load_data(mtime: float) -> pd.DataFrame:
    return pd.read_parquet(SNAPSHOT)


if not SNAPSHOT.exists():
    st.error("No snapshot found. Run `python src/ingest.py` first.")
    st.stop()

df = load_data(os.path.getmtime(SNAPSHOT))

# ---------------------------------------------------------------------------
# Session state / presets
# ---------------------------------------------------------------------------

for key, val in P.DEFAULTS.items():
    st.session_state.setdefault(key, val)


def nearest_dv_step(value_m: float) -> int:
    steps = [s for s in P.DOLLAR_VOLUME_STEPS_M if s <= value_m]
    return steps[-1] if steps else 0


def apply_preset() -> None:
    choice = st.session_state["preset_choice"]
    if choice == P.CUSTOM:
        return
    for key, val in P.DEFAULTS.items():
        st.session_state[key] = val
    for key, val in P.PRESETS[choice].items():
        if val == P.P90_DOLLAR_VOLUME:
            p90 = df["dollar_volume_eur"].quantile(0.9)
            val = nearest_dv_step((p90 or 0) / 1e6)
        st.session_state[key] = val


st.sidebar.title("EU Options Screener")
st.sidebar.selectbox(
    "Preset", [P.CUSTOM] + list(P.PRESETS), key="preset_choice",
    on_change=apply_preset,
    help="Applying a preset resets all filters, then sets the preset's values.",
)

st.sidebar.checkbox(
    "Exclude rows with missing data from numeric filters",
    key="f_excl_missing",
    help="Off (default): a stock missing e.g. ROE is NOT excluded by an ROE filter.",
)

# ---------------------------------------------------------------------------
# Filter widgets
# ---------------------------------------------------------------------------


def num_input(container, label, key, **kw):
    # value comes from session state (seeded from DEFAULTS / preset callback);
    # None renders as an empty input meaning "filter off".
    container.number_input(label, key=key, value=st.session_state[key],
                           placeholder="off", **kw)


with st.sidebar.expander("Liquidity", expanded=True):
    st.select_slider(
        "Min avg daily volume (EUR M)", options=P.DOLLAR_VOLUME_STEPS_M,
        key="f_dv_min_m",
        help="dollar_volume = avg_volume x price, FX-normalized to EUR. "
             "The key option-tradeability proxy.",
    )
    num_input(st, "Min market cap (EUR B)", "f_mcap_min_b", min_value=0.0, step=1.0)
    num_input(st, "Min avg share volume (M/day)", "f_avgvol_min_m", min_value=0.0, step=0.5)

with st.sidebar.expander("Valuation"):
    num_input(st, "Max P/E (trailing)", "f_pe_max", min_value=0.0, step=1.0)
    num_input(st, "Max P/E (forward)", "f_fpe_max", min_value=0.0, step=1.0)
    num_input(st, "Max price/book", "f_ptb_max", min_value=0.0, step=0.5)
    num_input(st, "Max EV/EBITDA", "f_evebitda_max", min_value=0.0, step=1.0)
    num_input(st, "Max PEG", "f_peg_max", min_value=0.0, step=0.25)
    num_input(st, "Min dividend yield (%)", "f_divyield_min", min_value=0.0, step=0.5)

with st.sidebar.expander("Quality"):
    num_input(st, "Min ROE (%)", "f_roe_min", step=1.0)
    num_input(st, "Min ROA (%)", "f_roa_min", step=1.0)
    num_input(st, "Min net margin (%)", "f_netmargin_min", step=1.0)
    num_input(st, "Min operating margin (%)", "f_opmargin_min", step=1.0)
    num_input(st, "Max debt/equity (Yahoo %: 150 = 1.5x)", "f_de_max",
              min_value=0.0, step=25.0)
    num_input(st, "Min current ratio", "f_currratio_min", min_value=0.0, step=0.25)

with st.sidebar.expander("Growth"):
    num_input(st, "Min earnings growth (%)", "f_egrowth_min", step=5.0)
    num_input(st, "Min revenue growth (%)", "f_rgrowth_min", step=5.0)

with st.sidebar.expander("Technical"):
    st.checkbox("Price above SMA20", key="f_above_sma20")
    st.checkbox("Price above SMA50", key="f_above_sma50")
    st.checkbox("Price above SMA200", key="f_above_sma200")
    c1, c2 = st.columns(2)
    num_input(c1, "% from 52w high ≥", "f_52high_min", step=5.0)
    num_input(c2, "% from 52w high ≤", "f_52high_max", step=5.0)
    c3, c4 = st.columns(2)
    num_input(c3, "% from 52w low ≥", "f_52low_min", step=5.0)
    num_input(c4, "% from 52w low ≤", "f_52low_max", step=5.0)
    c5, c6 = st.columns(2)
    num_input(c5, "Beta ≥", "f_beta_min", step=0.1)
    num_input(c6, "Beta ≤", "f_beta_max", step=0.1)


def options_of(col: str, split=False) -> list[str]:
    vals = df[col].dropna()
    if split:
        vals = vals.str.split(",").explode().str.strip()
    return sorted(v for v in vals.unique() if v)


with st.sidebar.expander("Categorical"):
    st.radio("Instruments",
             [P.INSTRUMENT_ALL, P.INSTRUMENT_STOCKS, P.INSTRUMENT_INDICES],
             key="f_instruments")
    st.multiselect("Sector", options_of("sector"), key="f_sectors")
    st.multiselect("Country", options_of("country"), key="f_countries")
    st.multiselect("Index membership", options_of("index_membership", split=True),
                   key="f_indices")
    st.multiselect("DEGIRO options venue", options_of("degiro_venue"), key="f_venues")

# ---------------------------------------------------------------------------
# Apply filters (NULL-tolerant)
# ---------------------------------------------------------------------------

ss = st.session_state
excl_missing = ss["f_excl_missing"]
mask = pd.Series(True, index=df.index)


def bound(col: str, value, kind: str) -> None:
    """AND a min/max condition into the mask; NULLs pass unless opted out."""
    global mask
    if value is None:
        return
    cond = (df[col] >= value if kind == "min" else df[col] <= value).fillna(False)
    if not excl_missing:
        cond = cond | df[col].isna()
    mask &= cond


bound("dollar_volume_eur", ss["f_dv_min_m"] * 1e6 if ss["f_dv_min_m"] else None, "min")
bound("market_cap_eur", ss["f_mcap_min_b"] * 1e9 if ss["f_mcap_min_b"] else None, "min")
bound("avg_volume", ss["f_avgvol_min_m"] * 1e6 if ss["f_avgvol_min_m"] else None, "min")
bound("pe_trailing", ss["f_pe_max"], "max")
bound("pe_forward", ss["f_fpe_max"], "max")
bound("price_to_book", ss["f_ptb_max"], "max")
bound("ev_to_ebitda", ss["f_evebitda_max"], "max")
bound("peg", ss["f_peg_max"], "max")
bound("dividend_yield", ss["f_divyield_min"], "min")
bound("roe", ss["f_roe_min"], "min")
bound("roa", ss["f_roa_min"], "min")
bound("net_margin", ss["f_netmargin_min"], "min")
bound("operating_margin", ss["f_opmargin_min"], "min")
bound("debt_to_equity", ss["f_de_max"], "max")
bound("current_ratio", ss["f_currratio_min"], "min")
bound("earnings_growth", ss["f_egrowth_min"], "min")
bound("revenue_growth", ss["f_rgrowth_min"], "min")
bound("pct_from_52w_high", ss["f_52high_min"], "min")
bound("pct_from_52w_high", ss["f_52high_max"], "max")
bound("pct_from_52w_low", ss["f_52low_min"], "min")
bound("pct_from_52w_low", ss["f_52low_max"], "max")
bound("beta", ss["f_beta_min"], "min")
bound("beta", ss["f_beta_max"], "max")

for n in (20, 50, 200):
    if ss[f"f_above_sma{n}"]:
        flag = df[f"price_vs_sma{n}"]
        cond = flag.fillna(not excl_missing).astype(bool)
        mask &= cond

if ss["f_instruments"] == P.INSTRUMENT_STOCKS:
    mask &= ~df["is_index"]
elif ss["f_instruments"] == P.INSTRUMENT_INDICES:
    mask &= df["is_index"]

if ss["f_sectors"]:
    mask &= df["sector"].isin(ss["f_sectors"])
if ss["f_countries"]:
    mask &= df["country"].isin(ss["f_countries"])
if ss["f_indices"]:
    pat = "|".join(map(re.escape, ss["f_indices"]))
    mask &= df["index_membership"].fillna("").str.contains(pat)
if ss["f_venues"]:
    mask &= df["degiro_venue"].isin(ss["f_venues"])

result = df[mask].sort_values("dollar_volume_eur", ascending=False, na_position="last")

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

st.subheader(f"{len(result)} of {len(df)} match")
last = df["last_updated"].dropna().max()
st.caption(f"End-of-day data via yfinance · snapshot last updated {last} · "
           "sizes FX-normalized to EUR · IV & chains: use the TradingView/DEGIRO "
           "links per row.")

view = result.assign(
    dollar_volume_eur_m=result["dollar_volume_eur"] / 1e6,
    market_cap_eur_b=result["market_cap_eur"] / 1e9,
)

display_cols = {
    "ticker": st.column_config.TextColumn("Ticker"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sector": st.column_config.TextColumn("Sector"),
    "country": st.column_config.TextColumn("Country"),
    "price": st.column_config.NumberColumn("Price", format="%.2f"),
    "currency": st.column_config.TextColumn("Ccy"),
    "dollar_volume_eur_m": st.column_config.NumberColumn("€ Vol/day (M)", format="%.1f"),
    "market_cap_eur_b": st.column_config.NumberColumn("Mcap (€B)", format="%.1f"),
    "pe_forward": st.column_config.NumberColumn("Fwd P/E", format="%.1f"),
    "roe": st.column_config.NumberColumn("ROE %", format="%.1f"),
    "debt_to_equity": st.column_config.NumberColumn("D/E %", format="%.0f"),
    "dividend_yield": st.column_config.NumberColumn("Div %", format="%.2f"),
    "price_vs_sma200": st.column_config.CheckboxColumn("P>SMA200"),
    "degiro_venue": st.column_config.TextColumn("DEGIRO venue"),
    "tradingview_url": st.column_config.LinkColumn("Chart", display_text="TradingView"),
    "degiro_note": st.column_config.TextColumn("DEGIRO note", width="large"),
}

st.dataframe(
    view[list(display_cols)],
    column_config=display_cols,
    hide_index=True,
    use_container_width=True,
    height=650,
)

st.download_button(
    "Download filtered as CSV",
    result.to_csv(index=False).encode("utf-8"),
    file_name="screener_filtered.csv",
    mime="text/csv",
)

with st.expander("Notes & limitations"):
    st.markdown(
        "- **No IV / Greeks** (free-data limitation) — judge IV in TradingView "
        "via the per-row link.\n"
        "- \"Offers liquid options\" is inferred from index membership; verify "
        "the actual chain in DEGIRO before trading.\n"
        "- Index rows (^AEX, ^FCHI, ^GDAXI, ^STOXX50E) are **cash-settled, "
        "European-style** — spreads only, the wheel does not apply.\n"
        "- yfinance fields can be stale or missing for some EU names; missing "
        "values never fail a filter unless you enable the exclude toggle.\n"
        "- `debt/equity` uses Yahoo's percent convention (150 = 1.5x equity)."
    )
