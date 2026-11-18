"""
WP8 / Step 7 — ExpiryWatch India Dashboard (Streamlit)
=======================================================
NIFTY-only, Spot-Price-Only, Tier-A Surveillance Framework.

Run from project root:
    streamlit run src/step7_dashboard.py

Language rule: scores rank surveillance priority only and do not establish intent.
"""
import json, pathlib, textwrap
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap

# ─────────────────────────── PAGE CONFIG ────────────────────────────────────
st.set_page_config(
    page_title="ExpiryWatch India",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BANNER = (
    "⚠️ **INTERPRETATION RULE:** MIRS ranks *surveillance priority* only. "
    "It is a data-limited upper bound and does not establish intent or wrongdoing."
)

# ─────────────────────────── PATHS ──────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
OUT  = ROOT / "outputs"
FORENSIC_DIR = OUT / "forensics"

# ─────────────────────────── LOAD DATA ──────────────────────────────────────
def _signature(paths):
    return tuple((str(p), p.stat().st_mtime_ns if p.exists() else -1) for p in paths)


@st.cache_data(show_spinner="Loading project data…")
def load_data(signature):
    del signature  # file mtimes invalidate cached data when pipeline outputs change
    required = [
        OUT / "step4_mirs_walkforward.csv", OUT / "step4_mirs_RETROSPECTIVE.csv",
        OUT / "wp7_nes_scores.csv", FORENSIC_DIR / "forensics_summary.csv",
        OUT / "expiry_features.parquet", OUT / "importance.csv",
        OUT / "expiry_residuals_walkforward.csv", OUT / "step3v2_scores_A.csv",
        OUT / "wp7_news_kb.json",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Required project outputs are missing: " + ", ".join(str(p.relative_to(ROOT)) for p in missing))
    mirs_wf = pd.read_csv(OUT / "step4_mirs_walkforward.csv", index_col=0, parse_dates=True)
    mirs_retro = pd.read_csv(OUT / "step4_mirs_RETROSPECTIVE.csv", index_col=0, parse_dates=True)
    nes = pd.read_csv(OUT / "wp7_nes_scores.csv", parse_dates=["date"])
    forensics = pd.read_csv(FORENSIC_DIR / "forensics_summary.csv", parse_dates=["date"])
    features = pd.read_parquet(OUT / "expiry_features.parquet")
    if "Expiry date" in features.columns:
        features = features.set_index(pd.to_datetime(features.pop("Expiry date")))
    features.index = pd.to_datetime(features.index).normalize()
    optional = lambda name: pd.read_csv(OUT / name, index_col=0, parse_dates=True) if (OUT / name).exists() else pd.DataFrame()
    shap_df = optional("expiry_shap.csv")
    importance = pd.read_csv(OUT / "importance.csv")
    residuals = optional("expiry_residuals_walkforward.csv")
    scores_a = optional("step3v2_scores_A.csv")
    with open(OUT / "wp7_news_kb.json", encoding="utf-8") as f:
        kb = json.load(f)
    date_fields = {"date", "tier_base", "MIRS_base", "U_pre_news", "NES_exploratory", "MIRS_WP7_sensitivity", "status", "selected_because"}
    missing_cols = date_fields - set(nes.columns)
    if missing_cols:
        raise ValueError("WP7 score file has the legacy schema. Re-run src/step6_wp7_news.py; missing: " + ", ".join(sorted(missing_cols)))
    if forensics["date"].duplicated().any() or nes["date"].duplicated().any():
        raise ValueError("Forensics and WP7 score files must contain unique dates")
    forensics = forensics.merge(nes, on="date", how="left", validate="one_to_one")
    return mirs_wf, mirs_retro, nes, forensics, features, shap_df, importance, residuals, scores_a, kb


try:
    (mirs_wf, mirs_retro, nes, forensics, features, shap_df, importance,
     residuals, scores_a, kb) = load_data(_signature([
        OUT / "step4_mirs_walkforward.csv", OUT / "step4_mirs_RETROSPECTIVE.csv",
        OUT / "wp7_nes_scores.csv", FORENSIC_DIR / "forensics_summary.csv",
        OUT / "expiry_features.parquet", OUT / "importance.csv",
        OUT / "expiry_residuals_walkforward.csv", OUT / "step3v2_scores_A.csv",
        OUT / "wp7_news_kb.json",
    ]))
except (FileNotFoundError, ValueError, KeyError, pd.errors.ParserError) as exc:
    st.error(f"Dashboard data check failed: {exc}")
    st.stop()

# ─────────────────────────── COLOUR HELPERS ─────────────────────────────────
TIER_COLOR = {"Green": "#27ae60", "Amber": "#e67e22", "Orange": "#e74c3c", "?": "#7f8c8d"}

def tier_badge(tier):
    color = TIER_COLOR.get(tier, "#7f8c8d")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.85em">{tier}</span>'

def mirs_color(val):
    if pd.isna(val): return ""
    if val >= 0.80: return "background-color:#fde8e8"
    if val >= 0.70: return "background-color:#fef3cd"
    return "background-color:#d4edda"

# ─────────────────────────── SIDEBAR ────────────────────────────────────────
st.sidebar.title("ExpiryWatch India")
st.sidebar.caption("NIFTY · Spot Only · Tier-A Surveillance Framework")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", [
    "📊 MIRS Dashboard",
    "🔬 Forensic Deep-Dive",
    "🧠 ML / Step 2 Residual",
    "📰 WP7 News Attribution",
    "📋 Methodology",
])

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Pipeline:** Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → WP7  \n"
    f"**Expiries:** {len(mirs_wf)} walk-forward · {len(mirs_retro)} retrospective  \n"
    f"**Forensic dates:** {len(forensics)}"
)
st.sidebar.warning(BANNER, icon="⚠️")

