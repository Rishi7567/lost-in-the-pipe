"""A template for testing YOUR edit applier with EditBreak.

Write a function that takes the file's text, the text to replace, and the replacement, and returns the new file text,
or None to refuse the edit. Then run, from the repository root:

    python editbreak/run.py --only strict --applier examples/my_applier.py:apply --limit 40 --out results/mine.json
    python editbreak/report.py results/mine.json

This example is plain str_replace (exact and unique), so its outcomes must equal the built-in `strict` on every case:
a quick check that your plug-in path works before you try your own logic.
"""


def apply(content, old, new):
    if content.count(old) != 1:
        return None                     # missing or ambiguous: refuse, so the model is told
    i = content.find(old)
    return content[:i] + new + content[i + len(old):]
