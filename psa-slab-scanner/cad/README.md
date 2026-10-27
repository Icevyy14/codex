# SlabRail CAD

Parametric CadQuery model of the whole machine. `layout.py` holds the master dimensions. The model, the exports, the
drawings, the geometry checks and the machine software's config all read from it. Everything in `out/` is generated:
change the Python, then regenerate. Do not edit the exports by hand.

Nothing has been built yet. The model is checked against itself (177 geometry checks, below), not against real parts.

Paths below are relative to this `cad/` folder. In `SlabRail_CAD.zip` that folder is `SlabRail_CAD/cad/`, and this file is
also copied to the top of the zip.

## Units

- Millimetres everywhere: the Python, the STEP, STL and DXF files, `print_list.json` and `cut_list.csv`.
  Volumes in `print_list.json` are cm³.
- The STEP files are AP214 (`AUTOMOTIVE_DESIGN`), written by Open CASCADE. The DXF declares millimetres
  (`$INSUNITS` 4).
- The GLB files are the only exception. glTF expects metres and +Y up, so their root node scales by 0.001 and turns the
  model Z-up to Y-up. The mesh data inside is still CAD millimetres on the CAD axes (see `export_glb.py`).

## Coordinate system and origin

Taken from `layout.py` and confirmed by measuring the model:

