from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)
wp5 = ROOT / "results_package" / "WP5"
wp6 = ROOT / "results_package" / "WP6"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 13,
                     "axes.labelsize": 10, "figure.dpi": 180, "savefig.dpi": 220})

# WP5: expiry-minus-control bps by expiry type and era.
df = pd.read_csv(wp5 / "wp5_1_settlement_timing_by_group.csv")
groups = ["All S1 expiries", "Weekly", "Monthly", "Era 2019-2022 (all)", "Era 2023-2026 (all)"]
labels = ["All", "Weekly", "Monthly", "2019-22", "2023-26"]
fig, ax = plt.subplots(figsize=(9.0, 4.7))
x = np.arange(len(groups)); width = .34
for j, (measure, label, color) in enumerate([
    ("Final-15-min absolute return", "Absolute return", "#176B87"),
    ("Final-15-min range", "High-low range", "#E07A35")
]):
    vals = [float(df[(df.group == g) & (df.measure == measure)].mean_diff.iloc[0]) * 1e4 for g in groups]
    ax.bar(x + (j - .5) * width, vals, width, label=label, color=color)
ax.axhline(0, color="#333333", linewidth=.8)
ax.set_xticks(x, labels); ax.set_ylabel("Expiry minus control mean (basis points)")
ax.set_title("Settlement-window differences by expiry group")
ax.legend(frameon=False, ncol=2, loc="upper left"); ax.grid(axis="y", alpha=.22)
fig.tight_layout(); fig.savefig(OUT / "wp5_settlement_differences.png", bbox_inches="tight"); plt.close(fig)

# WP6: sensitivity of tier counts to the signal cutoff.
tier = pd.read_csv(wp6 / "wp6_4_tier_cutoff_sensitivity.csv")
fig, ax = plt.subplots(figsize=(8.2, 4.7))
xx = np.arange(len(tier)); green = tier.green.to_numpy(); amber = tier.amber.to_numpy(); orange = tier.orange.to_numpy()
ax.bar(xx, green, label="Green", color="#6A9F58")
ax.bar(xx, amber, bottom=green, label="Amber", color="#E0AD42")
ax.bar(xx, orange, bottom=green+amber, label="Orange", color="#D35D47")
for i, row in tier.iterrows():
    ax.text(i, row.n_scored + 5, f"O {row.orange}  A {row.amber}  G {row.green}", ha="center", fontsize=8)
ax.set_xticks(xx, [f"{v:.2f}" for v in tier.signal_cutoff]); ax.set_xlabel("Signal percentile cutoff")
ax.set_ylabel("Walk-forward expiries (n=239)"); ax.set_title("MIRS-lite tier counts depend on the signal cutoff")
ax.set_ylim(0, 275)
ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.0))
ax.grid(axis="y", alpha=.22)
fig.tight_layout(); fig.savefig(OUT / "wp6_tier_sensitivity.png", bbox_inches="tight"); plt.close(fig)

