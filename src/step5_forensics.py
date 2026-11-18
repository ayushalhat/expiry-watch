"""
Step 5a - Event Forensics + draft evidence packs.  ExpiryWatch India (NIFTY, spot-only, Tier A).

For each expiry worth a human look it makes:
  * a chart: the expiry's 4-bar path vs its 3 matched control days (and their mean), and bar-by-bar |return|
  * an evidence card (markdown): metrics vs controls, the MIRS-lite components, tier, ML flags,
    the strongest LEGITIMATE explanations to test first (devil's-advocate rule), what data is missing,
    and an empty WP7 block for dated, cited news.

Selection: all Orange (walk-forward and retrospective), top-N by MIRS (walk-forward), the settlement-timing
extremes, and the negative controls. Edit SELECT_* below to change it.

Run from the project root:   python src/step5_forensics.py
Needs: data/NIFTY_2h_OHLC_data.csv, the workbook, outputs/expiry_features.parquet, outputs/step4_mirs_*.csv
Outputs: outputs/forensics/<date>.png, evidence_packs.md, forensics_summary.csv

INTERPRETATION RULE: everything here ranks SURVEILLANCE PRIORITY. Nothing here is evidence of manipulation.
"""
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ CONFIG
RAW_CANDIDATES = ["data/NIFTY_2h_OHLC_data.csv", "data/NIFTY_2h_OHLC_data__1_.csv"]
WP_XLSX = "data/ExpiryWatch_NIFTY_WP1_WP2.xlsx"
EXPIRY_PARQ = "outputs/expiry_features.parquet"
MIRS_WF = "outputs/step4_mirs_walkforward.csv"
MIRS_RETRO = "outputs/step4_mirs_RETROSPECTIVE.csv"
OUTDIR = "outputs/forensics"
SELECT_TOP_MIRS = 8              # top-N by walk-forward MIRS
SELECT_TOP_T = 4                 # top-N by settlement-timing component T (walk-forward)
NEG_CONTROLS = ["2020-03-12", "2023-01-25", "2024-02-01"]
BANNER = "Surveillance priority only - NOT evidence of manipulation or any legal violation."
os.makedirs(OUTDIR, exist_ok=True)

# ------------------------------------------------------------------ 1. bars -> regular days
raw_path = next((p for p in RAW_CANDIDATES if os.path.exists(p)), None)
assert raw_path, f"raw price file not found; tried {RAW_CANDIDATES}"
df = pd.read_csv(raw_path, encoding="utf-8-sig", parse_dates=["Date"])
df["d"] = pd.to_datetime(df["Date"].dt.date)
df["t"] = df["Date"].dt.strftime("%H:%M")
STD = ["09:15", "11:15", "13:15", "15:15"]
ok = df.groupby("d")["t"].apply(lambda s: list(s) == STD)
dd = df[df.d.isin(ok[ok].index)].copy()
dd["k"] = dd.groupby("d").cumcount() + 1
W = dd.pivot(index="d", columns="k", values=["Open", "High", "Low", "Close"])
O, H, L, C = W["Open"], W["High"], W["Low"], W["Close"]
R = pd.concat([np.log(C[1] / O[1]), np.log(C[2] / C[1]), np.log(C[3] / C[2]), np.log(C[4] / C[3])], axis=1)
R.columns = [1, 2, 3, 4]
days = pd.DataFrame(index=C.index)
days["prev_close"] = C[4].shift(1)
days["day_ret"] = C[4] / days["prev_close"] - 1
days["next_ret"] = C[4].shift(-1) / C[4] - 1
days["rv"] = np.sqrt((R ** 2).sum(axis=1))
days["abs_r4"] = R[4].abs()
days["lbs"] = R[4].abs() / R.abs().sum(axis=1)
days["rng4"] = (H[4] - L[4]) / C[3]
print(f"regular trading days: {len(days)}")

# ------------------------------------------------------------------ 2. expiry metadata + controls
ev = pd.read_excel(WP_XLSX, sheet_name="WP1 NIFTY Expiry Events")
ev["date"] = pd.to_datetime(ev["Expiry date"])
ev = ev.set_index("date")
ctrl = ev[["Control day 1", "Control day 2", "Control day 3"]].apply(pd.to_datetime, errors="coerce")

pq = pd.read_parquet(EXPIRY_PARQ)
pq.index = pd.to_datetime(pq.index)

wf = pd.read_csv(MIRS_WF, index_col=0, parse_dates=True)
rt = pd.read_csv(MIRS_RETRO, index_col=0, parse_dates=True)

# ------------------------------------------------------------------ 3. selection
sel = {}
def add(dates, why):
    for d_ in dates:
        d_ = pd.Timestamp(d_)
        sel.setdefault(d_, []).append(why)