| Axis | Direction | Zero |
|---|---|---|
| X | Left to right along the pocket row (the gantry beam's direction). | The left interior edge of cell 0, which is the inside surface of the leftmost guide rods (`rod_00` spans X −8 to 0). |
| Y | Front (−) to back (+). The operator stands at −Y; slab labels point to −Y. | The pocket row's centre line, which is also the cup's fixed Y. There is no Y axis. |
| Z | Up. | **The top surface of the pocket floor pads.** |

Reference heights and positions, measured on the model:

- Pad top Z 0, bed (plywood) top Z −3, bed underside −21, base-rail underside −41, feet bottom −49.
- The 14 cells are 92 mm apart (84 mm pocket + 8 mm wall line). Cell 7 is the read station (X 686, no pocket), so pocket
  0 is at X 42, pocket 6 at 594, pocket 7 at 778, and pocket 12, the exception pocket, at 1238.
- The X beam's front face (the rail mounting face) is at Y 107, and its centre is at Z 400.
- Machine coordinates use the same frame. **Machine X** is the X of the suction-cup axis. **c** (machine Z) is the height
  of the cup face above Z 0. In the `home` assembly the cup face is at Z 248, which is c = 248.
- Overall envelope in every pose: X −78 to 1358, Y −117.5 to 172, Z −49 to 671. The frame and the Z motor set it. The Z
  motor rides on the X carriage but does not move in Z.

## Poses

`build.POSES` defines four assembly poses. Each one is a call to `model.machine(cup_x, c, held_slab, fill)`.
"Full" means 30 slabs (`STACK_MAX`).

| Pose | Cup X | c | Slab on the cup | Stacks | What it shows |
|---|---|---|---|---|---|
| `home` | 134 (pocket 1) | 248 (`C_SAFE_EMPTY`, travel height) | no | start of a run: pockets 1–11 full, 0 and 12 empty | The machine as loaded. This is not the homing position: the X home switch trips at cup X 19 and the Z top switch at c = 258. |
| `pick_bottom` | 1146 (pocket 11) | 6.6 (one slab, `SLAB_T`) | no | pockets 1–10 full, pocket 11 holds 1, 0 and 12 empty | The lowest pick: the cup on the last slab of a pocket between full neighbours. |
| `carry` | 88 (between pocket 0 at 42 and pocket 1 at 134) | 248 (`C_SAFE_LOADED`) | yes | pocket 0 holds 12, pocket 1 holds 17, pockets 2–11 full | Loaded travel over the rods. |
| `station` | 686 (station, cell 7) | 171.6 (`STATION_READ_C`) | yes | pockets 0–2 full, pocket 3 holds 12, pocket 4 empty, pockets 5–11 full | Reading the slab's front label over the upward camera. The slab's front is 140 mm above the station lens. |

With nothing pressing on it, the cup hangs 2 mm (`CUP_HANG`) below c. A held slab's underside is therefore at
c − 2 − 6.6. `checks.py` uses many more poses than these four: every pick, place, travel height, hard stop and the
Phase 0 jig.

## Part names

Every part in an assembly is a `model.Part` with a `name`, `color`, `kind` (below) and `group`. The group is `static`,
`carriage` (moves in X) or `head` (moves in X and Z). In the assembly STEP each part is one named, coloured product. In the
GLB each part is one named mesh, with kind, group and note in the node's glTF `extras`.

- Subsystem prefixes: `x_` is the X axis (beam, rail, carriage, motor, idler, belt, switch, bracket) and `z_` is the Z axis
  (spine, rail, carriage, motor, lead screw, plate, end cap, switch).
- `_L` / `_R` mean the left (−X) and right (+X) side.
- Numbered parts: `pad_N`, `stack_N` and `labels_N` are pocket N (0–12). `rod_00`…`rod_81` are the 82 guide rods.
  `base_rail_0`/`_1` are the two base rails.
- Fastener heads (63 of them) are named by group: `fx_…` static (18), `fc_…` on the carriage (31), `fh_…` on the head (10),
  plus the probe board's `probe_m3…` and `probe_nut…` (4). Only heads that could foul another part are modelled. In the
  GLB they are merged into one mesh, `fasteners`, whose extras list the 63 names.
- `held_slab` and `held_label` are the slab on the cup, in the `carry` and `station` poses.
- Counts: 239 parts in `home` and `pick_bottom`, 243 in `carry`, 241 in `station`.

Printed parts have the same name in the assembly and in `out/printed/`, with three exceptions:

- `station` in the assembly is `station_mount` in the files.
- `belt_clamp_L` and `belt_clamp_R` are two prints of `belt_clamp`.
- Some files are not in the machine assemblies: the build and loading tools (`awl_adapter`, `drill_template`,
  `fill_gauge`) and the Phase 0 test jig (`phase0_base`, `phase0_occluder_mount`, `phase0_top`, `phase0_tray`).

## What each part is (bought, cut, printed, wood, sheet)

The `kind` field of every part:

| kind | Count (home) | What it is |
|---|---|---|
| `purchased` | 37 | Bought parts: aluminium extrusions, MGN12 rails and carriages, NEMA 17 motors, T8 lead screw, belt and pulleys, cameras, LED rings, switches, slotted optical sensors, vacuum cup, spring buffer, feet. **Modelled from catalog or listing dimensions as simplified envelopes: accurate where they meet another part, not in their detail.** The extrusions and the lead screw are also cut to length (`out/cut_list.csv`). `gate_beam` is the overfill laser beam, drawn as a thin red transparent rod. |
| `made` | 2 | Cut from 1 mm aluminium sheet: `probe_flag` (flat blank in `out/probe_flag_blank.dxf`/`.svg`, bent 90° and drilled) and `carry_flag` (flat). Blank sizes are in `out/cut_list.csv`. |
| `printed` | 19 | 3D printed. Material and settings are in each part's note and in `out/printed/print_list.json`. There are 25 printed files (27 prints) including tools and the Phase 0 jig. |
| `wood` | 83 | `bed_plywood` (18 mm plywood) and the 82 guide rods: hardwood dowels, 5/16 in (7.94 mm) in the cut list, modelled at 8.0 mm (`ROD_D`). |
| `foam` | 13 | Pocket floor pads, 3 mm EVA + microfiber (`PAD_T`). |
| `slab` | 22 | Graded slabs and their labels at the nominal PSA size (80.3 × 135.5 × 6.6, `dims.py`), there to check clearances. They are not parts to make. |
| `fastener` | 63 | Screw and nut heads that could foul something. Not every fastener in the machine is modelled. |

Not in the CAD: frame corner brackets and joining plates, cables, the vacuum tube, the electronics panel, and the optional
light roof and rear brace (`model.machine(roof=True)` adds a roof envelope; no export uses it).

## Files

### Source (`cad/*.py`)

| File | What it does |
|---|---|
| `layout.py` | Master dimensions: pockets, rods, heights, travel, hard stops, gantry stack-up, camera window, carry sensor. `python3 layout.py` prints the pockets and runs the static layout checks. |
| `dims.py` | Slab dimensions (nominal and max). |
| `model.py` | Builds every part from `layout.py` and lists the printed parts (`printed_catalog()`), the cut list and the probe-flag blank. |
| `build.py` | Exports `out/` (below). `build.assembly(pose)` is the part list for a pose. |
| `export_glb.py` | Writes the GLB viewing files and checks them with trimesh. |
| `checks.py` | The 177 geometry checks. |
| `drawings.py` | The dimensioned drawing set (`out/drawings/`). |
| `render_docs.py`, `render_parts.py` | The PNG images in `docs/img/`. |

### Outputs (`cad/out/`)

| File | What it is |
|---|---|
| `assembly/slabrail_<pose>.step` | The full assembly in each pose (`home`, `pick_bottom`, `carry`, `station`). One named, coloured product per part, in machine coordinates. About 4.9–5.0 MB each. |
| `assembly/slabrail_home.glb`, `slabrail_carry.glb` | The same assemblies as meshes for viewing (0.25 mm / 0.3 rad tessellation, about 1.9 MB each). Use them to look at the design. Measure on the STEP files. |
| `printed/<part>.step`, `printed/<part>.stl` | The 25 printed parts, one solid each, in print orientation, standing on Z 0 with the bounding-box corner at the origin. These files are not in machine coordinates. STL tessellation: 0.05 mm / 0.1 rad. |
| `printed/print_list.json` | Per printed part: `qty`, `size_mm` (bounding box), `volume_cm3`, and a print note (material, orientation, walls, infill). |
| `cut_list.csv` | Stock cut to length: profile, use, length_mm, qty. Covers extrusions, the lead screw, the two aluminium flag blanks, the Phase 0 jig posts and stub, and the 82 dowels. |
| `probe_flag_blank.dxf` | Flat outline of the probe flag (mm). |
| `probe_flag_blank.svg` | The probe flag drawing with dimensions, bend line, hole and steps. Print at 100 % and check the 10 mm bar. |
| `checks.txt` | Output of the last `checks.py` run: one line per check (PASS/FAIL, value, limit, the closest pair). |
| `drawings/SlabRail_drawings.pdf` | The drawing set. `drawings/png/` holds previews and `drawings/dims.json` lists every dimension shown and its source. |
| `heads_cad.json` | Head shadow boxes and camera offsets for the software simulator. Not a review file. |
| `renders/` | OpenSCAD renders and their temporary STLs (not in git). |
| `export.log`, `render_docs.log` | Logs of earlier runs (not in git). Not needed. |

## Opening the files

- **STEP** (assemblies and printed parts): Fusion 360 (open or upload the file), Onshape (Import), FreeCAD (File > Open).
  Parts arrive with their names and colours. The assemblies contain 241–245 solids each.
- **GLB**: any glTF viewer. Drop the file on https://gltf-viewer.donmccurdy.com, open it in Windows 3D Viewer, or import
  it into Blender (File > Import > glTF 2.0). Slabs are semi-transparent.
- **STL**: any slicer. Millimetres, already in print orientation.
- **DXF / SVG**: any CAD or vector program. The SVG is 1:1 at 100 % print scale.

## Regenerating

Run everything from the `cad/` folder. You need Python 3 with CadQuery. `export_glb.py`'s self-check also needs
trimesh, `drawings.py` needs matplotlib, and the renders need OpenSCAD and `xvfb-run`. Tested here with CadQuery 2.8.0
and trimesh 5.1.1.

| Command | What it does |
|---|---|
| `python3 build.py` | Re-exports the printed STEP/STL and `print_list.json`, `cut_list.csv`, the probe-flag DXF/SVG, `heads_cad.json` and the four assembly STEPs, **then renders the PNGs in `out/renders/`**. Without OpenSCAD it stops with "openscad not installed" after the exports are written. `--renders` renders only. |
| `python3 export_glb.py` | Writes `slabrail_home.glb` and `slabrail_carry.glb` and checks them (mesh count, bounds against the STEP). Name poses to export others: `python3 export_glb.py station`. |
| `python3 checks.py > out/checks.txt` | Runs the 177 geometry checks (about 12–17 min; 16 min 43 s on 27 Oct on a shared 4-core machine) and prints one line per check. Exit code 1 if any check fails. |
| `python3 drawings.py` | Writes the drawing set to `out/drawings/`. Re-measures every dimension and exits 1 if one disagrees with the model. |

Every STEP header carries a timestamp, so `build.py` changes every STEP file in git even when the geometry has not
changed. Re-export only after changing the model.

## Checks

`checks.py` runs **177 checks; all 177 pass** [Certain, re-run on 27 Oct 2026 after the mesh fix below; the numbers are in
`out/checks.txt`, unchanged from the 23 Oct run]. It
measures exact minimum distances and overlap volumes (OpenCascade) at every pick, place, travel, station, hard-stop and
Phase 0 pose: all-pairs interference, the held slab against everything above it, rail margins, camera sight lines, the
face-down card window, LED rings, the probe, the carry sensor and home switches, and printed-part walls. `docs/DESIGN.md`
("Verification") summarises the results.

**Not checked** (`docs/DESIGN.md`): belt slack, cables and the vacuum tube, the real shapes of bought parts, loads and
deflection, the side load the strikers put on the switch levers, and the corner brackets and joining plates.

## Export check (27 Oct 2026)

All exports were re-made on 27 Oct 2026 after the two fixes below (clean meshes, then missing holes), then checked
against the current model:

- **Assembly STEP files are current.** For each pose, the STEP re-imported with CadQuery has the same number of solids
  as `build.assembly(pose)` (home 241, pick_bottom 241, carry 245, station 243). The bounding box and volume of every
  solid also match. Compared with the export before the hole fix, the only changed solids are `x_bracket` (−221.5 mm³,
  its four clamp-screw holes) and `camera_bracket` (−60.8 mm³, its four board holes).
- **GLB files**: 177 meshes (home) and 181 (carry), 57,190 and 57,238 triangles. Each is one mesh per non-fastener part
  plus the merged `fasteners` mesh. Bounds reloaded with trimesh equal the STEP bounding box (0.0 mm difference).
- **Printed parts**: all 25 STLs are closed (watertight), one body each, with no non-manifold edges. Each STL's bounding
  box equals `print_list.json` `size_mm` within 0.05 mm (`size_mm` is rounded to 0.1 mm; the largest difference, 0.05 mm,
  is on `x_bracket` and `z_motor_mount`), and each STL's volume rounds to the listed `volume_cm3`. All 25 STEPs are one
  valid solid. In `print_list.json` only `x_bracket`'s volume changed (70.7 to 70.5 cm³; 800.7 cm³ in all 27 prints),
  and the print notes now give walls and infill for every part, as in `docs/BUILD_GUIDE.md` §3.2.

**Hole fix.** Two printed parts had holes that were never cut. `holes_z()` cuts from Z −50 to 150 unless it is given a
range, and these two parts are built at machine height, above that:

- `x_bracket`: the 4 M3 clearance holes for the belt clamps (the tab is at Z 437–446; only the nut traps were cut).
- `camera_bracket`: the 4 Ø2.2 mm board holes, 32 mm square round the lens (the shelf is at Z 156–160).

Both calls now give the Z range. A script checked every `holes_z`, `holes_y`, `holes_x` and `slot_y` call (41 call
sites, every part they build at every pose) and every other `.cut()` in `model.py` (66 lines, all reached by the
exports). Every hole now removes material, and the only other cuts that remove nothing are harmless (the shelf-hole cut in
`station_ring_seat()`, already cleared by its cone, and one of the two screw-head reliefs in `x_switch_mount()`). None of the printed-part holes is filled again by a later union except the camera-mast M2 holes: the base
plate closes their bottoms, which leaves blind holes 11.5 mm deep (`station_mount`) and 7.5 mm deep (`phase0_base`) for
M2×6 screws. `checks.py` does not check that holes exist.

**Mesh fix.** The earlier `station_mount`, `phase0_base` and `phase0_tray` STLs were not clean meshes. The STEPs were
valid; the cause was in the model, and `model.py` now avoids it without moving any functional feature:

- `camera_mast()` (`station_mount`, `phase0_base`): the four 5 mm M2 bosses (centres at X ±10.5) touched the inside of
  the mast wall (X ±13) along a line, which left four non-manifold edges. Each boss now has a 3 mm wide web that runs
  0.5 mm into the wall. The web lies at |X| ≥ 12.5, outside the 25 mm camera board, so the board sits on the same boss
  tops. +14.3 mm³ per part.
- `phase0_tray`: the 45° lead-in taper started on the recess wall, which left four 0.2 mm sliver faces at the recess
  corners (the STL split into 5 bodies). The taper now starts 0.5 mm lower and 0.5 mm inset, inside the recess, so the
  same 45° faces run from Z 3 to the top. The lead-in's rounded corners are 0.5 mm larger in radius (+0.6 mm³ in all).

The camera, hole positions, mast outline, recess size and depth and the lead-in angle are unchanged.
