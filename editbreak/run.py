"""EditBreak: when the tool channel garbles an edit, does an applier REFUSE it (the model is told) or ACCEPT it and
write a file that is not the intended one (SILENT corruption)?

496 real edits (data/hunks.jsonl, from the public patches of 116 tasks) x 6 channel forms + the clean edit, given to
each applier below. Outcome per (applier, case): E exact | R refused | N accepted but nothing changed |
C silent wrong, still parses | S silent wrong, no longer parses | X the applier crashed.

usage (from the repository root):
    python vendor/fetch_cecelia.py          # once: downloads cecelia's GPL-3.0 file, pinned + hash-checked
    python editbreak/run.py [--workers 4] [--limit N] [--out results/rerun.json]
                            [--only strict,aider,...] [--applier path/to/mine.py:apply[,...]]
Test YOUR applier: a function apply(content, old, new) returning the new file text, or None to refuse
(see examples/my_applier.py). --only skips the slow built-ins; the controls always run.
"""
import ast
import difflib
import json
import math
import os
import re
import sys
import time
import warnings
from difflib import SequenceMatcher
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
VENDOR = os.path.join(ROOT, 'vendor')
PROVENANCE = {
    'aider': 'Aider-AI/aider@5dc9490bb35f9729ef2c95d00a19ccd30c26339c aider/coders/editblock_coder.py (Apache-2.0)',
    'hermes_pre': 'NousResearch/hermes-agent@ddd0cc6944908d2655db2095786ac089a7c3ba0c tools/fuzzy_match.py '
                  '(parent of the PR 128011 merge f42f579; MIT)',
    'hermes': 'NousResearch/hermes-agent@775b9c553627435e71d3c99b4e9cd63ee5469954 tools/fuzzy_match.py + '
              'tools/escape_drift_autocorrect.py (MIT)',
    'davecode': 'DMRLZZ/DaveCode PR 18 merge 403179d2dfd24f0fefe049eee34465517305ec3e '
                'packages/core/src/autonomous/tools.ts repairDoubleEscaped + editFile, ported to Python (MIT)',
    'cecelia': 'schienstockd/cecelia PR 1444 merge 35587b6359b8bbf2fd0d05de99f2baa29080f220 '
               'mcp/cecelia_mcp/agent_text.py (GPL-3.0; downloaded, not redistributed; a rule written for PROSE, '
               'placed here in the str_replace flow)',
}


# ------------------------------------------------------------------------------------------------ data
def load_hunks():
    """-> [(task, path, start, n_old, old_lines, new_lines)] from data/hunks.jsonl."""
    out = []
    for line in open(os.path.join(DATA, 'hunks.jsonl'), encoding='utf-8'):
        h = json.loads(line)
        out.append((h['task'], h['path'], h['start'], h['n_old'], h['old_lines'], h['new_lines']))
    return out


# ------------------------------------------------------------------------------------------------ channel forms
def nl(s):
    return s.replace('\n', '\\n')                          # line breaks escaped one extra time, nothing else


def js(s):
    return json.dumps(s, ensure_ascii=False)[1:-1]         # one full extra JSON escape level


def bs(s):
    return '\n'.join(x + '\\' if k % 2 == 0 and x.strip() else x for k, x in enumerate(s.split('\n')))


FORMS = {'clean': (None, None), 'nl_new': (None, nl), 'nl_both': (nl, nl), 'json_new': (None, js),
         'json_both': (js, js), 'bs_new': (None, bs), 'bs_both': (bs, bs)}


def render(form, old, new):
    fo, fn = FORMS[form]
    return (fo(old) if fo else old), (fn(new) if fn else new)


# ------------------------------------------------------------------------------------------------ helpers
def parses(text):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            ast.parse(text)
            return True
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return False


def same(a, b):
    """Exact, except one uniform rule: a single EOF newline is not a channel effect."""
    return a.removesuffix('\n') == b.removesuffix('\n')


def exact_unique(text, old, new):
    """str_replace: exact, non-overlapping count (str.count = JS countOccurrences), must be unique."""
    n = text.count(old)
    if n != 1:
        return 'refused', f'old matches {n} times'
    i = text.find(old)
    return 'ok', text[:i] + new + text[i + len(old):]


