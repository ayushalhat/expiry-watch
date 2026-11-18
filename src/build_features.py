"""
ExpiryWatch — Step 1: Build the daily feature table and expiry feature table.

Outputs
-------
outputs/daily_features.parquet   : 1,789 rows × features (one row per regular trading day)
outputs/expiry_features.parquet  : 380 rows × features (one row per expiry, with EVR,
                                   expiry type, QC flags, control dates)

Usage
-----
    python src/build_features.py

Checks printed at the end:
  - daily_features row count must be 1,789
  - expiry_features row count must be 380
"""

import sys
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 0. Paths
# ---------------------------------------------------------------------------
CSV_PATH   = "data/NIFTY_2h_OHLC_data.csv"
XLSX_PATH  = "data/ExpiryWatch_NIFTY_WP1_WP2.xlsx"
OUT_DAILY  = "outputs/daily_features.parquet"
OUT_EXPIRY = "outputs/expiry_features.parquet"

# ---------------------------------------------------------------------------
# 1. Load the raw 2-hour bar CSV (Section 10.1 loader, verbatim)
# ---------------------------------------------------------------------------
print("Loading CSV …")
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", parse_dates=["Date"])
df["d"] = df["Date"].dt.date
df["t"] = df["Date"].dt.strftime("%H:%M")

STD = ["09:15", "11:15", "13:15", "15:15"]
ok  = df.groupby("d")["t"].apply(lambda s: list(s) == STD)
days = ok[ok].index                          # 1,789 regular trading days

d  = df[df.d.isin(days)].copy()
d["k"] = d.groupby("d").cumcount() + 1      # bar index 1..4

w = d.pivot(index="d", columns="k", values=["Open", "High", "Low", "Close"])
C, O, H, L = w["Close"], w["Open"], w["High"], w["Low"]

# Log returns: r1 = bar-1 open→close; r2..r4 = bar-to-bar
r = pd.concat(
    [np.log(C[1] / O[1]),
     np.log(C[2] / C[1]),
     np.log(C[3] / C[2]),
     np.log(C[4] / C[3])],
    axis=1
)
r.columns = [1, 2, 3, 4]

RV   = np.sqrt((r**2).sum(axis=1))
PATH = r.abs().sum(axis=1)
LBS  = r[4].abs() / PATH                    # last-bar share of path

# ---------------------------------------------------------------------------
# 2. Load the workbook's WP1 Daily Bars sheet
# ---------------------------------------------------------------------------
print("Loading WP1 Daily Bars …")
b = pd.read_excel(XLSX_PATH, sheet_name="WP1 Daily Bars")
b["Date"] = pd.to_datetime(b["Date"]).dt.date
b = b.set_index("Date")

# Defensive check: workbook must cover all 1,789 days
wb_days = set(b.index)
csv_days = set(days)
missing_in_wb = csv_days - wb_days
if missing_in_wb:
    print(f"  WARNING: {len(missing_in_wb)} CSV regular days not in workbook index — "
          f"first few: {sorted(missing_in_wb)[:5]}")

# ---------------------------------------------------------------------------
# 3. Build daily_features (index = date, one row per regular trading day)
# ---------------------------------------------------------------------------
print("Building daily_features …")
X = pd.DataFrame(index=C.index)

# --- Targets (all use bar-4 / final-15-min data) --------------------------
X["y_abs_r4"]  = r[4].abs()                           # |final-15-min log return|
X["y_log_r4"]  = np.log(r[4].abs() + 1e-5)            # log version (2 days have |r4|=0)
X["y_range4"]  = (H[4] - L[4]) / C[3]                 # final-bar range / prior close

# --- Features known by 15:15 (never use bar-4 info in predictive models) --
X["rv20"]       = b["Trailing 20d mean RV"]
X["rv20_pct"]   = b["RV20 percentile vs past 250 days"]
X["r5"]         = b["Prior 5d return"]
X["prev_absret"]= b["|Day return|"].shift(1)           # previous day |return| (shift by 1)
X["rv_first3"]  = np.sqrt((r[[1, 2, 3]] ** 2).sum(axis=1))   # realised vol of bars 1-3
X["trend_to_1515"] = np.log(C[3] / O[1])              # day trend from open to 13:15 close
X["strike50"]   = (C[3] % 50).pipe(lambda m: np.minimum(m, 50 - m)) / 50
X["gap"]        = b["|Overnight gap|"]
X["event"]      = (b["Is listed event"] == "Y").astype(int)
X["is_expiry"]  = (b["Is expiry"] == "Y").astype(int)
X["regime"]     = b["Regime ID"]

# --- Settlement regime label (S2 from 3 Aug 2026 onward) ------------------
cas_start = pd.Timestamp("2026-08-03").date()
X["settle"] = np.where(X.index >= cas_start, "S2", "S1")

# --- Full-day metrics (useful for anomaly models) -------------------------
X["rv"]   = RV
X["path"] = PATH
X["lbs"]  = LBS                                        # last-bar share

# --- Individual bar absolute returns (bars 1-4) ---------------------------
for k in [1, 2, 3, 4]:
    X[f"abs_r{k}"] = r[k].abs()

# --- Raw last-bar metrics (before workbook shift) -------------------------
X["h4"]   = H[4]
X["l4"]   = L[4]
X["c3"]   = C[3]
X["c4"]   = C[4]

print(f"  daily_features shape: {X.shape}")
assert len(X) == 1789, f"Expected 1,789 rows, got {len(X)}"
print(f"  ✓ Row count = {len(X)} (matches 1,789 required)")

X.to_parquet(OUT_DAILY)
print(f"  Saved → {OUT_DAILY}")

