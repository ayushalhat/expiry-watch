# ExpiryWatch — Research Questions (RQs) Material

This directory contains the complete econometric research packages, scripts, data tables, figures, and compiled reports for **RQ5**, **RQ6**, and **RQ8** evaluating expiry-day dynamics on the Indian equity derivatives market (NIFTY 50).

---

## Overview of Research Questions

| Question | Core Hypothesis / Focus | Key Finding | Primary Scripts | Compiled Report |
| :--- | :--- | :--- | :--- | :--- |
| **RQ5** | **Settlement Window Price Distortion & Reversal**<br>Do late-session price moves on expiry days reflect temporary price pressure that reverses at the next market open? | **No.** Next-open price changes show no systematic reversal; price trajectories indicate mild continuation rather than transient manipulation. Gap narrowed slightly post-Oct 2024 reform but remains statistically indistinguishable from normal days. | `rq5_main.py`<br>`rq5_final.py`<br>`rq5_v2.py`<br>`rq5_diag.py` | [`RQ5_report_section_v2.pdf`](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ5/RQ5_report_section_v2.pdf) |
| **RQ6** | **Anomaly Signature Recurrence & Temporal Clustering**<br>Do anomalous expiry-day signatures cluster in time or recur in systematic bursts across successive expiries? | **No serial bursts.** Anomalies recur at a baseline rate on expiries (elevated relative to non-expiry days post-2023), but show zero significant serial autocorrelation or temporal clustering beyond chance. | `rq6_main.py`<br>`rq6_extra.py`<br>`rq6_v2.py`<br>`rq6_figs.py` | [`RQ6_report_section_v2.pdf`](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ6/RQ6_report_section_v2.pdf) |
| **RQ8** | **Impact of 2024–2026 Regulatory Reforms**<br>Did the SEBI derivatives framework (Oct 2024), Tuesday contract relocation (Sep 2025), and Closing Auction Session (Aug 2026) reduce or relocate anomalies? | **No clear reduction, suggestive relocation.** Late-session moves and whole-day volatility did not systematically decrease. The clearest shift is relocation: the final bar now accounts for a higher share of intraday variance on expiry days. | `rq8_main.py`<br>`rq8_v2.py`<br>`rq8_calib.py`<br>`rq8_extra.py` | [`RQ8_report_section_v2.pdf`](file:///c:/Users/sawan/Downloads/Finance_project/expiry-watch/RQs/RQ8/RQ8_report_section_v2.pdf) |

---

## Directory Organization

```text
RQs/
├── README.md                          # This documentation file
├── RQ5/
│   ├── RQ5_report_section_v2.pdf      # Final compiled econometric report section
│   ├── README.txt                     # Execution order and additions
│   ├── figures/                       # Generated figures (fig1_path.png, fig2_forest.png)
│   ├── scripts/                       # Python pipeline, diagnostic, placebo & LaTeX sources
│   │   ├── rq5_main.py
│   │   ├── rq5_final.py
│   │   ├── rq5_v2.py
│   │   ├── rq5_diag.py
│   │   ├── rq5_figs.py
│   │   ├── rq5_panel.py
│   │   ├── rq5_placebo.py
│   │   ├── rq5lib.py
│   │   └── rq5_v2.tex
│   └── tables/                        # Regression outputs, matched pairs, placebo tests, logs
├── RQ6/
│   ├── RQ6_report_section_v2.pdf      # Final compiled report section
│   ├── README.txt                     # Run order and notes
│   ├── figures/                       # fig1_timeline.png, fig2_rates.png, fig3_acf.png
│   ├── scripts/                       # Python scripts & LaTeX source
│   │   ├── rq6_main.py
│   │   ├── rq6_extra.py
│   │   ├── rq6_v2.py
│   │   ├── rq6_figs.py
│   │   ├── rq6_v2.tex
│   │   ├── rq5lib.py
│   │   └── rq8lib.py
│   └── tables/                        # Serial correlation, clustering tests, Holm p-values
├── RQ8/
│   ├── RQ8_report_section_v2.pdf      # Final compiled report section
│   ├── README.txt                     # Run order and reform break notes
│   ├── figures/                       # Rolling trends, bar profiles, alerts, forest plots
│   │   ├── fig1_path.png
│   │   ├── fig1_rolling.png
│   │   ├── fig2_bars.png
│   │   ├── fig2_forest.png
│   │   └── fig3_alerts.png
│   ├── scripts/                       # Interrupted time series (ITS), calibration & LaTeX
│   │   ├── rq8_main.py
│   │   ├── rq8_v2.py
│   │   ├── rq8_calib.py
│   │   ├── rq8_extra.py
│   │   ├── rq8_figs.py
│   │   ├── rq8lib.py
│   │   ├── rq5lib.py
│   │   ├── rq8_v2.tex
│   │   └── regime_table.tex
│   └── tables/                        # ITS regressions, pre-trend slopes, bar variance shares
└── packages/
    ├── RQ5_RQ8_v2_scripts_and_tables.zip  # Original archived package for RQ5 and RQ8
    └── RQ6_v2_scripts_and_tables.zip      # Original archived package for RQ6
```

---

## Execution Guide

### Requirements
- Python 3.9+ with `numpy`, `pandas`, `scipy`, `statsmodels`, `matplotlib`.
- LaTeX distribution (e.g., `pdflatex`) with `booktabs`, `geometry`, `helvet` for compiling `.tex` reports.

### Running RQ5
```bash
cd RQs/RQ5/scripts
python rq5_main.py ../tables
python rq5_final.py ../tables
python rq5_v2.py ../tables
python rq5_figs.py ../figures
pdflatex rq5_v2.tex
```

### Running RQ6
```bash
cd RQs/RQ6/scripts
python rq6_main.py ../tables
python rq6_extra.py ../tables
python rq6_v2.py ../tables
python rq6_figs.py ../figures
pdflatex rq6_v2.tex
```

### Running RQ8
```bash
cd RQs/RQ8/scripts
python rq8_main.py ../tables
python rq8_v2.py ../tables
python rq8_extra.py ../tables
python rq8_calib.py ../tables
python rq8_figs.py ../figures
pdflatex rq8_v2.tex
```