PRE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=25mm,headheight=14pt]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{booktabs,tabularx,longtable,array}
\usepackage{amsmath}
\usepackage{xcolor}
\usepackage{fancyhdr}
\usepackage{caption}
\usepackage[hidelinks]{hyperref}
\usepackage{enumitem}
\definecolor{navy}{HTML}{15334A}
\definecolor{teal}{HTML}{176B87}
\captionsetup{font=small,labelfont=bf}
\setlength{\parskip}{5pt}
\setlength{\parindent}{0pt}
\setlist{nosep,leftmargin=1.5em}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small ExpiryWatch India}\fancyhead[R]{\small Work Package @@WP@@}
\fancyfoot[C]{\thepage}
\newcommand{\banner}{\begin{center}\colorbox{navy}{\parbox{0.94\linewidth}{\centering\color{white}\textbf{SURVEILLANCE PRIORITY ONLY -- NOT EVIDENCE OF MANIPULATION}}}\end{center}}
\newcommand{\bps}{\,\mathrm{bp}}
\begin{document}
\begin{titlepage}\centering\vspace*{22mm}
{\Large ExpiryWatch India\par}\vspace{18mm}
{\color{navy}\Huge\bfseries @@TITLE@@\par}\vspace{8mm}
{\Large @@SUBTITLE@@\par}\vspace{18mm}
\rule{0.72\linewidth}{0.7pt}\par\vspace{12mm}
{\large Alhat Ayush Arvind (24110028)\par}\vspace{4mm}
{\large NIFTY 50 spot-only empirical prototype\par}\vfill
{\large 18 November 2026\par}\vspace{5mm}
{\small Work-package report; results based on the supplied project outputs}\par
\end{titlepage}
\banner
\begin{abstract}
@@ABSTRACT@@
\end{abstract}
\tableofcontents\clearpage
"""
POST = r"""\end{document}
"""

def build(title, wp, subtitle, abstract, body):
    return PRE.replace("@@WP@@", wp).replace("@@TITLE@@", title).replace("@@SUBTITLE@@", subtitle).replace("@@ABSTRACT@@", abstract) + body + POST

wp5_body = r"""\section{Purpose and scope}
Work Package 5 in the project proposal asks whether expiry-related price movement is concentrated in settlement-relevant time, a small set of index constituents, low-flow/high-impact episodes, or derivative-linked cross-market patterns. This report documents the subset that can be computed from NIFTY spot prices at two-hour frequency and the existing matched-control workbook. The data support the final 15-minute bar and next-day diagnostics, plus an unweighted close-to-strike check. They do not support a full cross-market price-influence analysis.

All scores and elevated observations are research screening outputs. They do not identify actors, intent, or a legal violation. The CAS period is excluded: the input has nine CAS expiries and the Step 2/3/4 package is restricted to comparable S1 sessions.

\section{Inputs and sample}
The analysis uses the NIFTY spot series and WP1/WP2 workbook in the project data directory, the five WP5 result tables in the results package, and the matching logic already implemented in WP2. The analysis sample contains 367 S1 expiries with three matched controls each: 282 weekly and 85 monthly. Four otherwise eligible expiries are omitted after feature warm-up; nine CAS expiries are outside this S1 sample. The settlement-relevant interval observable in the supplied bar structure is 15:15--15:30 only. Controls are drawn within plus or minus 60 calendar days; the matching and standardisation inherit the WP2 full-sample design and therefore have mild look-ahead exposure.

\section{Methods}
\subsection{Settlement timing}
For each expiry, final-bar absolute return, final-bar high-low range, and the final bar's share of the four-bar daily price path are compared with the mean of three matched non-expiry controls. The primary contrast is the expiry-minus-control difference. The tables report Welch tests, Wilcoxon tests, and Benjamini--Hochberg adjusted q-values within each result table. Results are also grouped by expiry type and broad era (2019--2022 and 2023--2026). These are subgroup descriptions, not a causal reform design.

\subsection{Concentration, strike alignment, reversal and recurrence}
Effect concentration sorts expiry-minus-control differences and reports how much positive excess is carried by the largest 5, 10 and 20 percent of events. Strike distance is computed from the 15:30 spot close, on 50- and 100-point grids, without open-interest weighting; under a uniform fractional strike position, the expected mean fractional distance is 0.25 and the expected share within 0.05 is 10 percent. Next-day reversal is the signed next-day return difference relative to controls, with positive values defined as movement against the expiry-day direction. Recurrence is assessed using lag-one autocorrelation and permutation tests of consecutive same-type top-decile events; pair-test q-values use BH correction.

\section{Results}
\subsection{Settlement-window activity}
Across all 367 expiries, final-15-minute absolute return is 1.48 basis points higher than controls (19.2 percent relative; Welch $p=0.004$, BH $q=0.009$). Final-bar range is 1.88 basis points higher (12.0 percent; $p<0.001$, $q<0.001$), and the final-bar share of the daily path is 2.03 percentage points higher ($p<0.001$, $q=0.002$). The effect differs by expiry type: weekly absolute return is 0.53 basis points higher (6.9 percent; $p=0.328$), whereas monthly absolute return is 4.62 basis points higher (60.4 percent; $p<0.001$). Monthly final-bar range is 6.91 basis points higher (44.7 percent; $p<0.001$). The weekly estimates are small and not statistically distinguishable from zero in this comparison.