# ════════════════════════════════════════════════════════════════════════════
# PAGE 1 — MIRS DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
if page == "📊 MIRS Dashboard":
    st.title("📊 MIRS Dashboard — All Expiries")
    st.info(BANNER)

    # ── Controls ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        source = st.selectbox("Dataset", ["Walk-Forward (2022–2026)", "Retrospective (all years)"])
    with col2:
        tier_filter = st.multiselect("Filter by Tier", ["Green", "Amber", "Orange"], default=["Green", "Amber", "Orange"])
    with col3:
        exp_type = st.multiselect("Expiry type", ["Weekly", "Monthly"], default=["Weekly", "Monthly"])

    df = mirs_wf.copy() if source.startswith("Walk") else mirs_retro.copy()

    # Apply filters
    if tier_filter:
        df = df[df["tier"].isin(tier_filter)]
    if exp_type:
        df = df[df["expiry_type"].isin(exp_type)]

    df = df.sort_values("MIRS", ascending=False)

    # ── KPI strip ─────────────────────────────────────────────────────────
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total expiries", len(df))
    kpi2.metric("🟠 Orange", (df["tier"] == "Orange").sum())
    kpi3.metric("🟡 Amber", (df["tier"] == "Amber").sum())
    kpi4.metric("🟢 Green", (df["tier"] == "Green").sum())

    st.markdown("---")

    # ── Timeline chart ────────────────────────────────────────────────────
    st.subheader("MIRS over time")
    fig, ax = plt.subplots(figsize=(12, 3.5))
    colors = [TIER_COLOR.get(t, "#7f8c8d") for t in df["tier"]]
    ax.scatter(df.index, df["MIRS"], c=colors, s=22, zorder=3, alpha=0.85)
    ax.set_ylabel("MIRS"); ax.set_xlabel("")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax.legend(handles=[plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=TIER_COLOR[k], label=k, markersize=7) for k in ["Green", "Amber", "Orange"]],
              fontsize=8, loc="upper left", frameon=False)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, width="stretch")
    plt.close(fig)

    # ── Top-20 table ──────────────────────────────────────────────────────
    st.subheader("Top-20 by MIRS")
    top_fields = [c for c in ["expiry_type", "tier", "MIRS", "U", "A", "T", "R", "Rec"] if c in df.columns]
    top20 = df.head(20)[top_fields].copy()
    top20.index = top20.index.strftime("%Y-%m-%d")
    top20 = top20.rename(columns={
        "expiry_type": "Type", "tier": "Tier", "MIRS": "MIRS",
        "U": "U (base composite)", "A": "A (whole-day)",
        "T": "T (settlement timing)", "R": "R (reversal)", "Rec": "Rec (recurrence)",
    })
    st.dataframe(
        top20.style
            .format({c: "{:.3f}" for c in top20.columns if c not in ["Type", "Tier"]})
            .map(mirs_color, subset=["MIRS"]),
        width="stretch"
    )

    # ── Full table with search ────────────────────────────────────────────
    with st.expander("📋 Full table (all filtered expiries)"):
        show_cols = ["expiry_type", "tier", "MIRS", "U", "T", "EVR"]
        show_cols = [c for c in show_cols if c in df.columns]
        full = df[show_cols].copy()
        full.index = full.index.strftime("%Y-%m-%d")
        st.dataframe(full.style.format({c: "{:.3f}" for c in ["MIRS","U","T","EVR"] if c in full.columns}),
                     width="stretch", height=400)

    # ── Distribution ─────────────────────────────────────────────────────
    st.subheader("MIRS distribution by tier")
    fig2, axes = plt.subplots(1, 3, figsize=(11, 3), sharey=False)
    for ax, tier in zip(axes, ["Green", "Amber", "Orange"]):
        vals = df[df["tier"] == tier]["MIRS"]
        if len(vals):
            ax.hist(vals, bins=20, color=TIER_COLOR[tier], alpha=0.8, edgecolor="white")
        ax.set_title(f"{tier} (n={len(vals)})", fontsize=10)
        ax.set_xlabel("MIRS")
    fig2.tight_layout()
    st.pyplot(fig2, width="stretch")
    plt.close(fig2)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 2 — FORENSIC DEEP-DIVE
