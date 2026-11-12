"""EditBreak paper figures from results.json (controls must pass first - report.controls).
F4  outcome shares per applier over garbled cases (100% stacked bars; status colours + labels + CI column).
F4b silent-wrong % per applier x channel form (sequential single-hue heatmap, every cell labelled).
usage: python editbreak/figures.py [results/results.json] -> figures/figure4_editbreak, figure5_forms (.png, .svg); any other input file -> figures/<name>_editbreak, <name>_forms
"""
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report as rep                                  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9'
GOOD, NEUTRAL, CRITICAL = '#0ca30c', '#c3c2b7', '#d03b3b'
FORM_LABEL = {'nl_new': 'newlines escaped\n(new only)', 'nl_both': 'newlines escaped\n(old + new)',
              'json_new': 'extra JSON level\n(new only)', 'json_both': 'extra JSON level\n(old + new)',
              'bs_new': 'stray line-end \\\n(new only)', 'bs_both': 'stray line-end \\\n(old + new)'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'text.color': INK, 'axes.edgecolor': GRID,
                     'svg.fonttype': 'none'})


def check_layout(fig, inside=(), pad=3):
    """Computed, not eyeballed: every visible text box (ticks, legend, labels) must not overlap another and must lie
    on the canvas; every (text, bar) pair in `inside` must fit within its bar with `pad` px to spare on every side
    (render check of F1: text exactly touching a border passed bare containment). -> list of problems (empty = clean)."""
    # only texts that are actually DRAWN: findobj also returns tick labels matplotlib creates but never draws (ticks
    # outside the view limits) - control test (b) showed those as false off-canvas hits that masked a real overlap
    drawn, orig = [], matplotlib.text.Text.draw

    def record(self, renderer):
        if self.get_visible() and self.get_text().strip():
            drawn.append(self)
        return orig(self, renderer)
    matplotlib.text.Text.draw = record
    try:
        fig.canvas.draw()
    finally:
        matplotlib.text.Text.draw = orig
    rend = fig.canvas.get_renderer()
    canvas = fig.bbox
    boxes = [(t, t.get_window_extent(rend)) for t in dict.fromkeys(drawn)]
    bad = []
    for t, b in boxes:
        if b.x0 < canvas.x0 - 1 or b.y0 < canvas.y0 - 1 or b.x1 > canvas.x1 + 1 or b.y1 > canvas.y1 + 1:
            bad.append(f'off-canvas: {t.get_text()!r}')
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            if a.x0 < b.x1 - 0.5 and b.x0 < a.x1 - 0.5 and a.y0 < b.y1 - 0.5 and b.y0 < a.y1 - 0.5:
                bad.append(f'overlap: {boxes[i][0].get_text()!r} x {boxes[j][0].get_text()!r}')
    for t, bar in inside:
        tb, bb = t.get_window_extent(rend), bar.get_window_extent(rend)
        if tb.x0 < bb.x0 + pad or tb.x1 > bb.x1 - pad or tb.y0 < bb.y0 + pad or tb.y1 > bb.y1 - pad:
            bad.append(f'label outside its bar: {t.get_text()!r}')
    return bad


def save_checked(fig, out, inside=()):
    """Refuse to write a figure whose layout check fails."""
    bad = check_layout(fig, inside)
    if bad:
        plt.close(fig)
        sys.exit(f'LAYOUT FAIL {os.path.basename(out)}: ' + '; '.join(bad[:10]))
    for ext in ('png', 'svg'):
        fig.savefig(f'{out}.{ext}', facecolor=SURFACE, bbox_inches='tight')
    print(f'{os.path.basename(out)}: layout check PASS (no text overlap, all on canvas, in-bar labels fit)')
    plt.close(fig)


def shares(rows, name, forms):
    n, k, silent = rep.summarize(rows, name, forms)
    return n, k['E'] / n, k['R'] / n, silent / n, silent