The broad era split is also marked. For 2019--2022 the absolute-return difference is -0.13 basis points ($p=0.865$); for 2023--2026 it is +3.02 basis points, or 49.5 percent ($p<0.001$, BH $q<0.001$). The later-era estimate is descriptive and overlaps changes in expiry composition and market rules; it is not an estimate of the effect of a specific policy.

\begin{figure}[htbp]\centering\includegraphics[width=0.92\linewidth]{wp5_settlement_differences.png}\caption{Expiry-minus-control means for final-bar absolute return and range. Values are in basis points; era groups overlap with expiry-type composition.}\end{figure}

\begin{table}[htbp]\centering\caption{Table 1: Primary settlement-timing contrasts}\small
\begin{tabular}{lrrrr}\toprule Group & $n$ & $|r_4|$ diff. (bp) & Relative & Range diff. (bp)\\\midrule
All S1 expiries & 367 & +1.48 & +19.2\% & +1.88\\
Weekly & 282 & +0.53 & +6.9\% & +0.36\\
Monthly & 85 & +4.62 & +60.4\% & +6.91\\
2019--2022 & 180 & -0.13 & -1.3\% & +0.32\\
2023--2026 & 187 & +3.02 & +49.5\% & +3.37\\\bottomrule\end{tabular}
\caption*{Welch two-sided $p$ for all / weekly / monthly / 2019--22 / 2023--26 absolute-return contrasts: 0.004 / 0.328 / $<0.001$ / 0.865 / $<0.001$.}
\end{table}

\subsection{Concentration and strike alignment}
The top 10 percent of expiries (37 events) account for 52.6 percent of the total positive excess final-bar absolute return and 150.5 percent of net excess. A share above 100 percent means the remaining events net to a negative contribution. This concentration describes the distribution of the measured timing effect; it is not constituent-level influence concentration.

Across the full sample, mean distance to the nearest 50-point grid is 0.244 (uniform-position reference 0.250); 11.4 percent of closes fall within 0.05 of a 50-point strike compared with 10 percent expected ($p=0.339$, BH $q=0.678$). The corresponding 100-point share is 8.2 percent ($p=0.296$). Monthly 100-point proximity is 3.5 percent ($p=0.045$), but does not survive the within-table correction ($q=0.454$). The evidence does not support a robust spot-close pinning result. These distances are not open-interest-weighted and the close is not the settlement VWAP.

\subsection{Reversal and recurrence}
Mean next-day signed reversal difference is +0.115 percentage points for all expiries ($p=0.090$, BH $q=0.383); weekly is +0.076 points ($q=0.383) and monthly +0.245 points ($q=0.383). None of the reported conditional groups survives correction. The pattern is therefore weak evidence of reversal, not a reliable post-expiry reversal effect.

No lag-one autocorrelation is significant after correction for either weekly or monthly expiries. One nominal recurrence result appears for weekly last-bar-share differences: seven consecutive top-decile pairs versus 2.84 expected under random ordering ($p=0.014$), but BH $q=0.086$. It does not pass the stated 5 percent corrected threshold. Quarter-end monthly comparisons are also non-significant (final-bar absolute return $p=0.833$; range $p=0.578$; last-bar share $p=0.981$). The annual share of type-specific top-decile events varies from 4 to 17 percent, without a systematic pattern established by this descriptive summary.

\section{WP5 coverage and unmet requirements}
\begin{table}[htbp]\centering\caption{Table 2: Proposal diagnostics and data status}\small
\begin{tabularx}{\linewidth}{p{0.24\linewidth}p{0.18\linewidth}X X}\toprule Diagnostic & Status & Limitation in this run & Data required\\\midrule
Settlement timing concentration & Partial & Final 15 minutes only; final hour/30/5 minutes and settlement VWAP are unavailable & Minute-level index prices and settlement prints\\
Index-contribution concentration (WPPI/EIC) & Not built & No component returns or weights in the analysis input & Historical NIFTY constituent prices and index weights\\
Price impact (Kyle $\lambda$) & Not built & No signed flow, turnover, or order-book depth & Trade/order data with direction and volume\\
Cross-market asymmetry (CMBR) & Not built & No option/futures exposure or participant positioning & F\&O bhavcopy, options OI by strike, futures basis; participant data for expanded test\\
Strike/payoff alignment & Partial & Spot close, equally weighted; no option OI weighting & F\&O bhavcopy with strike-level OI and settlement values\\
Reversal & Partial & Next trading day only; news and intraday dynamics are not controlled & Intraday post-expiry data and WP7 event/news retrieval\\
Recurrence & Partial & NIFTY only; same-type event sequence & Comparable BANKNIFTY, FINNIFTY and SENSEX expiry series\\\bottomrule\end{tabularx}\end{table}