# ════════════════════════════════════════════════════════════════════════════
elif page == "🔬 Forensic Deep-Dive":
    st.title("🔬 Forensic Deep-Dive — 17 Flagged Expiries")
    st.info(BANNER)

    # Selector
    dates_str = forensics["date"].dt.strftime("%Y-%m-%d").tolist()
    tiers_str = forensics["tier"].tolist() if "tier" in forensics.columns else ["?"] * len(dates_str)
    options = [f"{d}  [{t}]" for d, t in zip(dates_str, tiers_str)]
    sel = st.selectbox("Select expiry date", options)
    sel_date = sel.split("  ")[0]
    row = forensics[forensics["date"].dt.strftime("%Y-%m-%d") == sel_date].iloc[0]

    # Header
    tier = row.get("tier", "?")
    mirs_val = row.get("MIRS", row.get("mirs", np.nan))
    nes_val = row.get("NES_exploratory", np.nan)
    st.markdown(f"## {sel_date} &nbsp; {tier_badge(tier)}", unsafe_allow_html=True)

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("MIRS", f"{mirs_val:.3f}" if not pd.isna(mirs_val) else "—")
    k2.metric("Exploratory NES",  f"{nes_val:.2f}"  if not pd.isna(nes_val)  else "PENDING")
    sensitivity = row.get("MIRS_WP7_sensitivity", np.nan)
    k3.metric("WP7 sensitivity", f"{sensitivity:.3f}" if pd.notna(sensitivity) else "PENDING")
    k4.metric("Type", row.get("expiry_type", "?"))
    k5.metric("Evidence review", row.get("status", "PENDING"))
    st.caption(f"**Selected because:** {row.get('selected_because','?')}")

    st.markdown("---")
    left, right = st.columns([1.1, 1])

    # Price chart
    with left:
        st.subheader("Intraday Price Chart")
        png_path = FORENSIC_DIR / f"{sel_date}.png"
        if png_path.exists():
            st.image(str(png_path), width="stretch")
        else:
            st.warning("Chart image not found.")

    # News card
    with right:
        st.subheader("WP7 News Attribution")
        kb_entry = kb.get("dates", {}).get(sel_date, {})
        st.caption("Public information near the date is context only; temporal overlap does not establish a cause.")
        evidence_items = kb_entry.get("items", []) if isinstance(kb_entry, dict) else []
        if evidence_items:
            for item in evidence_items:
                with st.expander(f"{item.get('category', 'Evidence')} · {item.get('event_date', 'date pending')}", expanded=True):
                    st.write(item.get("summary", "No summary provided."))
                    st.caption(f"Public by: {item.get('available_at', 'timestamp pending')} · Review: {item.get('review_status', 'pending')}")
                    for source in item.get("sources", []):
                        if isinstance(source, dict) and source.get("url"):
                            st.markdown(f"- [{source.get('publisher', 'Source')}: {source.get('title', 'Open source')}]({source['url']}) · {source.get('published_at', 'publication time pending')}")
        else:
            st.warning("No source-complete, human-reviewed evidence is available for this date. This is pending evidence, not a finding that no relevant news existed.")
        st.markdown(f"**Surveillance note:** {row.get('analyst_note', '')}")
        if row.get("audit_notes"):
            with st.expander("Evidence validation details"):
                st.write(row["audit_notes"])

    # Feature snapshot
    st.markdown("---")
    st.subheader("Feature Snapshot vs Controls")
    dt = pd.Timestamp(sel_date)
    if dt in features.index:
        feat_row = features.loc[dt]
        display_feats = {
            "EVR (expiry vs range ratio)": "evr",
            "Last-bar share": "lbs",
            "Next-day reversal ratio": "reversal_ratio",
            "Overnight gap": "overnight_gap",
            "Events ±5 days": "events_pm5d",
            "r4 diff vs control": "r4_diff",
        }
        vals, keys = [], []
        for label, col in display_feats.items():
            if col in feat_row.index and not pd.isna(feat_row[col]):
                vals.append(feat_row[col]); keys.append(label)
        if vals:
            fig3, ax3 = plt.subplots(figsize=(7, 3))
            colors3 = ["#e74c3c" if v > 0 else "#3498db" for v in vals]
            ax3.barh(keys, vals, color=colors3, alpha=0.8)
            ax3.axvline(0, color="black", lw=0.8)
            ax3.set_xlabel("Value"); ax3.grid(axis="x", alpha=0.3)
            fig3.tight_layout(); st.pyplot(fig3, width="stretch"); plt.close(fig3)
    else:
        st.caption("Feature data not available for this date.")

    # MIRS component breakdown
    st.markdown("---")
    st.subheader("MIRS Components")
    comp_cols = ["T", "U", "EVR", "MIRS"]
    src_df = mirs_wf if dt in mirs_wf.index else (mirs_retro if dt in mirs_retro.index else None)
    if src_df is not None and dt in src_df.index:
        comp_row = src_df.loc[dt]
        fig4, ax4 = plt.subplots(figsize=(6, 2.5))
        components = ["A", "T", "R", "Rec"]
        vals4 = [float(comp_row.get(c, np.nan)) * w for c, w in zip(components, [0.25, 0.45, 0.10, 0.20])]
        ax4.bar(["A × .25", "T × .45", "R × .10", "Rec × .20"],
                vals4, color=["#3498db", "#176B87", "#9b59b6", "#e67e22"], alpha=0.85)
        ax4.axhline(comp_row.get("MIRS", 0), color="red", ls="--", lw=1.2, label=f"MIRS={comp_row.get('MIRS',0):.3f}")
        ax4.set_ylim(0, 1.05); ax4.legend(fontsize=9); ax4.set_ylabel("Score")
        ax4.grid(axis="y", alpha=0.3); fig4.tight_layout()
        st.pyplot(fig4, width="stretch"); plt.close(fig4)
    else:
        st.caption("MIRS component data not available.")


