"""Download cecelia's escaped-newline repair (GPL-3.0) at its pinned merge commit into vendor/, verifying its MD5.
It is fetched rather than redistributed because this repository is Apache-2.0.
usage: python vendor/fetch_cecelia.py
"""
import hashlib
import os
import urllib.request

COMMIT = '35587b6359b8bbf2fd0d05de99f2baa29080f220'           # schienstockd/cecelia PR 1444 merge
URL = f'https://raw.githubusercontent.com/schienstockd/cecelia/{COMMIT}/mcp/cecelia_mcp/agent_text.py'
MD5 = 'eda3b506f1bca4b610d340c7e707b36f'
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cecelia_agent_text.py')


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        body = r.read()
    got = hashlib.md5(body).hexdigest()
    if got != MD5:
        raise SystemExit(f'MD5 mismatch: expected {MD5}, got {got} - not written')
    with open(DEST, 'wb') as f:
        f.write(body)
    print(f'ok: {DEST} (md5 {got})')


if __name__ == '__main__':
    main()
