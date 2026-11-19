import sys, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT = sys.argv[1]
BLUE, ORANGE = '#2a78d6', '#eb6834'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'text.color': INK, 'axes.spines.top': False, 'axes.spines.right': False})

# ---- Fig 1: signed price path after a large late move ----
pe = pd.read_csv(f'{OUT}/path_expiry.csv', index_col=0); pn = pd.read_csv(f'{OUT}/path_nonexpiry.csv', index_col=0)
labels = ['15:15\n(start of\nlast bar)', 'Close\n15:30', 'Next\nopen', 'Next\n11:15', 'Next\n13:15', 'Next\nclose', '+2d\nclose', '+5d\nclose']
x = np.arange(len(labels))
fig, ax = plt.subplots(figsize=(6.6, 3.5))
for df, col, nm in [(pn, ORANGE, 'Non-expiry days (n=157)'), (pe, BLUE, 'Expiry days (n=66)')]:
    m, se = df['mean'].values, df['se'].values
    ax.fill_between(x, m - 1.96 * se, m + 1.96 * se, color=col, alpha=0.12, lw=0)
    ax.plot(x, m, color=col, lw=2, marker='o', ms=5, mfc=col, mec='white', mew=1.2, label=nm)
ax.axhline(0, color=GRID, lw=1); ax.axhline(pe['mean'].iloc[1], color=INK2, lw=0.8, ls=(0, (3, 3)))
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7.5)
ax.set_ylabel('Cumulative move in direction of\nthe late move (bps)')
ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.legend(frameon=False, loc='upper left', fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{OUT}/fig1_path.png', dpi=220); plt.close(fig)

# ---- Fig 2: forest of primary test + placebos ----
P = pd.read_csv(f'{OUT}/primary_sign_matched.csv'); PL = pd.read_csv(f'{OUT}/placebo_signmatched.csv')
keep = ['All expiries', 'Weekly only', 'Monthly', 'Late move up', 'Late move down', '2019-22', '2023-26', 'All, excl. 2020']
rows = [(r.group + f'  (n={r.n})', r.diff_pp, r.lo, r.hi, 'exp') for r in P.set_index('group').loc[keep].reset_index().itertuples()]
rows += [(r.placebo.replace(' (Thursday era)', '').replace(' treated as expiry', '').replace('Non-expiry Thursday (Tuesday era)', 'Thursday, Tuesday era') + f' [placebo]  (n={r.n})', r.diff_pp, r.lo, r.hi, 'plc') for r in PL.itertuples()]
fig, ax = plt.subplots(figsize=(6.6, 4.6))
ypos = np.arange(len(rows))[::-1]
gap_after = 8  # visual gap before placebos
ypos = np.array([y - (1.0 if k == 'plc' else 0) for y, (_, _, _, _, k) in zip(ypos, rows)])
for y, (lab, m, lo, hi, k) in zip(ypos, rows):
    col = BLUE if k == 'exp' else ORANGE
    ax.plot([lo, hi], [y, y], color=col, lw=2, solid_capstyle='round')
    ax.plot(m, y, 'o', ms=6, color=col, mec='white', mew=1.2)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks(ypos); ax.set_yticklabels([r[0] for r in rows], fontsize=7.5)
ax.set_xlabel('Reversal probability at next open: expiry minus matched days (pp)\n← less reversal (more continuation)      more reversal →', fontsize=7.5)
ax.grid(axis='x', color=GRID, lw=0.8); ax.set_axisbelow(True)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([0], [0], color=BLUE, lw=2, marker='o', ms=5, label='Expiry sessions'),
                   Line2D([0], [0], color=ORANGE, lw=2, marker='o', ms=5, label='Placebo (non-expiry days labelled as expiry)')],
          frameon=False, loc='lower center', bbox_to_anchor=(0.45, 1.0), ncol=2, fontsize=7.5)
fig.tight_layout(); fig.savefig(f'{OUT}/fig2_forest.png', dpi=220); plt.close(fig)
print('ok')