# ════════════════════════════════════════════════════════════════════════════
# PAGE 3 — ML / STEP 2 RESIDUAL
# ════════════════════════════════════════════════════════════════════════════
elif page == "🧠 ML / Step 2 Residual":
    st.title("🧠 ML & Step 2 Residual Model")
    st.info(BANNER)

    tab1, tab2, tab3 = st.tabs(["Step 2: Residual Model", "Step 3: Unsupervised Models", "MIRS Components"])

    # ── Tab 1: Step 2 ─────────────────────────────────────────────────────
    with tab1:
        st.subheader("Gradient-Boosted Residual (Walk-Forward OOS)")
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**Feature Importance**")
            if len(importance):
                fig_imp, ax_imp = plt.subplots(figsize=(5, 3.5))
                imp = importance.sort_values(importance.columns[1], ascending=True).tail(8)
                ax_imp.barh(imp.iloc[:,0], imp.iloc[:,1], color="#3498db", alpha=0.85)
                ax_imp.set_xlabel("Importance"); ax_imp.grid(axis="x", alpha=0.3)
                fig_imp.tight_layout(); st.pyplot(fig_imp, width="stretch"); plt.close(fig_imp)

        with col_b:
            st.markdown("**Residual over time (walk-forward)**")
            if "residual" in residuals.columns:
                fig_res, ax_res = plt.subplots(figsize=(5, 3.5))
                ax_res.plot(residuals.index, residuals["residual"], lw=0.8, color="#e74c3c", alpha=0.7)
                ax_res.axhline(0, color="black", lw=0.6)
                ax_res.set_ylabel("OOS Residual"); ax_res.grid(alpha=0.3)
                fig_res.tight_layout(); st.pyplot(fig_res, width="stretch"); plt.close(fig_res)
            else:
                st.caption(f"Residuals columns: {residuals.columns.tolist()}")

        st.markdown("---")
        st.markdown("**SHAP values (mean |SHAP| per feature)**")
        if len(shap_df.columns) > 1:
            mean_shap = shap_df.abs().mean().sort_values(ascending=False).head(10)
            fig_shap, ax_shap = plt.subplots(figsize=(8, 3))
            ax_shap.bar(mean_shap.index, mean_shap.values, color="#9b59b6", alpha=0.85)
            ax_shap.set_ylabel("Mean |SHAP|"); ax_shap.set_xticks(range(len(mean_shap.index)), mean_shap.index, rotation=35, ha="right")
            ax_shap.grid(axis="y", alpha=0.3); fig_shap.tight_layout()
            st.pyplot(fig_shap, width="stretch"); plt.close(fig_shap)

    # ── Tab 2: Step 3 ─────────────────────────────────────────────────────
    with tab2:
        st.subheader("Isolation Forest · LOF · One-Class SVM (Walk-Forward, Version A)")
        if set(["IF_pct","LOF_pct","SVM_pct"]).issubset(scores_a.columns):
            fig_ml, axes_ml = plt.subplots(1, 3, figsize=(12, 3.5), sharey=False)
            for ax_ml, col, title, color in zip(
                axes_ml,
                ["IF_pct","LOF_pct","SVM_pct"],
                ["Isolation Forest","LOF","One-Class SVM"],
                ["#e74c3c","#e67e22","#3498db"]
            ):
                ax_ml.hist(scores_a[col].dropna(), bins=25, color=color, alpha=0.8, edgecolor="white")
                ax_ml.axvline(0.90, color="black", ls="--", lw=0.9)
                ax_ml.set_title(title, fontsize=10); ax_ml.set_xlabel("Percentile rank")
            fig_ml.suptitle("Unsupervised model score distributions (WF Version A)", fontsize=10)
            fig_ml.tight_layout(); st.pyplot(fig_ml, width="stretch"); plt.close(fig_ml)

            # Correlation matrix
            st.markdown("**Spearman rank correlation between models**")
            corr = scores_a[["IF_pct","LOF_pct","SVM_pct"]].corr(method="spearman")
            corr.index = corr.columns = ["IF","LOF","SVM"]
            fig_corr, ax_corr = plt.subplots(figsize=(3.5, 3))
            cmap = LinearSegmentedColormap.from_list("", ["#3498db","white","#e74c3c"])
            im = ax_corr.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
            ax_corr.set_xticks(range(3)); ax_corr.set_yticks(range(3))
            ax_corr.set_xticklabels(["IF","LOF","SVM"]); ax_corr.set_yticklabels(["IF","LOF","SVM"])
            for i in range(3):
                for j in range(3):
                    ax_corr.text(j, i, f"{corr.values[i,j]:.2f}", ha="center", va="center", fontsize=10)
            plt.colorbar(im, ax=ax_corr, shrink=0.8)
            fig_corr.tight_layout(); st.pyplot(fig_corr, width="stretch"); plt.close(fig_corr)
        else:
            st.caption(f"Available columns: {scores_a.columns.tolist()}")

    # ── Tab 3: MIRS decomposition ──────────────────────────────────────────
    with tab3:
        st.subheader("MIRS-lite = weighted behaviour components, then Step 4's fixed discount")
        st.markdown("""
| Component | Weight | Description |
|---|---|---|
| **A** | 0.25 | Whole-day anomaly percentile |
| **T** | 0.45 | Settlement-timing percentile |
| **R** | 0.10 | Next-day reversal percentile |
| **Rec** | 0.20 | Recent recurrence percentile |

`U = .25A + .45T + .10R + .20Rec`; `MIRS = U × (1 − .5 × news_expl)`.
Step 4's base MIRS already includes its fixed rule-based discount. WP7's optional sensitivity replaces that rule from U; it does not discount base MIRS a second time and does not change tiers.
        """)
        df_w = mirs_wf[["A", "T", "R", "Rec", "MIRS"]].dropna() if set(["A", "T", "R", "Rec", "MIRS"]).issubset(mirs_wf.columns) else pd.DataFrame()
        if len(df_w):
            fig_comp, ax_comp = plt.subplots(figsize=(10, 3.5))
            ax_comp.stackplot(df_w.index,
                              df_w["A"]*0.25, df_w["T"]*0.45, df_w["R"]*0.10, df_w["Rec"]*0.20,
                              labels=["A×.25", "T×.45", "R×.10", "Rec×.20"],
                              colors=["#3498db", "#176B87", "#9b59b6", "#e67e22"], alpha=0.8)
            ax_comp.plot(df_w.index, df_w["MIRS"], "k-", lw=0.8, label="MIRS")
            ax_comp.legend(loc="upper left", fontsize=8); ax_comp.set_ylabel("Score")
            ax_comp.grid(axis="y", alpha=0.3); fig_comp.tight_layout()
            st.pyplot(fig_comp, width="stretch"); plt.close(fig_comp)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 4 — WP7 NEWS ATTRIBUTION