\section{Limitations and interpretation}
The two-hour bar source resolves the last 15 minutes from the 15:15 bar but cannot reconstruct finer settlement windows. Matched controls are observational and can differ in unmeasured state. The broad era split can reflect policy, lot-size, tax, weekday, and expiry-composition changes; it should not be read causally. P-values are exploratory, and BH correction is performed within each listed table rather than across every analysis in the project. Weekly expiries form a time sequence, so independent-observation tests may overstate precision. Strike analysis omits OI and uses the close. The sample excludes CAS expiries. These results are descriptive market-behaviour diagnostics and cannot establish price influence by any participant.

\section{Implications for later work}
The strongest current finding is a late-session difference concentrated in monthly expiries and the 2023--2026 era, with substantial event-level concentration. The next data step should resolve 5-, 30- and 60-minute windows and combine index moves with constituent contributions, option OI, futures basis, turnover and order-book measures. WP7 should condition selected episodes on dated public information; WP8 should use a separately specified reform design with pre-trend checks and overlapping-rule changes addressed. Until those layers are present, WP5 remains a spot-only subset.

\appendix
\section{Definitions, reproducibility and file map}
Here $r_4$ is the final 15-minute absolute return; range is the high-low range of that bar; last-bar share is its absolute path contribution relative to the four-bar day. The package tables are \texttt{WP5/wp5\_1\_settlement\_timing\_by\_group.csv} through \texttt{wp5\_5\_recurrence\_serial\_dependence.csv}, with supplementary quarter-end and annual tables. The analysis code is \texttt{src/wp5\_wp6\_results.py}; price features and matching are documented in WP1/WP2. Main counts and statistics are in \texttt{RESULTS\_SUMMARY.txt}.

\section{Data dictionary (report variables)}
\begin{description}[style=nextline]
\item[Expiry-minus-control difference] Expiry observation less the mean of its three matched controls.
\item[Final-bar absolute return] Absolute close-to-close return for 15:15--15:30.
\item[Final-bar range] High-low range scaled by the index level.
\item[Last-bar share] Final-bar path measure divided by the four-bar daily path measure.
\item[Fractional strike distance] Distance to the nearest strike grid, divided by grid spacing; zero denotes an exact grid point.
\item[Reversal difference] Next-day signed move against the expiry-day direction, less the matched-control mean.
\item[BH q-value] Benjamini--Hochberg adjusted value within the specified results table.
\end{description}
"""

wp6_body = r"""\section{Purpose and scope}
WP6 proposes unsupervised or one-class methods because verified manipulation labels are sparse and legally complex. This report records the implemented spot-only prototype: an expected late-session-move residual model, three unsupervised rankers, and MIRS-lite as a transparent surveillance-priority score. It covers walk-forward and clearly separated retrospective results, score stability, threshold sensitivity, and the evidence cards. It does not claim an automated decision system or a manipulation detector.

\section{Data, sample and analysis conventions}
The run begins with 367 model-eligible S1 expiries (282 weekly, 85 monthly) and 1,728 S1 trading days. Step 2 uses 1,361 non-expiry days for training/evaluation pools. Four expiry observations are lost to feature warm-up. The main walk-forward set for unsupervised Version A and MIRS contains 239 expiries from 2022 onward; Version B, which requires the Step 2 walk-forward residual, scores 135 expiries from 2024 onward. Retrospective scores use leave-one-year-out/in-sample information as labelled in the output and are descriptive only. Nine CAS expiries are excluded. Throughout, a high score means higher surveillance review priority relative to past same-type expiries.