# ---------------------------------------------------------------------------
# 4. Load WP1 NIFTY Expiry Events and build expiry_features
# ---------------------------------------------------------------------------
print("\nLoading WP1 NIFTY Expiry Events …")
ev = pd.read_excel(XLSX_PATH, sheet_name="WP1 NIFTY Expiry Events")

# Normalise the expiry date column
ev["Expiry date"] = pd.to_datetime(ev["Expiry date"]).dt.date
ev = ev.set_index("Expiry date")

# --- Select and rename the columns we need ---------------------------------
expiry_cols = {
    "Event ID"                                         : "event_id",
    "Weekday"                                          : "weekday",
    "Expiry type"                                      : "expiry_type",
    "Holiday-shifted?"                                 : "holiday_shifted",
    "Regime ID"                                        : "regime",
    "Settlement regime"                                : "settle",
    "Weekly lot"                                       : "weekly_lot",
    "Last bar comparable (S1)?"                        : "last_bar_comparable",
    "Listed event overlap"                             : "listed_event_overlap",
    "Daily Bars row"                                   : "daily_bars_row",
    # Price levels
    "Prev close"                                       : "prev_close",
    "Open"                                             : "open",
    "High"                                             : "high",
    "Low"                                              : "low",
    "Close 13:15 bar"                                  : "close_1315",
    "Close"                                            : "close",
    "Next-day close"                                   : "next_close",
    # Return / vol metrics
    "Overnight gap"                                    : "overnight_gap",
    "Day return"                                       : "day_return",
    "Intraday return (O→C)"                            : "intraday_return",
    "Range % of prev close"                            : "range_pct",
    "Intraday RV"                                      : "rv",
    "Last-bar return (15:15 bar)"                      : "r4",
    "Last-bar share of path"                           : "lbs",
    "Next-day return"                                  : "next_day_return",
    "Reversal ratio (RR)"                              : "reversal_ratio",
    # State / control features
    "Pre-expiry trailing 20d RV"                       : "rv20",
    "Prior 5d return"                                  : "r5",
    # Controls
    "Control day 1"                                    : "ctrl1",
    "Control day 2"                                    : "ctrl2",
    "Control day 3"                                    : "ctrl3",
    "Control RV 1"                                     : "ctrl_rv1",
    "Control RV 2"                                     : "ctrl_rv2",
    "Control RV 3"                                     : "ctrl_rv3",
    # Anomaly metrics
    "EVR"                                              : "evr",
    "EVR percentile within regime"                     : "evr_pct",
    # Rules
    "STT futures (%)"                                  : "stt_fut",
    "STT options premium (%)"                          : "stt_opt",
    "Closing-price mechanism"                          : "closing_mechanism",
    "Days since previous expiry"                       : "days_since_prev",
    "Expiry-cycle return (prev expiry close → close)"  : "cycle_return",
    "Pre-expiry vol percentile (past 250d)"            : "pre_vol_pct",
    "Volatility regime"                                : "vol_regime",
    "Listed events within ±5 days"                    : "events_pm5d",
    "Control match distance"                           : "ctrl_dist",
    "Data QC flags"                                    : "qc_flags",
}

# Keep only columns that actually exist in the sheet
available = {k: v for k, v in expiry_cols.items() if k in ev.columns}
missing   = [k for k in expiry_cols if k not in ev.columns]
if missing:
    print(f"  WARNING: these expected columns are absent from the Events sheet: {missing}")

E = ev[list(available.keys())].rename(columns=available)

# --- Derived / convenience columns ----------------------------------------
# Has controls: QC flags show "No controls" for the 4 warm-up expiries
E["has_controls"] = ~E["qc_flags"].fillna("").str.contains("No controls", case=False)

# Mean control RV (from the three individual control RVs)
E["ctrl_rv_mean"] = E[["ctrl_rv1", "ctrl_rv2", "ctrl_rv3"]].mean(axis=1)

# Flag for model exclusion (matches Section 0, instruction 7):
# Exclude S2 days (CAS) and the 4 warm-up expiries with no controls
E["model_ok"] = (E["settle"] == "S1") & E["has_controls"]

print(f"  expiry_features shape: {E.shape}")
assert len(E) == 380, f"Expected 380 rows, got {len(E)}"
print(f"  ✓ Row count = {len(E)} (matches 380 required)")

n_s1          = (E["settle"] == "S1").sum()
n_s2          = (E["settle"] == "S2").sum()
n_no_controls = (~E["has_controls"]).sum()
n_model_ok    = E["model_ok"].sum()

print(f"\n  Settlement breakdown:")
print(f"    S1 (comparable last bar): {n_s1}")
print(f"    S2 (CAS / auction print): {n_s2}")
print(f"  No-controls (warm-up):     {n_no_controls}")
print(f"  model_ok (S1 + controls):  {n_model_ok}  ← use this mask in every model")

E.to_parquet(OUT_EXPIRY)
print(f"\n  Saved → {OUT_EXPIRY}")

# ---------------------------------------------------------------------------
# 5. Final summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("Step 1 complete.")
print(f"  daily_features : {len(X):,} rows × {X.shape[1]} cols → {OUT_DAILY}")
print(f"  expiry_features: {len(E):,} rows × {E.shape[1]} cols → {OUT_EXPIRY}")
print("=" * 60)

# Quick sanity: every expiry date should also appear in daily_features
expiry_dates = set(E.index)
daily_dates  = set(X.index)
orphan = expiry_dates - daily_dates
if orphan:
    print(f"\n  WARNING: {len(orphan)} expiry dates not found in daily_features index:")
    for d_ in sorted(orphan):
        print(f"    {d_}")
else:
    print("\n  ✓ All 380 expiry dates are present in the daily_features index.")