# ------------------------------------------------------------------------------------------------ appliers
def strict(ctx, old, new):
    return exact_unique(ctx['content'], old, new)


def strict_gate(ctx, old, new):
    st, out = strict(ctx, old, new)
    if st == 'ok' and ctx['parses'] and not parses(out):
        return 'refused', 'edit breaks the syntax (lint gate)'
    return st, out


AIDER_FUNCS = ('prep', 'perfect_or_whitespace', 'perfect_replace', 'replace_most_similar_chunk', 'try_dotdotdots',
               'replace_part_with_missing_leading_whitespace', 'match_but_for_leading_whitespace',
               'replace_closest_edit_distance', 'strip_quoted_wrapping', 'do_replace')


def load_aider():
    """The named top-level functions + DEFAULT_FENCE of Aider's editblock_coder.py, extracted by AST and executed
    unmodified (the module itself imports Aider's whole app)."""
    path = os.path.join(VENDOR, 'aider_editblock_coder.py')
    tree = ast.parse(open(path, encoding='utf-8').read())
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in AIDER_FUNCS) or
            (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'DEFAULT_FENCE' for t in n.targets))]
    missing = set(AIDER_FUNCS) - {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    assert not missing and len(keep) == len(AIDER_FUNCS) + 1, f'aider extraction: missing {missing}'
    ns = {'difflib': difflib, 'math': math, 're': re, 'sys': sys, 'SequenceMatcher': SequenceMatcher, 'Path': Path}
    exec(compile(ast.Module(keep, []), path, 'exec'), ns)
    return ns


def make_aider(ns):
    def aider(ctx, old, new):
        # EditBlockCoder.apply_edits: new_content = do_replace(full_path, content, original, updated, self.fence);
        # success iff new_content is truthy. (Its "try the other chat files" fallback has no other file here.)
        try:
            out = ns['do_replace'](ctx['abs'], ctx['content'], old, new, ns['DEFAULT_FENCE'])
        except Exception as e:                            # noqa: BLE001 - any crash = the edit did not apply
            return 'refused', f'{type(e).__name__}: {e}'
        return ('ok', out) if out else ('refused', 'SEARCH block failed to match')
    return aider


def load_hermes(sub):
    """Import vendor/<sub>/tools/fuzzy_match.py as the package `tools` (its own lazy imports say
    `from tools.escape_drift_autocorrect import ...` at call time, so the LAST loaded version stays registered)."""
    for k in [k for k in sys.modules if k == 'tools' or k.startswith('tools.')]:
        del sys.modules[k]
    base = os.path.join(VENDOR, sub)
    sys.path.insert(0, base)
    try:
        import tools.fuzzy_match as fm                    # noqa: PLC0415
        if os.path.exists(os.path.join(base, 'tools', 'escape_drift_autocorrect.py')):
            import tools.escape_drift_autocorrect        # noqa: F401,PLC0415  registered before any call
    finally:
        sys.path.remove(base)
    return fm


def make_hermes(fm):
    def hermes(ctx, old, new):
        try:
            out, count, _strategy, err = fm.fuzzy_find_and_replace(ctx['content'], old, new)
        except Exception as e:                            # noqa: BLE001
            return 'refused', f'{type(e).__name__}: {e}'
        if err or not count:
            return 'refused', err or 'no match'
        return 'ok', out
    return hermes


def repair_double_escaped(text):
    """DaveCode PR 18 repairDoubleEscaped (TypeScript, MIT), ported line for line."""
    if '\n' in text or not re.search(r'\\[nt]', text):
        return text
    out, quote, i = [], None, 0
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else None
        if char == '\\' and nxt is not None:
            if quote is None and nxt in ('n', 't'):
                out.append('\n' if nxt == 'n' else '\t')
            else:
                out.append(char + nxt)
            i += 2
            continue
        if quote is None and char in ('"', "'", '`'):
            quote = char
        elif char == quote:
            quote = None
        out.append(char)
        i += 1
    return ''.join(out)


def make_repair_flow(repair):
    """DaveCode editFile: repair new_string always; after a miss repair old_string and recount; exact + unique.
    (Its CRLF retry never fires here: contents are LF.)"""
    def flow(ctx, old, new):
        text = ctx['content']
        new = repair(new)
        if text.count(old) == 0:
            repaired = repair(old)
            if repaired != old:
                old = repaired
        return exact_unique(text, old, new)
    return flow


def load_cecelia():
    path = os.path.join(VENDOR, 'cecelia_agent_text.py')
    if not os.path.exists(path):
        sys.exit('vendor/cecelia_agent_text.py is missing: run  python vendor/fetch_cecelia.py  first')
    import importlib.util                                  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location('cecelia_agent_text', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return lambda s: mod.repair_escaped_newlines(s)[0]


def naive(ctx, old, new):
    """The common hand fix (a BASELINE, not a project): on a miss, decode literal \\n and \\t in both strings."""
    text = ctx['content']
    if text.count(old) == 0:
        old, new = (s.replace('\\n', '\n').replace('\\t', '\t') for s in (old, new))
    return exact_unique(text, old, new)


def plant(ctx, old, new):
    """CONTROL: a correct applier that writes one wrong character -> every acceptance must score silent."""
    return strict(ctx, old, (new[:-1] + chr(ord(new[-1]) ^ 1)) if new else 'x')


def refuse_all(ctx, old, new):
    """CONTROL: must score 100% refused."""
    return 'refused', 'control'


# built-in appliers in BUILD order (hermes_pre before hermes: see load_hermes); built lazily, so --only stays fast
BUILTIN = {
    'strict': lambda: strict,
    'strict_gate': lambda: strict_gate,
    'aider': lambda: make_aider(load_aider()),
    'hermes_pre': lambda: make_hermes(load_hermes('hermes_pre')),
    'hermes': lambda: make_hermes(load_hermes('hermes')),
    'davecode': lambda: make_repair_flow(repair_double_escaped),
    'cecelia': lambda: make_repair_flow(load_cecelia()),
    'naive': lambda: naive,
    'ctl_plant': lambda: plant,
    'ctl_refuse': lambda: refuse_all,
}
REQUIRED = ('strict', 'ctl_plant', 'ctl_refuse')          # report.py's instrument controls need these in every run


def load_external(spec):
    """'path/to/file.py:function' -> (name, applier). The function takes (content, old, new) and returns the new file
    text, or None to refuse; an exception counts as a crash (X), never as a refusal."""
    import importlib.util                                  # noqa: PLC0415
    path, func = spec.rsplit(':', 1)
    path = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    name = f'{os.path.splitext(os.path.basename(path))[0]}.{func}'
    mod_spec = importlib.util.spec_from_file_location(name.replace('.', '_'), path)
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    fn = getattr(mod, func)

    def external(ctx, old, new):
        out = fn(ctx['content'], old, new)
        return ('refused', 'returned None') if out is None else ('ok', out)
    return name, external


def build_appliers(only=None, externals=()):
    """only: built-in names to run (None = all); the REQUIRED controls always run. externals: --applier specs."""
    out = {n: make() for n, make in BUILTIN.items() if only is None or n in only or n in REQUIRED}
    for spec in externals:
        name, fn = load_external(spec)
        out[name] = fn
    return out


# ------------------------------------------------------------------------------------------------ run
def classify(st, out, ctx):
    if st != 'ok':
        return 'R'
    if same(out, ctx['E']):
        return 'E'
    if same(out, ctx['content']):
        return 'N'
    return 'C' if parses(out) else 'S'


def hunk_ctx(task, path, start, n_old, new):
    abs_path = os.path.join(DATA, 'files', task, *path.split('/'))
    raw = open(abs_path, encoding='utf-8', newline='').read().replace('\r\n', '\n')
    lines = raw.split('\n')
    exp = lines[:start - 1] + new + lines[start - 1 + n_old:]
    return {'path': path, 'abs': abs_path, 'content': raw, 'E': '\n'.join(exp), 'parses': parses(raw)}


def worker(job):
    wid, hunks, only, externals = job
    appliers = build_appliers(only, externals)
    rows, examples, secs = [], {}, {a: 0.0 for a in appliers}
    t_start = time.time()
    for done, (task, path, start, n_old, old_l, new_l) in enumerate(hunks):
        if done % 25 == 0:
            print(f'  [w{wid}] {done}/{len(hunks)} hunks, {time.time() - t_start:.0f} s', flush=True)
        ctx = hunk_ctx(task, path, start, n_old, new_l)
        if not ctx['E'].strip():
            continue                                       # a whole-file deletion is not an str_replace edit
        old, new = '\n'.join(old_l), '\n'.join(new_l)
        for form in FORMS:
            o2, n2 = render(form, old, new)
            if form != 'clean' and (o2, n2) == (old, new):
                continue                                   # the form changes nothing: a duplicate of clean
            out = {}
            for name, fn in appliers.items():
                t0 = time.perf_counter()
                try:
                    st, res = fn(ctx, o2, n2)
                    out[name] = classify(st, res, ctx)
                except Exception as e:                    # noqa: BLE001 - an applier CRASH: counted, never hidden
                    res, out[name] = f'{type(e).__name__}: {e}', 'X'
                    examples.setdefault(f'{name}|CRASH', []).append({'task': task, 'path': path, 'start': start,
                                                                    'form': form, 'error': res[:300]})
                secs[name] += time.perf_counter() - t0
                if out[name] in 'NCS' and len(examples.setdefault(f'{name}|{form}', [])) < 4:
                    diff = list(difflib.unified_diff(ctx['E'].split('\n'), res.split('\n'), 'expected', name,
                                                     n=1, lineterm=''))
                    examples[f'{name}|{form}'].append({'task': task, 'path': path, 'start': start,
                                                       'diff': diff[:24]})
            rows.append({'task': task, 'path': path, 'start': start, 'form': form, 'out': out,
                         'unique': ctx['content'].count(old) == 1, 'backslash': '\\' in old + new})
    return rows, examples, secs


def main():
    import multiprocessing                                 # noqa: PLC0415
    args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    workers = int(args.get('--workers', 4))
    out_arg = args.get('--out', os.path.join('results', 'rerun.json'))
    out = os.path.join(ROOT, out_arg)                       # an absolute --out stays absolute
    only = set(args['--only'].split(',')) if '--only' in args else None
    unknown = (only or set()) - set(BUILTIN)
    if unknown:
        sys.exit(f'unknown --only applier(s) {sorted(unknown)}; built-ins: {", ".join(BUILTIN)}')
    externals = [s for s in args.get('--applier', '').split(',') if s]
    hunks = load_hunks()
    if int(args.get('--limit', 0)):
        hunks = hunks[:int(args['--limit'])]
    build_appliers(only, externals)                        # fail fast (a missing cecelia file, a bad --applier)
    t0 = time.time()
    with multiprocessing.Pool(workers) as pool:
        parts = pool.map(worker, [(w, hunks[w::workers], only, externals) for w in range(workers)])
    rows = [r for p in parts for r in p[0]]
    examples, secs = {}, {}
    for _, ex, sc in parts:
        for k, v in ex.items():
            examples.setdefault(k, []).extend(v)
        for k, v in sc.items():
            secs[k] = secs.get(k, 0.0) + v
    names = list(rows[0]['out'])
    table = {name: {form: {k: [r['out'][name] for r in rows if r['form'] == form].count(k) for k in 'ERNCSX'} |
                    {'n': sum(1 for r in rows if r['form'] == form)} for form in FORMS} for name in names}
    result = {'hunks': len(hunks), 'cases': len(rows), 'seconds': round(time.time() - t0, 1),
              'applier_seconds': {k: round(v, 1) for k, v in secs.items()}, 'provenance': PROVENANCE,
              'table': table, 'examples': examples, 'rows': rows}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(result, open(out, 'w', encoding='utf-8'), indent=1)
    print(f'{len(hunks)} hunks -> {len(rows)} cases in {result["seconds"]} s -> {out}')
    print('next:  python editbreak/report.py', out_arg)    # not relpath: it raises across Windows drives


if __name__ == '__main__':
    main()