The scripts record post-hoc changes in \texttt{outputs/CHANGES.txt}: the minimum training history was changed from 90 to 80 rows so Version B could score 2024 with 84 training rows; test-point jitter was removed while training jitter was retained; and the LOF training reference was restored to \texttt{negative\_outlier\_factor\_}. Step 4 and Step 5 have no post-hoc changes recorded. These choices are disclosed because they were made after an earlier look at results.

\section{Methods}
\subsection{Expected late-session-move residual}
Step 2 predicts log final-15-minute absolute return and log range from pre-15:15 state features using non-expiry days. The feature set is $\{rv20,r5,prev\_absret,rv\_first3,abs\_trend,strike50,gap,event\}$. A gradient-boosting model and a ridge benchmark are evaluated with a report-style split and an expanding walk-forward procedure. The residual is actual minus expected activity; positive standardized residuals identify closes more active than the model predicts. SHAP values are calculated for explanatory context on a model fit to the non-expiry pool; they are not a causal decomposition.

\subsection{Unsupervised models}
Version A ranks expiry behaviour using EVR, final-bar return difference, range difference, last-bar-share difference, and reversal ratio. Version B adds the Step 2 walk-forward residual and begins only when at least 80 past rows are available. Isolation Forest, Local Outlier Factor (LOF), and One-Class SVM scores are converted to one-sided percentiles against past same-type expiries, with activity above the median retained. Agreement is reported using Spearman correlations, bootstrap confidence intervals, and top-tail consensus counts compared with a permutation independence baseline. Hyperparameter and seed checks measure rank and top-20 stability.

\subsection{MIRS-lite}
MIRS-lite combines past-only percentiles for whole-day anomaly $A$, settlement timing $T$, reversal $R$, and recurrence $Rec$, with weights 0.25, 0.45, 0.10 and 0.20. The unadjusted score is $U$; an event-based news-explanation term reduces it by $U(1-0.5\times news\_expl)$. The news term is rule-based and not yet validated by WP7. ML consensus is not part of the base score. Orange requires at least two component signals including settlement timing and no qualifying news explanation; Amber marks one signal or multiple explained signals; Green has none. Red is unassignable without cross-market evidence. The signal percentile threshold defaults to 0.90.

\section{Results}
\subsection{Step 2 residual model}
In the report-style split, gradient boosting has out-of-sample $R^2=0.061$ for log final-bar absolute return and 0.105 for log range; ridge has 0.026 and -0.075. In expanding walk-forward evaluation, non-expiry OOS $R^2$ is 0.070 for log absolute return and 0.229 for log range. Among walk-forward expiries from 2022 onward, the absolute-return residual is 0.282 log units above the non-expiry mean ($n=239$ versus 888; Welch $t=4.35$, $p<0.001$); monthly difference is 0.627 ($n=55$) and weekly 0.179 ($n=184$, $p=0.011$). This is consistent with greater close activity than the non-expiry model predicts, but residual scale is not a causal effect.

Mean absolute SHAP values for the primary final-return target are led by $rv20$ (0.1331) and $rv\_first3$ (0.1183), followed by $r5$ (0.0478), $abs\_trend$ (0.0347), and $prev\_absret$ (0.0216). The event indicator has zero reported mean absolute importance in this fit. The retrospective top events and the walk-forward top events are kept distinct; the latter is the appropriate basis for ranking.

\subsection{Model agreement and consensus}
For Version A, IF--LOF agreement is $\rho=0.103$ (95\% CI [-0.046, 0.240]), IF--SVM is -0.026 ([-0.164, 0.115]), and LOF--SVM is 0.175 ([0.042, 0.299]). These low correlations indicate that the methods often rank different expiries. At the 0.90 score threshold, 18 expiries are flagged by at least two models versus 10.23 expected under score independence ($p_{perm}=0.0026$); all-three consensus is zero versus 0.46 expected. Version B also shows excess two-model consensus at 0.90 (13 vs 6.24 expected; $p=0.0012$), but its smaller sample and different feature set make it a separate sensitivity, not a direct replication.

