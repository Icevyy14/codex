# Web pages

Three standalone pages. GitHub shows HTML as source code, so **download a file and open it in a browser**. Each page needs an internet connection for its fonts, and the 3D model also needs one for its 3D library.

| File | What it is |
|---|---|
| `slabrail.html` | One-page overview: what the machine does, what is proven and what isn't, cost, layout and the build plan |
| `slabrail_3d.html` | Interactive 3D model of the whole machine, generated from the CAD. Rotate, zoom, click a part to see what it is, hide groups of parts. |
| `slabrail_replay.html` | Animated replay of a simulated 330-slab batch, timed by the simulator's motion model and run by the real machine software. The labels are synthetic. |

The overview page shows the state on 23 Oct 2026. For anything that disagrees with it, the docs win, starting with [docs/REVIEWER_BRIEF.md](../docs/REVIEWER_BRIEF.md).

## Rebuilding

The sources are in `src/`. Run these from `psa-slab-scanner/`.

- **Overview:**
  ```
  python3 web/src/overview/build_page.py TESTS SCHOOL SEC_PER_SLAB RUN_TIME
  python3 web/src/pages.py overview
  ```
  The arguments are the test-count text, the school-stock cost, the seconds per slab and the batch time. All four come from the latest runs in [docs/DESIGN.md](../docs/DESIGN.md) §6.
- **3D model:**
  ```
  cd cad && PYTHONPATH=. python3 ../web/src/viewer/export_meshes.py /tmp/mesh carry && cd ..
  python3 web/src/pages.py viewer /tmp/mesh
  ```
- **Replay:**
  ```
  python3 web/src/replay/record.py software 330 /tmp/replay
  python3 web/src/pages.py replay /tmp/replay
  ```
