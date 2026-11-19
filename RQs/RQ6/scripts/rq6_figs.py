import sys, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from statsmodels.stats.proportion import proportion_confint as pc
OUT, REP = sys.argv[1], sys.argv[2]
BLUE, ORANGE = '#2a78d6', '#eb6834'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'text.color': INK, 'axes.spines.top': False, 'axes.spines.right': False})
E = pd.read_pickle(f'{OUT}/E6.pkl')
# Fig 1: every expiry
fig, ax = plt.subplots(figsize=(6.8, 3.6))
a = E[E.alert_L == 1]; n = E[E.alert_L == 0]
ax.scatter(n.index, n.L15R.clip(lower=0.03), s=9, color=BLUE, alpha=0.55, lw=0, label=f'Expiries below threshold (n={len(n)})')
ax.scatter(a.index, a.L15R, s=14, color=ORANGE, lw=0, label=f'Last 15 minutes over 3x matched days (n={len(a)})')
ax.axhline(3, color=INK2, lw=0.8, ls=(0, (3, 3))); ax.axhline(1, color=GRID, lw=1)
ax.set_yscale('log'); ax.set_yticks([0.1, 0.3, 1, 3, 10, 30]); ax.set_yticklabels(['0.1', '0.3', '1', '3', '10', '30'])
ax.set_ylabel('Last-15-minute move: expiry / matched days'); ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.legend(frameon=False, loc='upper left', fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{REP}/fig1_timeline.png', dpi=220); plt.close(fig)
# Fig 2: alert rates
P = pd.read_csv(f'{OUT}/S_placebo_alert_rates.csv'); P['k'] = (P.alertL / 100 * P.n).round().astype(int)
rows = []
for nm, g in [('Weekly expiries, all years', E[E.type == 'weekly']), ('Monthly expiries, all years', E[E.type == 'monthly'])]:
    rows.append((nm, int(g.alert_L.sum()), len(g), 'e'))
rows.append(('Thursday expiries (to Aug 2025)', int(P.k.iloc[0]), int(P.n.iloc[0]), 'e'))
rows.append(('Mon/Tue/Wed/Fri placebo days', int(P.k.iloc[1:].sum()), int(P.n.iloc[1:].sum()), 'p'))
fig, ax = plt.subplots(figsize=(6.6, 2.9)); y = np.arange(len(rows))[::-1].astype(float); y[2:] -= 0.6
for yy, (nm, k, nn, t) in zip(y, rows):
    lo, hi = pc(k, nn, method='wilson'); col = BLUE if t == 'e' else ORANGE
    ax.plot([100 * lo, 100 * hi], [yy, yy], color=col, lw=2, solid_capstyle='round'); ax.plot(100 * k / nn, yy, 'o', ms=6, color=col, mec='white', mew=1.2)
    ax.text(100 * hi + 1, yy, f'{100 * k / nn:.1f}%  ({k}/{nn})', va='center', fontsize=7.5, color=INK2)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=8); ax.set_xlim(0, 52)
ax.set_xlabel('Days with last-15-minute move above 3x matched days (%)'); ax.grid(axis='x', color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.legend(handles=[Line2D([0], [0], color=BLUE, lw=2, marker='o', ms=5, label='Expiry days'), Line2D([0], [0], color=ORANGE, lw=2, marker='o', ms=5, label='Placebo (normal days)')], frameon=False, loc='lower right', fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{REP}/fig2_rates.png', dpi=220); plt.close(fig)
# Fig 3: autocorrelation
T = pd.read_csv(f'{OUT}/T1_serial.csv'); T = T[T.spec == 'primary (no replacement)']
fig, ax = plt.subplots(figsize=(6.2, 3.0)); x = np.arange(1, 5)
for o, col, off in [('log L15R', BLUE, -0.07), ('log EVR', ORANGE, 0.07)]:
    d = T[T.outcome == o]; ax.plot(x + off, d.acf, 'o-', color=col, lw=2, ms=6, mec='white', mew=1.2, label=o)
sd = T.null_sd.mean(); ax.axhspan(-1.96 * sd, 1.96 * sd, color=GRID, alpha=0.6, lw=0)
ax.axhline(0, color=INK2, lw=0.8); ax.set_xticks(x); ax.set_xlabel('Lag (number of expiries apart)'); ax.set_ylabel('Autocorrelation of residuals')
ax.set_ylim(-0.25, 0.25); ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True); ax.legend(frameon=False, loc='upper right', fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{REP}/fig3_acf.png', dpi=220); plt.close(fig)
print('ok')