At Version A's 0.90 consensus threshold, flagged expiries have mean residual 1.135 versus 0.223 for the remaining scored events, and mean EVR 1.772 versus 1.143. The rank-sum comparisons are small in p-value. However, this profile is partly circular because the unsupervised inputs include the same final-bar behaviour used by the residual and EVR measures. Gate G4 gives Spearman $\rho=0.137$ between the ML percentile sum and Step 2 residual ($p=0.034$, $n=239$), with top-20 overlap 5/20 in the Step 3 diagnostic. This does not establish stable incremental out-of-sample value. G4 is not passed; ML stays out of the base score.

\subsection{MIRS-lite, tiers and forensics}
At the default 0.90 signal cutoff, the 239 walk-forward expiries yield 173 Green, 64 Amber, and 2 Orange observations: 18 April 2024 and 12 September 2024. Six of the top 20 by MIRS are Green, demonstrating why the ordered review list is more informative than a tier label alone. The tier rule is sensitive to its threshold: at cutoffs 0.80, 0.85, 0.90, and 0.95, Orange counts are 14, 7, 2, and 1, respectively. Only 12 September 2024 remains Orange for every cutoff from 0.85 upward.

Tier membership is sensitive to the signal threshold, so we report rankings and the threshold sensitivity table, not the tiers alone.

\begin{figure}[htbp]\centering\includegraphics[width=0.86\linewidth]{wp6_tier_sensitivity.png}\caption{Walk-forward tier counts across signal percentile cutoffs. Lower cutoffs produce more Orange and Amber labels.}\end{figure}

Weight sensitivity is comparatively high in rank terms: the 300-draw walk-forward test reports median Spearman correlation 0.97 and a mean top-20 overlap of 16.9/20. Adding 15 percent ML consensus as a sensitivity changes MIRS ordering modestly ($\rho=0.96$ versus base), but ML consensus itself correlates only 0.29 with MIRS in the walk-forward results; the base score therefore remains ML-free. The automated Step 5 pack contains 17 event charts/cards, including the two walk-forward Orange events, the top MIRS events, timing extremes and three negative controls. Its WP7 news blocks are empty. The 50 percent news discount is a mechanical prototype setting; the negative controls show the rule is applied, not that the discount is appropriately sized.

\begin{table}[htbp]\centering\caption{Table 1: Walk-forward MIRS tier sensitivity}\small
\begin{tabular}{rrrrr}\toprule Signal cutoff & Scored & Orange & Amber & Green\\\midrule
0.80 & 239 & 14 & 110 & 115\\
0.85 & 239 & 7 & 94 & 138\\
0.90 & 239 & 2 & 64 & 173\\
0.95 & 239 & 1 & 34 & 204\\\bottomrule\end{tabular}\end{table}

\begin{table}[htbp]\centering\caption{Table 2: Top 20 expiries by walk-forward MIRS}\scriptsize
\begin{tabular}{rllrrl}\toprule Rank & Date & Type & MIRS & ML consensus & Tier\\\midrule
1 & 2024-04-18 & Weekly & 0.740 & 0.981 & Orange\\
2 & 2023-11-16 & Weekly & 0.728 & 0.981 & Amber\\
3 & 2024-09-12 & Weekly & 0.725 & 0.967 & Orange\\
4 & 2025-05-22 & Weekly & 0.712 & 0.672 & Green\\
5 & 2023-12-21 & Weekly & 0.698 & 0.209 & Green\\
6 & 2022-03-24 & Weekly & 0.677 & 0.236 & Amber\\
7 & 2023-07-06 & Weekly & 0.676 & 0.981 & Amber\\
8 & 2026-06-23 & Weekly & 0.675 & 0.498 & Amber\\
9 & 2025-05-08 & Weekly & 0.667 & 0.981 & Amber\\
10 & 2024-03-28 & Monthly & 0.659 & 0.729 & Amber\\
11 & 2022-11-24 & Monthly & 0.656 & 0.415 & Amber\\
12 & 2024-02-08 & Weekly & 0.654 & 0.557 & Amber\\
13 & 2025-04-30 & Monthly & 0.649 & 0.992 & Amber\\
14 & 2023-09-28 & Monthly & 0.647 & 0.070 & Green\\
15 & 2025-06-12 & Weekly & 0.638 & 0.469 & Amber\\
16 & 2023-07-27 & Monthly & 0.638 & 0.247 & Green\\
17 & 2022-04-07 & Weekly & 0.638 & 0.925 & Amber\\
18 & 2026-05-12 & Weekly & 0.637 & 0.359 & Amber\\
19 & 2023-06-08 & Weekly & 0.632 & 0.209 & Green\\
20 & 2025-10-14 & Weekly & 0.631 & 0.725 & Green\\\bottomrule\end{tabular}
\caption*{The tier is a review label at the default 0.90 component threshold. The ranking is the primary ordered output. Six listed events are Green.}\end{table}

