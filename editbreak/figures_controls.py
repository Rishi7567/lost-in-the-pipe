"""Control tests of figures.check_layout: each planted defect must be caught BY THE RIGHT CHECK."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figures as ef
import report as rep
import matplotlib.pyplot as plt


def legend_fig(labels, header_y_offset):
    """The real F4 geometry: 10 bars, the real applier names on the y axis, a 3-column legend above, a CI header."""
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=200)
    for y in range(10):
        ax.barh(y, 1.0, height=0.62)
    ax.set_yticks(range(10))
    ax.set_yticklabels([rep.LABEL[n] for n in rep.ORDER], fontsize=8.5)
    ax.set_xlim(0, 1)
    ax.text(1.02, 10 - header_y_offset, 'silently wrong\n[95% CI]' if header_y_offset < 0.5 else 'silent [95% CI]',
            ha='left', va='bottom', fontsize=8)
    hs = [plt.Rectangle((0, 0), 1, 1) for _ in range(3)]
    ax.legend(hs, labels, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.5,
              handlelength=1.1, columnspacing=1.6)
    fig.tight_layout()
    return fig


cases = []
fig, ax = plt.subplots(figsize=(4, 3))
ax.text(0.5, 0.5, 'first label here')
ax.text(0.52, 0.5, 'second label')
cases.append(('a planted overlap', ef.check_layout(fig), 'overlap'))
plt.close(fig)
fig = legend_fig(['applied exactly as intended', 'refused (the model is told)',
                  'accepted but the file is wrong (silent)'], 0.35)
cases.append(('b the REAL earlier legend defect', ef.check_layout(fig), "x 'accepted but the file is wrong"))
plt.close(fig)
fig, ax = plt.subplots(figsize=(4, 2))
bar = ax.barh(0, 0.05, height=0.6)[0]
ax.set_xlim(0, 1)
t = ax.text(0.005, 0, '100%', va='center', fontsize=9)
cases.append(('c label wider than its bar', ef.check_layout(fig, [(t, bar)]), 'label outside its bar'))
plt.close(fig)
fig, ax = plt.subplots(figsize=(4, 3))
ax.text(1.3, 0.5, 'far right, off the canvas')
cases.append(('e text off the canvas', ef.check_layout(fig), 'off-canvas'))
plt.close(fig)
fig = legend_fig(['exact (as intended)', 'refused (the model is told)', 'silent (accepted, file wrong)'], 0.5)
cases.append(('d the FIXED legend (must pass)', ef.check_layout(fig), None))
plt.close(fig)
ok_all = True
for name, probs, expect in cases:
    ok = (not probs) if expect is None else any(expect in p for p in probs)   # the planted defect, by its own check
    ok_all &= ok
    print(f'{"OK  " if ok else "MISS"} {name}: {probs[:3]}')
print('ALL CONTROLS OK' if ok_all else 'CONTROL FAILURE')
