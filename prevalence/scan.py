"""Prevalence of escape drift in PUBLIC agent trajectories of a different model and harness:
nebius/SWE-rebench-openhands-trajectories (Qwen3-Coder-480B + OpenHands v0.54.0, 67,074 trajectories, CC-BY-4.0).

For every str_replace_editor call (str_replace / create), the detector flags NEWLINE DRIFT:
  new_only : old_str has real line breaks, new_str has none and carries >= 2 literal backslash-n pairs
  both     : old_str and new_str both have no real line break and each carries >= 2 literal backslash-n pairs
  create   : file_text has no real line break and carries >= 2 literal backslash-n pairs
and reads the harness's own reply to the call: applied (the drift was WRITTEN, silently) or refused.

The detector is validated first on EditBreak's known edits (validate()): false positives on the clean edits, recall
on the damaged forms. usage:
  python prevalence/scan.py validate
  python prevalence/scan.py scan path/to/trajectories.parquet [--max-rows N]
The parquet (2.1 GB) is at https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories (CC-BY-4.0).
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                               # the repository root
LIT = '\\n'                                                # the 2-character escape: a backslash then n


def drift(old, new):
    """-> 'new_only' | 'both' | None for one str_replace call."""
    if '\n' not in new and new.count(LIT) >= 2:
        if '\n' in old:
            return 'new_only'
        if old.count(LIT) >= 2:
            return 'both'
    return None


def drift_create(text):
    return 'create' if '\n' not in text and text.count(LIT) >= 2 else None


def validate():
    """FP on clean EditBreak edits; recall on the newline-drift forms of the same edits (multi-line new texts)."""
    sys.path.insert(0, os.path.join(ROOT, 'editbreak'))
    import run as eb                                       # noqa: PLC0415  the published EditBreak forms
    fp = n_clean = hit_new = n_new = hit_both = n_both = 0
    for _task, _path, _start, _n_old, old_l, new_l in eb.load_hunks():
        old, new = '\n'.join(old_l), '\n'.join(new_l)
        n_clean += 1
        fp += drift(old, new) is not None
        if new.count('\n') >= 2:                            # >= 2 literal pairs after drift needs >= 3 lines
            for form, (o2, n2) in (('nl_new', eb.render('nl_new', old, new)), ('json_new', eb.render('json_new', old, new))):
                n_new += 1
                hit_new += drift(o2, n2) == 'new_only'
            if old.count('\n') >= 2:
                o2, n2 = eb.render('nl_both', old, new)
                n_both += 1
                hit_both += drift(o2, n2) == 'both'
    print(f'clean edits: {n_clean}, false positives: {fp}')
    print(f'new-only drift (nl_new + json_new): recall {hit_new}/{n_new}')
    print(f'both-strings drift (nl_both): recall {hit_both}/{n_both}')
    return fp, n_clean


def verdict(obs):
    """OpenHands' reply to a str_replace_editor call -> 'applied' | 'refused' | 'other'."""
    if not obs:
        return 'other'
    if 'has been edited' in obs or 'File created successfully' in obs:
        return 'applied'
    if 'No replacement was performed' in obs or 'did not appear verbatim' in obs or obs.lstrip().startswith('ERROR'):
        return 'refused'
    return 'other'


def scan(path, max_rows=None):
    import pyarrow.parquet as pq                           # noqa: PLC0415
    pf = pq.ParquetFile(path)
    cols = [c for c in ('instance_id', 'trajectory', 'resolved') if c in pf.schema_arrow.names]
    stats = {'trajectories': 0, 'edit_calls': 0, 'str_replace': 0, 'create': 0, 'flagged': {},
             'trajectories_with_drift': 0, 'resolved_with_drift': 0}
    examples, t0 = [], time.time()
    for batch in pf.iter_batches(batch_size=200, columns=cols):
        for row in batch.to_pylist():
            stats['trajectories'] += 1
            obs_by_id, calls = {}, []
            for msg in row['trajectory'] or []:
                if msg.get('role') == 'tool' and msg.get('tool_call_id'):
                    obs_by_id[msg['tool_call_id']] = msg.get('content') or ''
                for tc in (msg.get('tool_calls') or []) if msg.get('role') == 'assistant' else []:
                    fn = tc.get('function') or {}
                    if fn.get('name') == 'str_replace_editor':
                        calls.append((tc.get('id'), fn.get('arguments')))
            had = False
            for cid, raw in calls:
                try:
                    args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except ValueError:
                    continue
                cmd = args.get('command')
                if cmd == 'str_replace':
                    stats['str_replace'] += 1
                    kind = drift(args.get('old_str') or '', args.get('new_str') or '')
                elif cmd == 'create':
                    stats['create'] += 1
                    kind = drift_create(args.get('file_text') or '')
                else:
                    continue
                stats['edit_calls'] += 1
                if kind:
                    had = True
                    v = verdict(obs_by_id.get(cid))
                    key = f'{kind}|{v}'
                    stats['flagged'][key] = stats['flagged'].get(key, 0) + 1
                    if len(examples) < 500:                 # keep EVERY flagged call for the audit
                        examples.append({'instance': row.get('instance_id'), 'kind': kind, 'verdict': v,
                                         'path': args.get('path'), 'old': (args.get('old_str') or '')[:300],
                                         'new': (args.get('new_str') or args.get('file_text') or '')[:300],
                                         'obs': (obs_by_id.get(cid) or '')[:200]})
            stats['trajectories_with_drift'] += had
            stats['resolved_with_drift'] += bool(had and row.get('resolved'))
            if max_rows and stats['trajectories'] >= max_rows:
                break
        print(f"  {stats['trajectories']} trajectories, {stats['edit_calls']} edit calls, flagged "
              f"{sum(stats['flagged'].values())}, {time.time() - t0:.0f} s", flush=True)
        if max_rows and stats['trajectories'] >= max_rows:
            break
    out = os.path.join(ROOT, 'results', 'prevalence_rerun.json')
    json.dump({'stats': stats, 'examples': examples}, open(out, 'w', encoding='utf-8'), indent=1)
    print(json.dumps(stats, indent=1))
    print('->', out)


def main():
    if sys.argv[1] == 'validate':
        validate()
    else:
        mr = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
        scan(sys.argv[2], mr)


if __name__ == '__main__':
    main()
