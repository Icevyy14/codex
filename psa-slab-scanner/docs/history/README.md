# Design history

Working reports from the design rounds, kept as a record of what was found and changed and why. **They are not the current design.** Numbers in them were right on the day they were written and many have since changed. The current values are in the code (`cad/layout.py`, `software/slabscan/config.py`), [DESIGN.md](../DESIGN.md) and [REVIEWER_BRIEF.md](../REVIEWER_BRIEF.md).

Each round followed the same pattern: build, verify independently, fix what the verification found, then update the docs. Paths that pointed into the working area outside the repo now read `scratch/...`. Those files (simulator outputs, image sets) are not in the repo.

| Folder | What it covers |
|---|---|
| `round2/` | Cup and spring-buffer research, the second CAD head, the first face-down check and its fixes |
| `round3/` | CAD rebuild and check totals, software build, integration, two independent verifications and their fixes |
| `round4/` | CAD and software builds, verification, fixes, and a full walkthrough of the build guide as a first-time builder would read it |
| `round5/` | Final CAD, software and docs rounds: home switches, LED ring seats, the 8-digit ITF rule, and the fixes they needed |
| `real_eval/` | The decoding rules run on public scans of 64 real PSA, CGC, BGS and SGC slabs (`EVAL_REPORT.md`), an independent check of that report's claims (`CHECK_VERDICT.md`), and the per-image tables. The scans themselves are not included: they are copyrighted images from the graders' sites. |
| `sourcing/links.json` | The raw sourcing data behind [SHOPPING_LIST.md](../SHOPPING_LIST.md): every link, price, pack size and how each was checked |