\section{Requirements not implemented}
\begin{table}[htbp]\centering\caption{Table 3: WP6 methods and evidence gaps}\small
\begin{tabularx}{\linewidth}{p{0.24\linewidth}p{0.20\linewidth}X X}\toprule Method / layer & Status & Current boundary & Additional evidence or work\\\midrule
Gradient-boosted residual & Built & Spot-only target; state model, not a manipulation label & Intraday return/flow targets and rolling recalibration\\
Isolation Forest, LOF, One-Class SVM & Built & Weak cross-model agreement and limited expiry sample & Frozen validation, broader regimes and genuinely independent features\\
SHAP & Built for Step 2 & Explains fitted residual model; no attribution for IF/LOF/SVM & Per-event model explanations or validated surrogate explanations\\
MIRS-lite & Prototype & News discount unvalidated; Red unavailable; missing cross-market drivers make it an upper-bound priority score & WP3/WP4 inputs, WP7 cited evidence, calibrated review outcomes\\
Autoencoder & Not built & No need to add a black-box model without validation capacity & Larger sample and feature attribution plan\\
HDBSCAN / recurring clusters & Not built & Small sample and regime changes complicate rare-cluster interpretation & More indices and validated regime taxonomy\\
Intraday change point & Not built & Two-hour bars cannot locate short structural breaks & Minute or finer index bars\\
Case-study validation & Pending WP8 & No frozen case-study evaluation in this package & Dated regulatory case sessions and pre-registered evaluation\\\bottomrule\end{tabularx}\end{table}

\section{Limitations and interpretation}
The 239-event walk-forward set is modest and model agreement is weak. Version B covers only 135 events and includes a residual feature that overlaps conceptually with other behaviour measures. Consensus enrichment is therefore not independent confirmation. Retrospective scores use future information relative to some event dates and must not be presented as live forecasting performance. Settings were changed after results were inspected, as disclosed above, creating a risk of analyst degrees of freedom. Stability across the tested seeds/hyperparameters does not repair this selection concern.

MIRS-lite uses illustrative weights and fixed rule thresholds. Its event discount is not evidence-based until WP7 is completed. Six of the top 20 MIRS events are Green at the default threshold, and labels change as the cutoff moves. Red cannot be assigned because the data contain no cross-market evidence. The score ranks cases for review only; it is an upper-bound priority estimate because legitimate hedge, liquidity, rebalancing and arbitrage explanations are unobserved. Automated forensics hypotheses are prompts for investigation, not findings. All WP5/WP6 inference is exploratory, and the underlying matched-control construction carries mild look-ahead exposure.

\section{Implications and next work}
WP6 demonstrates a reproducible, explainable screening pipeline using a residual model and three one-class methods, with transparent rank and threshold diagnostics. It does not pass the incremental-value gate for adding ML to the score. The practical output is the top-20 MIRS review list with components and threshold sensitivity. Before operational use, freeze the specification, complete WP7 source-backed news review, add options/futures/constituent/liquidity inputs, validate on held-out regulatory case studies under WP8, and test whether ranks remain useful across regimes and indices.

