"""Filter presets. Each preset is a partial override of DEFAULTS; applying a
preset first resets every filter key to its default, then applies overrides.

Convention: None = filter off. Percentages are whole numbers (roe=10 -> 10%).
debt_to_equity follows Yahoo's convention (percent: 150 = 1.5x equity).
Money filters are in EUR millions/billions (FX-normalized columns).
"""

CUSTOM = "custom"

INSTRUMENT_ALL = "Stocks + indices"
INSTRUMENT_STOCKS = "Stocks only"
INSTRUMENT_INDICES = "Indices only"

# Special marker: resolved at apply-time to the 90th percentile of
# dollar_volume_eur in the loaded snapshot (in EUR millions).
P90_DOLLAR_VOLUME = "__p90_dollar_volume__"

DOLLAR_VOLUME_STEPS_M = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

DEFAULTS = {
    # liquidity
    "f_dv_min_m": 10,          # spec: default high-ish; "Show everything" sets 0
    "f_mcap_min_b": None,
    "f_avgvol_min_m": None,
    # valuation (max unless noted)
    "f_pe_max": None,
    "f_fpe_max": None,
    "f_ptb_max": None,
    "f_evebitda_max": None,
    "f_peg_max": None,
    "f_divyield_min": None,
    # quality
    "f_roe_min": None,
    "f_roa_min": None,
    "f_netmargin_min": None,
    "f_opmargin_min": None,
    "f_de_max": None,
    "f_currratio_min": None,
    # growth
    "f_egrowth_min": None,
    "f_rgrowth_min": None,
    # technical
    "f_above_sma20": False,
    "f_above_sma50": False,
    "f_above_sma200": False,
    "f_52high_min": None,
    "f_52high_max": None,
    "f_52low_min": None,
    "f_52low_max": None,
    "f_beta_min": None,
    "f_beta_max": None,
    # categorical
    "f_sectors": [],
    "f_countries": [],
    "f_indices": [],
    "f_venues": [],
    "f_instruments": INSTRUMENT_ALL,
    # NULL handling
    "f_excl_missing": False,
}

PRESETS = {
    "Wheel candidates": {
        "f_dv_min_m": 20,
        "f_mcap_min_b": 10.0,
        "f_roe_min": 0.0,
        "f_de_max": 200.0,          # Yahoo convention: <= 2x equity
        "f_currratio_min": 1.0,
        "f_52high_min": -30.0,      # avoid falling knives
        "f_instruments": INSTRUMENT_STOCKS,
    },
    "Liquid spread underlyings": {
        "f_dv_min_m": P90_DOLLAR_VOLUME,   # top dollar-volume decile
        "f_beta_min": 0.8,
        "f_beta_max": 2.0,
        "f_instruments": INSTRUMENT_ALL,
    },
    "Value + quality": {
        "f_dv_min_m": 5,
        "f_pe_max": 15.0,
        "f_ptb_max": 2.0,
        "f_roe_min": 10.0,
        "f_netmargin_min": 5.0,
        "f_opmargin_min": 5.0,
        "f_instruments": INSTRUMENT_STOCKS,
    },
    "Show everything": {
        "f_dv_min_m": 0,
    },
}