def fig_outcomes(res, forms, out):
    rows = res['rows']
    data = []
    for name in rep.appliers(rows):
        n, e, r, s, k = shares(rows, name, forms)
        data.append((name, n, e, r, s, k))
    data.sort(key=lambda d: d[4])                        # most silent corruption at the TOP (barh draws bottom-up)
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=200, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    h = 0.62
    inside = []
    for y, (name, n, e, r, s, k) in enumerate(data):
        left = 0.0
        for share, colour, ink in ((e, GOOD, '#ffffff'), (r, NEUTRAL, INK), (s, CRITICAL, '#ffffff')):
            if share > 0:
                bar = ax.barh(y, share, left=left, height=h, color=colour, edgecolor=SURFACE, linewidth=1.6)[0]
                if share >= 0.075:                        # print inside only where it fits; else table carries it
                    inside.append((ax.text(left + 0.012, y, f'{100 * share:.0f}%', va='center', ha='left',
                                           fontsize=8, color=ink, fontweight='bold'), bar))
            left += share
        lo, hi = rep.wilson(k, n)
        ax.text(1.02, y, f'{100 * s:.1f}%  [{100 * lo:.0f}-{100 * hi:.0f}]', va='center', ha='left', fontsize=8.5,
                color=INK, fontweight='bold' if name == 'rt_ours' else 'normal')
    ax.set_yticks(range(len(data)))
    ax.set_yticklabels([rep.label(d[0]) for d in data], fontsize=8.5, color=INK)
    for lbl, d in zip(ax.get_yticklabels(), data):
        if d[0] == 'rt_ours':
            lbl.set_fontweight('bold')
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(['0%', '25%', '50%', '75%', '100%'], color=MUTED, fontsize=8)
    ax.tick_params(axis='both', length=0)
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    # the CI column header sits right of the axes, the legend stays INSIDE the axes width (render check 1: a legend
    # wider than the plot ran into this header)
    ax.text(1.02, len(data) - 0.5, 'silent [95% CI]', ha='left', va='bottom', fontsize=8, color=INK2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (GOOD, NEUTRAL, CRITICAL)]
    ax.legend(handles, ['exact (as intended)', 'refused (the model is told)', 'silent (accepted, file wrong)'],
              loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.5, handlelength=1.1,
              columnspacing=1.4, borderaxespad=0.3)
    n_cases = data[0][1]
    ax.set_xlabel(f'share of {n_cases} garbled edits per applier ({res["hunks"]} real gold edits x {len(forms)} '
                  f'channel forms)', color=INK2, fontsize=8.5)
    fig.tight_layout()
    save_checked(fig, out, inside)


def fig_forms(res, forms, out):
    rows = res['rows']
    names = sorted(rep.appliers(rows), key=lambda nm: -shares(rows, nm, forms)[3])
    cells = [[shares(rows, nm, {f}) for f in forms] for nm in names]
    grid = [[c[3] for c in row] for row in cells]
    cmap = LinearSegmentedColormap.from_list('red', ['#fbeaea', '#f2b8b5', '#e27b78', '#d03b3b', '#8e1f1f'])
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=200, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=1, aspect='auto')
    for i, row in enumerate(cells):
        for j, (_n, exact, _r, silent, _k) in enumerate(row):
            dark = silent >= 0.5
            ax.text(j, i - 0.13, f'{100 * silent:.0f}%', ha='center', va='center', fontsize=8.5, fontweight='bold',
                    color='#ffffff' if dark else INK)
            # a 0% cell is either "applied exactly" or "refused all": the second line tells them apart
            ax.text(j, i + 0.22, f'exact {100 * exact:.0f}%', ha='center', va='center', fontsize=6.6,
                    color='#ffffff' if dark else INK2)
    ax.set_xticks(range(len(forms)))
    ax.set_xticklabels([FORM_LABEL[f] for f in forms], fontsize=7.8, color=INK)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([rep.label(n) for n in names], fontsize=8.5, color=INK)
    for lbl, n in zip(ax.get_yticklabels(), names):
        if n == 'rt_ours':
            lbl.set_fontweight('bold')
    ax.set_xticks([x - 0.5 for x in range(1, len(forms))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(names))], minor=True)
    ax.grid(which='minor', color=SURFACE, linewidth=2)
    ax.tick_params(axis='both', which='both', length=0)   # render check: minor ticks (the cell gaps) drew stray marks
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title('silent = accepted with a WRONG file (bold); exact = applied as intended (small)', fontsize=9,
                 color=INK, loc='left')
    fig.tight_layout()
    save_checked(fig, out)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(rep.ROOT, 'results', 'results.json')
    res = json.load(open(path, encoding='utf-8'))
    bad = rep.controls(res['rows'])
    if bad:
        sys.exit(f'controls FAIL x{len(bad)} - no figure from an unvalidated instrument')
    forms = [f for f in dict.fromkeys(r['form'] for r in res['rows']) if f != 'clean']
    out = os.path.join(rep.ROOT, 'figures')
    published = os.path.basename(path) == 'results.json'
    stem = '' if published else os.path.splitext(os.path.basename(path))[0] + '_'
    fig_outcomes(res, forms, os.path.join(out, 'figure4_editbreak' if published else stem + 'editbreak'))
    fig_forms(res, forms, os.path.join(out, 'figure5_forms' if published else stem + 'forms'))
    print('figures ->', out)


if __name__ == '__main__':
    main()
