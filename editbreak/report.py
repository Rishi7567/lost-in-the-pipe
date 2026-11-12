"""EditBreak report: the instrument controls first, then the table. Nothing is printed if a control fails.
Works on the published run (results/results.json, which includes the author's editor rt) and on a rerun.
usage: python editbreak/report.py [results/results.json]
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ['strict', 'strict_gate', 'aider', 'hermes_pre', 'hermes', 'davecode', 'cecelia', 'naive', 'rt_orig',
         'rt_ours']
LABEL = {'strict': 'str_replace (exact, unique)', 'strict_gate': 'str_replace + syntax gate',
         'aider': 'Aider SEARCH/REPLACE', 'hermes_pre': 'Hermes, before PR 128011', 'hermes': 'Hermes, today',
         'davecode': 'DaveCode repairDoubleEscaped', 'cecelia': 'cecelia newline rule', 'naive': 'naive unescape',
         'rt_orig': 'rt before S1 (ours, old)', 'rt_ours': 'rt after S1 (ours)'}


def wilson(k, n, z=1.96):
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def controls(rows):
    """V1 strict is exact on every unique clean edit and refuses every ambiguous one; V2 the planted-error applier is
    silent exactly where strict accepts; V3 the refuse-all applier refuses everything. -> failures (empty = valid)."""
    bad = []
    for r in rows:
        if r['form'] == 'clean':
            s, p = r['out']['strict'], r['out']['ctl_plant']
            if r['unique'] and s != 'E':
                bad.append(f"V1 strict not exact on a unique clean case {r['task']} {r['path']}:{r['start']} -> {s}")
            if not r['unique'] and s != 'R':
                bad.append(f"V1 strict accepted a non-unique old {r['task']} {r['path']}:{r['start']} -> {s}")
            if (s == 'E') != (p in 'NCS'):
                bad.append(f"V2 plant/strict acceptance differ {r['task']} {r['path']}:{r['start']}")
        if r['out']['ctl_refuse'] != 'R':
            bad.append(f"V3 refuse-all scored {r['out']['ctl_refuse']}")
    return bad


def summarize(rows, name, forms):
    sel = [r['out'][name] for r in rows if r['form'] in forms]
    k = {c: sel.count(c) for c in 'ERNCSX'}
    return len(sel), k, k['N'] + k['C'] + k['S']


def pct(k, n):
    return f'{100 * k / n:.1f}' if n else '-'


def appliers(rows):
    return [a for a in ORDER if a in rows[0]['out']]


def garbled_forms(rows):
    return [f for f in dict.fromkeys(r['form'] for r in rows) if f != 'clean']


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'results', 'results.json')
    res = json.load(open(path, encoding='utf-8'))
    rows = res['rows']
    bad = controls(rows)
    print(f'{res["hunks"]} hunks, {res["cases"]} cases; controls: {"PASS" if not bad else f"FAIL x{len(bad)}"}')
    for b in bad[:20]:
        print('  ', b)
    if bad:
        sys.exit(1)
    forms = garbled_forms(rows)
    out = ['| applier | garbled n | exact % | refused % | SILENT wrong % [95% CI] | clean exact % | '
           'clean silent | crashes |', '|---|---|---|---|---|---|---|---|']
    for name in appliers(rows):
        n, k, silent = summarize(rows, name, forms)
        lo, hi = wilson(silent, n)
        cn, ck, csil = summarize(rows, name, {'clean'})
        crashes = sum(1 for r in rows if r['out'][name] == 'X')
        out.append(f'| {LABEL[name]} | {n} | {pct(k["E"], n)} | {pct(k["R"], n)} | **{pct(silent, n)}** '
                   f'[{100 * lo:.1f}-{100 * hi:.1f}] | {pct(ck["E"], cn)} | {csil} | {crashes} |')
    out += ['', '| applier | ' + ' | '.join(forms) + ' |', '|---|' + '---|' * len(forms)]
    for name in appliers(rows):
        cells = []
        for f in forms:
            _n, k, silent = summarize(rows, name, {f})
            cells.append(f'{k["E"]}/{k["R"]}/**{silent}**')
        out.append(f'| {LABEL[name]} | ' + ' | '.join(cells) + ' |')
    out.append('\ncells = exact / refused / **silent wrong** (accepted, file != the intended file).')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
