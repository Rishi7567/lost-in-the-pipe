# Third-party material

This repository's own code is Apache-2.0 (see `LICENSE`). It also contains, or downloads, material from other
projects under their own licences. Full licence texts are in `licenses/`.

| What | Where | Source | Licence |
|---|---|---|---|
| Hermes Agent fuzzy matcher, after the escape-drift fix | `vendor/hermes/tools/` | NousResearch/hermes-agent @ 775b9c553627435e71d3c99b4e9cd63ee5469954 | MIT |
| Hermes Agent fuzzy matcher, before the fix | `vendor/hermes_pre/tools/` | NousResearch/hermes-agent @ ddd0cc6944908d2655db2095786ac089a7c3ba0c | MIT |
| Aider SEARCH/REPLACE applier | `vendor/aider_editblock_coder.py` | Aider-AI/aider @ 5dc9490bb35f9729ef2c95d00a19ccd30c26339c | Apache-2.0 |
| DaveCode `repairDoubleEscaped` (ported from TypeScript) | `editbreak/run.py` | DMRLZZ/DaveCode PR 18, merge 403179d2dfd24f0fefe049eee34465517305ec3e | MIT |
| cecelia `repair_escaped_newlines` | downloaded by `vendor/fetch_cecelia.py`, **not redistributed** | schienstockd/cecelia PR 1444, merge 35587b6359b8bbf2fd0d05de99f2baa29080f220 | GPL-3.0 |
| Source-file snapshots the edits apply to | `data/files/` | fastapi/fastapi, psf/requests, Textualize/rich, encode/httpx at each task's base commit (`data/hunks.jsonl`) | MIT, Apache-2.0, MIT, BSD-3-Clause |

The vendored files are unmodified. The Aider applier is loaded by extracting its named top-level functions with
`ast`, because its module imports the whole Aider application.