# ════════════════════════════════════════════════════════════════════════════
elif page == "📰 WP7 News Attribution":
    st.title("📰 WP7 — News Evidence Review")
    st.info(BANNER)
    st.markdown("""
This page shows source-audited public information near each expiry. A news item is context, not proof that it caused a market move. The app does not call an LLM or search the web at run time; it validates a curated evidence file. A score is shown only when the item has a direct source, publication timestamp, human review, and availability before the expiry close.

**NES is an exploratory temporal-proximity index, not a calibrated causal score.** The WP7 sensitivity replaces Step 4's rule-based news discount starting from U. It does not apply another discount to base MIRS and never changes the reported tier.
    """)

    reviewed = nes[nes["status"] == "REVIEWED"] if "status" in nes else pd.DataFrame()
    pending = len(nes) - len(reviewed)
    m1, m2, m3 = st.columns(3)
    m1.metric("Forensic dates", len(nes))
    m2.metric("Dates with reviewed evidence", len(reviewed))
    m3.metric("Pending source audit", pending)
    if pending:
        st.warning(f"{pending} date(s) have no source-complete, human-reviewed evidence. Pending means unverified, not that no relevant information existed.")

    if len(reviewed):
        plot = reviewed.sort_values("MIRS_base", ascending=False).copy()
        fig_nes, ax_nes = plt.subplots(figsize=(11, 4))
        x = np.arange(len(plot))
        ax_nes.bar(x - 0.18, plot["MIRS_base"], label="Base MIRS", color="#176B87", width=0.36)
        ax_nes.bar(x + 0.18, plot["MIRS_WP7_sensitivity"], label="WP7 sensitivity (exploratory)", color="#e0ad42", width=0.36)
        ax_nes.set_xticks(x, plot["date"].dt.strftime("%Y-%m-%d"), rotation=45, ha="right", fontsize=8)
        ax_nes.set_ylabel("Score"); ax_nes.legend(frameon=False); ax_nes.grid(axis="y", alpha=0.25)
        fig_nes.tight_layout(); st.pyplot(fig_nes, width="stretch"); plt.close(fig_nes)

    st.subheader("Evidence and validation status")
    display = nes[["date", "expiry_type", "tier_base", "MIRS_base", "NES_exploratory", "MIRS_WP7_sensitivity", "verified_item_count", "status", "audit_notes"]].copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(display, width="stretch", height=500)

    st.subheader("Evidence source links")
    for _, score_row in nes.iterrows():
        date_key = score_row["date"].strftime("%Y-%m-%d")
        entry = kb.get("dates", {}).get(date_key, {})
        items = entry.get("items", []) if isinstance(entry, dict) else []
        with st.expander(f"{date_key} · {score_row.get('status', 'PENDING')}"):
            if not items:
                st.write("Evidence pending review. No inference is made from the empty record.")
            for item in items:
                st.markdown(f"**{item.get('category', 'Evidence')} · {item.get('event_date', 'date pending')}** — {item.get('summary', '')}")
                st.caption(f"Public by: {item.get('available_at', 'not recorded')} · review status: {item.get('review_status', 'pending')}")
                for source in item.get("sources", []):
                    if isinstance(source, dict) and source.get("url"):
                        st.markdown(f"- [{source.get('publisher', 'Source')}: {source.get('title', 'Open source')}]({source['url']}) · {source.get('published_at', 'time not recorded')}")


