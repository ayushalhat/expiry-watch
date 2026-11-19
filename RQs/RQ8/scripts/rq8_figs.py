import sys, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT = sys.argv[1]; REP = sys.argv[2]
BLUE, ORANGE = '#2a78d6', '#eb6834'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'text.color': INK, 'axes.spines.top': False, 'axes.spines.right': False})
D1, D2 = pd.Timestamp('2024-10-01'), pd.Timestamp('2025-09-01')
E = pd.read_pickle(f'{OUT}/Epre.pkl')
W = 26
roll = E[['EVR', 'L15R']].rolling(W).median().dropna()

# Fig 1: rolling medians, two single-series panels
fig, axs = plt.subplots(2, 1, figsize=(6.8, 5.0), sharex=True)
for ax, col, lab in [(axs[0], 'L15R', 'Last-15-minute move vs matched days\n(rolling median, ratio)'),
                     (axs[1], 'EVR', 'Whole-day volatility vs matched days\n(rolling median, ratio)')]:
    ax.plot(roll.index, roll[col], color=BLUE, lw=2)
    ax.axhline(1, color=INK2, lw=0.8, ls=(0, (3, 3)))
    for d, t in [(D1, 'Oct 2024\npackage + STT'), (D2, 'Sep 2025\nTuesday expiry')]:
        ax.axvline(d, color=ORANGE, lw=1.6)
    ax.set_ylabel(lab, fontsize=8); ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_ylim(0, max(roll[col].max() * 1.1, 1.5))
axs[0].text(D1, axs[0].get_ylim()[1] * 0.97, ' Oct 2024', color=INK2, fontsize=7.5, va='top', ha='right')
axs[0].text(D2, axs[0].get_ylim()[1] * 0.97, ' Sep 2025', color=INK2, fontsize=7.5, va='top', ha='left')
fig.tight_layout(); fig.savefig(f'{REP}/fig1_rolling.png', dpi=220); plt.close(fig)

# Fig 2: per-bar profile pre vs post
B = pd.read_csv(f'{OUT}/bar_profile.csv')
bars = ['09:15-11:15', '11:15-13:15', '13:15-15:15', '15:15-15:30']
fig, ax = plt.subplots(figsize=(6.6, 3.4)); x = np.arange(4)
for g, col, nm, off in [('Pre-reform (P0)', ORANGE, 'Before Oct 2024 (n=271)', -0.06), ('Post-reform (P1-P3)', BLUE, 'Oct 2024 to Jul 2026 (n=96)', 0.06)]:
    d = B[B.group == g].set_index('bar').loc[bars]
    ax.errorbar(x + off, d.med, yerr=[d.med - d.lo, d.hi - d.med], color=col, lw=2, marker='o', ms=6, mfc=col, mec='white', mew=1.2, capsize=0, label=nm)
ax.axhline(1, color=INK2, lw=0.8, ls=(0, (3, 3)))
ax.set_xticks(x); ax.set_xticklabels(['09:15-11:15', '11:15-13:15', '13:15-15:15', '15:15-15:30\n(last bar)'], fontsize=8)
ax.set_ylabel('Median expiry / matched-day\n|move| ratio, by bar'); ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.legend(frameon=False, loc='upper left', fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{REP}/fig2_bars.png', dpi=220); plt.close(fig)

# Fig 3: share of EVR>2.7 by half-year
h = E.index.year.astype(str) + np.where(E.index.month <= 6, 'H1', 'H2')
g = E.assign(h=h).groupby('h').agg(n=('alert_E', 'size'), a=('alert_E', 'sum'))
g['pct'] = 100 * g.a / g.n
fig, ax = plt.subplots(figsize=(6.8, 3.3)); x = np.arange(len(g))
ax.bar(x, g.pct, color=BLUE, width=0.62)
for i, (p, a, n) in enumerate(zip(g.pct, g.a, g.n)):
    ax.text(i, p + 0.6, f'{a}/{n}', ha='center', fontsize=6.8, color=INK2)
i1 = list(g.index).index('2024H2') - 0.5 + 0.5  # Oct 2024 sits inside 2024H2
ax.axvline(list(g.index).index('2024H2'), color=ORANGE, lw=1.6)
ax.axvline(list(g.index).index('2025H2') - 0.5 + 0.17, color=ORANGE, lw=1.6, ls=(0, (4, 2)))
ax.set_xticks(x); ax.set_xticklabels([s.replace('H1', '\nH1').replace('H2', '\nH2') for s in g.index], fontsize=7)
ax.set_ylabel('Expiries with whole-day\nvolatility > 2.7x matched (%)'); ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig(f'{REP}/fig3_alerts.png', dpi=220); plt.close(fig)
g.to_csv(f'{OUT}/alertE_halfyear.csv'); print(g.to_string())