add(wf.index[wf.tier == "Orange"], "Orange (walk-forward)")
add(rt.index[rt.tier == "Orange"], "Orange (retrospective)")
add(wf.nlargest(SELECT_TOP_MIRS, "MIRS").index, f"top-{SELECT_TOP_MIRS} MIRS (walk-forward)")
add(wf.nlargest(SELECT_TOP_T, "T").index, f"top-{SELECT_TOP_T} settlement-timing T (walk-forward)")
add(NEG_CONTROLS, "negative control (listed event)")
sel_dates = sorted(sel)
print(f"selected expiries: {len(sel_dates)}")

# ------------------------------------------------------------------ 4. helpers
XLAB = ["Open", "09:15-11:15", "11:15-13:15", "13:15-15:15", "15:15-15:30"]
BARLAB = ["09:15", "11:15", "13:15", "15:15 (final 15 min)"]


def path_bps(d_):
    r = R.loc[d_].values
    return np.concatenate([[0.0], np.cumsum(r)]) * 1e4


def hints(row, pqrow, is_event_day):
    out = []
    if row["expiry_type"] == "Monthly":
        out.append("Monthly expiry: larger open interest is rolled, hedged or unwound into the close (WP2 found the final-bar effect "
                   "concentrated in monthlies). Needs OI/rollover data to test.")
    if is_event_day or pqrow["events_pm5d"] >= 1:
        out.append("A listed information event falls on or within 5 days of this expiry: news / price discovery is a leading explanation.")
    elif row["news_expl"] > 0:
        out.append("Extreme overnight gap: information probably arrived before the open.")
    if row["A"] >= 0.9 and row["T"] < 0.7:
        out.append("The whole-day volatility is unusual but the settlement-window evidence is weak: the move happened earlier in the day.")
    if row["R"] >= 0.9:
        out.append("Large next-day reversal: can come from hedging, inventory or liquidity effects; it must never be used alone (proposal 9.4).")
    if row["T"] >= 0.9 and row["A"] < 0.7:
        out.append("Quiet day overall but an active close: look at roll/unwind, delta hedging and VWAP-targeting execution first.")
    return out