\appendix
\section{Reproducibility and package map}
The run scripts are \texttt{src/step2\_residual\_model.py}, \texttt{src/step3\_unsupervised\_v2.py}, \texttt{src/step4\_mirs\_lite.py}, and \texttt{src/step5\_forensics.py}. WP6 summary tables are \texttt{results\_package/WP6/wp6\_1\_model\_agreement.csv} through \texttt{wp6\_5\_top20\_mirs\_walkforward.csv}; Step 2/3/4 diagnostics and the 17 forensics cards appear under \texttt{results\_package/from\_steps/}. \texttt{outputs/CHANGES.txt} documents the post-hoc edits.

\section{Data dictionary}
\begin{description}[style=nextline]
\item[EVR] Expiry-window realised volatility divided by matched-control expected volatility.
\item[$A$] Past-only percentile for whole-day anomaly (EVR).
\item[$T$] Past-only percentile for settlement timing; combines residual, final-bar range and last-bar-share dimensions.
\item[$R$] Past-only percentile for next-day reversal ratio.
\item[$Rec$] Recurrence component based on recent same-type expiries with high settlement-timing scores.
\item[$U$] Weighted mean of the four upward components before the news explanation discount.
\item[MIRS] MIRS-lite score after the rule-based news explanation discount; used for review ranking.
\item[ML consensus] Median percentile across IF, LOF and One-Class SVM; separately reported, not included in base MIRS.
\item[Walk-forward] Each event is scored using earlier observations only, subject to the minimum-history rules.
\item[Retrospective] Descriptive analysis that can use future years; not out-of-sample evidence.
\end{description}
"""

(OUT / "WP5_Cross_Market_Diagnostics.tex").write_text(build(
    "Work Package 5", "5", "Cross-Market Price-Influence Diagnostics -- Spot-Only Subset",
    "This report evaluates the WP5 diagnostics that can be estimated from two-hour NIFTY spot data and matched controls. Across 367 S1 expiries, elevated final-bar activity is concentrated in monthly expiries and the 2023--2026 era, while strike proximity, next-day reversal and serial recurrence provide limited or non-robust evidence. Constituent concentration, price impact and cross-market asymmetry remain unmeasured because the required constituent, flow, options and futures data are absent. The findings describe market behaviour and surveillance priority only.",
    wp5_body), encoding="utf-8")
(OUT / "WP6_AI_ML_Anomaly_Detection.tex").write_text(build(
    "Work Package 6", "6", "AI/ML Anomaly Detection -- Spot-Only Prototype",
    "This report documents a walk-forward residual model, Isolation Forest, Local Outlier Factor, One-Class SVM, and a transparent MIRS-lite score for ranking NIFTY expiry events for review. The unsupervised models show weak agreement; consensus at the 90th percentile exceeds a permutation independence baseline, but its enrichment partly reuses the same behaviour features. The ML incremental-value gate is not passed, the news discount is unvalidated, and tier membership is sensitive to its threshold. The system is a screening prototype, not evidence of manipulation.",
    wp6_body), encoding="utf-8")
import re
for source in [OUT / "WP5_Cross_Market_Diagnostics.tex", OUT / "WP6_AI_ML_Anomaly_Detection.tex"]:
    tex = source.read_text(encoding="utf-8")
    stack = []
    for line_no, line in enumerate(tex.splitlines(), 1):
        line = re.sub(r"(?<!\\\\)%.*$", "", line)
        for match in re.finditer(r"(?<!\\\\)[{}]", line):
            if match.group() == "{":
                stack.append(line_no)
            elif stack:
                stack.pop()
            else:
                raise ValueError(f"{source.name}:{line_no}: extra closing brace")
    if stack:
        raise ValueError(f"{source.name}: unclosed braces at lines {stack[-5:]}")
    env_stack = []
    for token in re.finditer(r"\\(begin|end)\{([^}]+)\}", tex):
        action, name = token.groups()
        if action == "begin":
            env_stack.append(name)
        elif not env_stack or env_stack.pop() != name:
            raise ValueError(f"{source.name}: mismatched LaTeX environment near {name}")
    if env_stack:
        raise ValueError(f"{source.name}: unclosed LaTeX environments {env_stack}")
    print(source.name, f"({source.stat().st_size:,} bytes): braces and environments balanced")
print(f"Wrote report sources and Matplotlib figures to {OUT}")