# ════════════════════════════════════════════════════════════════════════════
# PAGE 5 — METHODOLOGY
# ════════════════════════════════════════════════════════════════════════════
elif page == "📋 Methodology":
    st.title("📋 Methodology & Limitations")
    st.info(BANNER)

    st.markdown("""
## Pipeline Overview

```
Step 1  build_features.py         → expiry_features.parquet  (380 rows × 49 cols)
Step 2  step2_residual_model.py   → walk-forward OOS residual, SHAP
Step 3  step3_unsupervised_v2.py → IF / LOF / One-Class SVM percentile ranks
Step 4  step4_mirs_lite.py        → weighted A/T/R/Rec score and rule-based tiers
Step 5  step5_forensics.py        → 17 forensic evidence packs + PNGs
WP7     step6_wp7_news.py         → validate curated source records and build an exploratory sensitivity
WP8     step7_dashboard.py        → This dashboard
```

## MIRS-lite components and tiers

| Component | Weight | Source |
|---|---|---|
| A (whole-day anomaly) | 0.25 | EVR percentile |
| T (settlement timing) | 0.45 | Step 2 residual, final-bar range and last-bar-share percentiles |
| R (reversal) | 0.10 | Next-day reversal percentile |
| Rec (recurrence) | 0.20 | Recent same-type timing recurrence |

`U = 0.25A + 0.45T + 0.10R + 0.20Rec`; base `MIRS = U × (1 − 0.5 × news_expl)`. Step 3 ML consensus is not in this formula.

Orange requires at least two high component signals including T, with the Step 4 rule-based news explanation below its threshold. Amber means one signal or explained multiple signals; Green means no signal. These labels are not cutoffs on numeric MIRS. Red is not assignable without cross-market evidence.

## Walk-Forward Tier Counts

| Tier | Walk-forward count |
|---|---|---|
| 🟠 Orange | 2 (2024-04-18, 2024-09-12) |
| 🟡 Amber  | 64 |
| 🟢 Green  | 173 |

## Key Limitations (disclosed)

1. **Gate G4 not passed.** ML has not shown stable incremental value beyond the residual model and is excluded from base MIRS.
2. **Red tier not assignable.** No cross-market evidence in spot-only data.
3. **Step 4 news discount is a fixed rule (λ=0.5)**, not validated statistically. WP7 supplies a separate source-backed sensitivity and does not change the base tier.
4. **Walk-forward training requires ≥80 past expiries** (MIN_TRAIN_ROWS=80, lowered post-hoc from 90;
   disclosed in CHANGES.txt).
5. **CAS-regime expiries (3 Aug 2026+) excluded** — last bar is auction print, incompatible.
6. **Weekly expiries are serially correlated**; naive t-tests overstate precision.
7. **WP5/6 era effect (2019–22 vs 2023–26)** is descriptive, confounded by regime/lot changes.
8. **Strike analysis is unweighted by OI** (no F&O bhavcopy available).

## Post-hoc Setting Changes (from CHANGES.txt)
""")
    changes_path = OUT / "CHANGES.txt"
    if changes_path.exists():
        st.code(changes_path.read_text(encoding="utf-8"), language="text")
    else:
        st.warning("CHANGES.txt not found.")

    st.markdown("""
## Data Sources and WP7 status

| Layer | Source |
|---|---|
| NIFTY 50 spot prices | NSE bhavcopy (2-hr bars) via ExpiryWatch_NIFTY_WP1_WP2.xlsx |
| Control windows | Matched controls in the WP1/WP2 workbook |
| News KB | Curated JSON evidence items with direct URL, publication timestamp, information cutoff and human review |

The WP7 script validates the evidence catalogue; it does not retrieve news or call an LLM. Dates with incomplete provenance remain `SOURCE_AUDIT_PENDING`, rather than receiving NES=0. Missing evidence means unknown, not "no news". Any WP7 score is an exploratory temporal-proximity index and cannot establish that news caused a move.

## Authors

ExpiryWatch India — BTech Finance Course Project, IIT Gandhinagar.
    """)

# ─────────────────────────── FOOTER ─────────────────────────────────────────
st.markdown("---")
st.caption(
    "ExpiryWatch India v1.0 · NIFTY spot-only · Tier-A framework · "
    "MIRS ranks surveillance priority only, NOT evidence of manipulation."
)