# ------------------------------------------------------------------ 5. charts + cards
cards, rows = [], []
for d_ in sel_dates:
    src = wf if d_ in wf.index else (rt if d_ in rt.index else None)
    if src is None or d_ not in days.index or d_ not in ctrl.index:
        print("skip (missing data):", d_.date())
        continue
    row = src.loc[d_]
    pqrow = pq.loc[d_]
    cdates = [c for c in ctrl.loc[d_].tolist() if pd.notna(c) and c in days.index]
    is_event_day = isinstance(pqrow.get("listed_event_overlap", None), str) and pqrow["listed_event_overlap"] not in ("", "nan", "None")
    tier = row["tier"]

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for c in cdates:
        ax[0].plot(XLAB, path_bps(c), color="grey", alpha=0.5, lw=1)
    if cdates:
        ax[0].plot(XLAB, np.mean([path_bps(c) for c in cdates], axis=0), color="black", ls="--", lw=1.5, label="mean of 3 controls")
    ax[0].plot(XLAB, path_bps(d_), color="crimson", lw=2.5, marker="o", label="expiry")
    ax[0].axhline(0, color="k", lw=0.5)
    ax[0].set_ylabel("cumulative log return from open (bps)")
    ax[0].set_title("Intraday path (4 two-hour bars)")
    ax[0].tick_params(axis="x", labelrotation=25)
    ax[0].legend(fontsize=8)
    exp_abs = np.abs(R.loc[d_].values) * 1e4
    ctl_abs = np.mean([np.abs(R.loc[c].values) * 1e4 for c in cdates], axis=0) if cdates else np.zeros(4)
    x = np.arange(4)
    ax[1].bar(x - 0.2, exp_abs, 0.4, color="crimson", label="expiry")
    ax[1].bar(x + 0.2, ctl_abs, 0.4, color="grey", label="mean of controls")
    ax[1].set_xticks(x)
    ax[1].set_xticklabels(BARLAB, fontsize=8, rotation=15)
    ax[1].set_ylabel("absolute bar return (bps)")
    ax[1].set_title("Bar-by-bar absolute return: placebo bars 1-3 vs final bar")
    ax[1].legend(fontsize=8)
    fig.suptitle(f"{d_.date()}  {row['expiry_type']}  {row['regime']}   tier={tier}  MIRS={row['MIRS']:.2f}", fontsize=11)
    fig.text(0.5, 0.005, BANNER, ha="center", fontsize=7, color="dimgrey")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    png = f"{OUTDIR}/{d_.date()}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    cm = lambda col: days.loc[cdates, col].mean() if cdates else np.nan
    m = days.loc[d_]
    metrics = [
        ("Day return", f"{m.day_ret * 100:+.2f}%", "-"),
        ("Intraday realised vol (EVR vs controls)", f"{m.rv * 100:.2f}%  (EVR {pqrow['evr']:.2f})", f"{cm('rv') * 100:.2f}%"),
        ("Final 15 min absolute return", f"{m.abs_r4 * 1e4:.1f} bps", f"{cm('abs_r4') * 1e4:.1f} bps"),
        ("Final 15 min range", f"{m.rng4 * 1e4:.1f} bps", f"{cm('rng4') * 1e4:.1f} bps"),
        ("Last-bar share of price path", f"{m.lbs * 100:.1f}%", f"{cm('lbs') * 100:.1f}%"),
        ("Overnight gap (signed)", f"{pqrow['overnight_gap'] * 100:+.2f}%", "-"),
        ("Next-day return", f"{m.next_ret * 100:+.2f}%" if pd.notna(m.next_ret) else "n/a", "-"),
        ("Listed events within +-5 days", f"{int(pqrow['events_pm5d'])}", "-"),
    ]
    mt = "| Measure | Expiry | Mean of 3 controls |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in metrics)
    comp = (f"A (whole-day anomaly) {row['A']:.2f} | T (settlement timing) {row['T']:.2f} | R (reversal) {row['R']:.2f} | "
            f"Recurrence {row['Rec']:.2f} | signals {int(row['n_signals'])} | U {row['U']:.2f} | news explanation {row['news_expl']:.2f} "
            f"| **MIRS {row['MIRS']:.2f}** | rank {int(row['rank_MIRS'])} of {len(src)}")
    mlline = (f"ML consensus (median of IF/LOF/SVM percentiles) {row['ml_consensus']:.2f}; at least 2 of 3 models above 0.90: "
              f"{'yes' if row.get('ml_2of3_above_90', 0) == 1 else 'no'}  (secondary flag; ML is not inside MIRS)"
              if pd.notna(row.get("ml_consensus", np.nan)) else "ML consensus: not available for this date")
    hs = hints(row, pqrow, is_event_day)
    hs_txt = "\n".join(f"- {h}" for h in hs) if hs else "- No rule-based innocent explanation triggered; test the generic ones below."
    card = f"""## {d_.date()} - {row['expiry_type']} expiry, regime {row['regime']} - **{tier}**
*Selected because:* {', '.join(sel[d_])}   |   *Run:* {'walk-forward (out-of-sample)' if src is wf else 'retrospective only'}

![path]({d_.date()}.png)

{mt}

**Score components (past-only percentiles):** {comp}

{mlline}

**Strongest legitimate explanations to test FIRST (devil's-advocate rule; auto-generated hypotheses, not findings):**
{hs_txt}
- Delta/gamma hedging, roll/unwind, arbitrage convergence, index rebalancing and liquidity cannot be tested with spot-only data
  (need OI by strike, futures, constituents, volume/spread/depth).

**WP7 news / information evidence (to be filled with dated, cited sources before any conclusion):**
- [ ] RBI / macro release on or before this date:  source ______  time ______
- [ ] Corporate or index announcement (heavy NIFTY constituents):  source ______  time ______
- [ ] Global market move overnight / intraday:  source ______  time ______
- Conclusion (one sentence, in surveillance language): ______

**Data needed to go further:** F&O bhavcopy (OI, strike distribution, futures basis), constituent prices and weights, intraday volume.
> {BANNER}

---
"""
    cards.append(card)
    rows.append(dict(date=d_.date(), expiry_type=row["expiry_type"], regime=row["regime"], tier=tier, MIRS=row["MIRS"],
                     rank_MIRS=row["rank_MIRS"], A=row["A"], T=row["T"], R=row["R"], Rec=row["Rec"], news_expl=row["news_expl"],
                     abs_r4_bps=m.abs_r4 * 1e4, abs_r4_ctrl_bps=cm("abs_r4") * 1e4, lbs=m.lbs, lbs_ctrl=cm("lbs"),
                     ml_consensus=row.get("ml_consensus", np.nan), selected_because="; ".join(sel[d_])))

hdr = f"""# ExpiryWatch India - draft evidence packs (spot-only, Tier A)
> **{BANNER}** Tiers are surveillance-priority labels from MIRS-lite; Red is not assignable without cross-market evidence.
> Every card lists legitimate explanations first. These drafts become evidence packs only after WP7 news evidence is filled in.

"""
open(f"{OUTDIR}/evidence_packs.md", "w", encoding="utf-8").write(hdr + "\n".join(cards))
pd.DataFrame(rows).to_csv(f"{OUTDIR}/forensics_summary.csv", index=False)
print(f"wrote {len(cards)} cards + charts to {OUTDIR}/ (evidence_packs.md, forensics_summary.csv)")
