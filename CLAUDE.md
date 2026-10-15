# CLAUDE.md

Context for working in this repo that `README.md` does not cover. `README.md` covers
project structure, installation, the run/registry workflow, and adding a new mask type.

## What these masks are for

LANES (STI-IEM, EPFL) studies the optoelectronics and photonics of transition metal
dichalcogenides (TMDCs). Samples are currently **exfoliated flakes**; later they will be
wafer-scale grown or transferred films. The group builds **single devices** (one
heterostructure, one ring resonator, one cavity), not integrated systems.

| Mask | Purpose |
|------|---------|
| `wafer_mask.py` | Wafer of template chips: the substrate that hBN and graphene flakes are exfoliated onto. |
| `wafer_local_gates_mask.py` | Local back gates, patterned under the heterostructure. |
| `photonic_wafer_mask.py` | SiN photonics. **Current goal: process qualification** — show that SiN devices can be fabricated at all. |

### The GDS stops where manual work begins

The masks define only what is patterned before and around the 2D material. After that:

- Flakes are exfoliated or transferred onto the chip.
- **Top gates and contacts are drawn by hand**, by aligning microscope images to the GDS.
  Flakes have irregular shapes that cannot be modelled in gdstk.

So do not generate contacts, top gates, or any geometry that must follow a flake's shape.
A missing contact layer is intentional.

### The position grid is a coordinate system

The 31×31 marker grid on `pos_markers` (layer 12) lets a flake be found again under a
microscope, and lets a measured device be traced to its position. People read
`grid_style`, `grid_spacing` and the grid labels by eye, so **changing them breaks
existing records**. The same holds for the per-chiplet wafer-ID stamp and the chiplet ID
number.

### Photonic chiplets are test devices for process qualification

- Parameter sweeps and dose tests are the purpose. Keep the list-valued config fields
  (`ap_radii`, `ad_radii`, `rt_gaps`) and the labelled device arrays.
- **Every device needs a label.** The label maps to the device's parameters in the JSON
  sidecar (the `.json` written next to each `.gds`). New device → new label.
- Each device is self-contained: its waveguides extend, bend and end in grating couplers,
  as in `pulley_with_leads`. Do not route between devices, expose ports at chiplet level,
  or lay the chiplet out as a system.
- Do not propose refactors toward joining photonics and electronics. That comes later,
  for single devices first, then at wafer scale.

The default cross-section is `SIN_VIS` (780 nm), chosen to couple to TMDC exciton
emission rather than telecom wavelengths. `LNOI` and `BTO` exist in `technology.py` but
are not in use.

## Process constraints: the layer decides the tool

Two CMI tools pattern the wafer. **The layer a feature is on decides which tool writes
it, and therefore its minimum size.** A 300 nm gap is fine on layer 40 and impossible on
layer 70.

| Tool | Writes | Min feature | Placement / alignment |
|------|--------|-------------|----------------------|
| [MLA150](https://www.epfl.ch/research/facilities/cmi/equipment/photolithography/mla-150/) maskless aligner | Wafer + chip markers, pads, IDs, local gates, top gates | **1 µm** | front-side < 500 nm; back-side < 1000 nm |
| [Raith EBPG5000](https://www.epfl.ch/research/facilities/cmi/equipment/ebeam-lithography/raith-ebpg5000/) e-beam | Photonic structures | **< 10 nm** | < 20 nm placement |

Layer → tool:

- **Layers 10–13, 21–23, 70–73** → MLA150. Nothing below **1 µm**.
- **Layers 40–45** (`wg_core`, `ring`, `grating`, `photonic_crystal`, `heater`,
  `metal_contact`) → EBPG5000. Sub-micron features are normal.
- **Layers 80–88** (`inv_coarse`, `inv_t1`…`inv_t8`) → EBPG5000. All one etch, split
  across layers so each part gets its own beam current. See "Inverse tone" below.
- **Layers 1–3, 9, 100–103** → never exposed. They hold annotation. Which layers are
  exposed is chosen at job setup, not in the GDS.

Smallest current features: on MLA150 layers, 5 µm (`local_gate_contact_width`,
`grid_marker_size`, `cross_sm_width`), 5× the limit. On photonic layers, 150 nm
(`ap_gap`) and 180 nm (`grating_line_width`). **Before choosing a dimension for new
geometry, check which layer it is on.**

### Inverse tone: one etch, several beam currents

`--invert` on the photonic entry points adds the negative of the photonic pattern, so the
SiN is etched everywhere except the rings and waveguides
(`src/components/photonics/inverse_tone.py`). That means exposing nearly the whole
144 mm² chip, so the exposure is split into **tiers**. A tier is one layer of the
exposure, written with its own beam current. Every exposed point is in exactly one tier.

- **Fine tier**: the area near devices, where waveguide sidewalls are. One per zone, on
  `inv_t1`…`inv_t8` (layers 81–88), written at low current (5–100 nA).
- **Coarse tier**: the rest of the chip, on `inv_coarse` (layer 80), written at high
  current (default 500 nA). It contains no sidewalls.

Terms used below:

- **`protect`**: everything on `wg_core`, `ring`, `grating` and `notes`. This film
  survives; no tier exposes it.
- **zone**: the definition of one fine tier: an area of the chip (its *frame*), an output
  layer and a beam current. The tier it produces is `frame − protect`.
- **frame**: either `shape: "box"` (default), the bounding boxes of the selected devices
  grown by `margin` µm; or `shape: "collar"`, `protect` itself grown by `width` µm.
- **selector**: picks what a box frame surrounds. `site` = each device plus its label;
  `label` = each label; `inst:<name>` = each sub-cell of a device whose cell name
  contains `<name>`, converted to chip coordinates with `ref.dtrans * sub.dbbox()`.
- **seam**: the edge where two tiers meet.
- **coverage guard**: the check that every part of `protect` lies inside some zone's frame.

Because a tier is `frame − protect`, **the frame decides which features a zone writes**.
Selectors only place the frame.

`--invert-zones` picks one of three ready-made zone lists:

| zone set | tiers | finest tier | total |
|----------|-------|-------------|-------|
| `site` (default) | 1 fine + coarse | 0.94 mm² @ 5 nA → 9.4 min | 23.3 min |
| `feature` | 4 fine + coarse | 0.04 mm² @ 5 nA → 24 s | 14.9 min |
| `collar` (w = 2 µm) | 1 fine + coarse | 0.03 mm² @ 5 nA → 17 s | 14.3 min |

**Assign each layer its own beam current at EBPG job setup.** Written entirely at 5 nA,
the same exposure takes ~23 h.

The coarse tier takes ~14 min in all three sets, so every zone set has a total write time
of at least ~14 min. Going from `site` to `feature` or `collar` saves ~9 min, by
shortening the 5 nA tier from 9.4 min to 17–24 s. That improves edge quality, not speed:
a shorter high-resolution write gives the beam and stage less time to drift. To cut the
total, change the coarse tier instead: shrink it (`invert_coarse_extent = "active_area"`)
or raise its beam current.

Rules that are easy to break:

- **Zone order is precedence, finest first.** Frames can overlap: around one
  `pulley_with_leads` the grating-coupler box spans y 19…79 µm and the bend box spans
  y −11…39 µm. Each zone takes only area no earlier zone took, so the earlier zone keeps
  the overlap.
- **The coarse frame is `coarse_box` minus all zone frames** — the frames, not the
  tiers. That gives tiers shared edges with no gap and no double exposure. `coarse_box` is
  the chip or the active area, set by `invert_coarse_extent`.
- **The coverage guard must raise an error.** Protected geometry outside every frame falls
  into the coarse tier, so its sidewall is written with the largest spot. This happens
  when a zone set omits a feature class: removing the `routing` zone from
  `ZONES_PER_FEATURE` leaves 359 µm² of bends and straights uncovered. Set
  `invert_allow_uncovered = True` only when that is intended.
- **`break_polygons` runs last.** A GDSII polygon holds at most 1024 points (one 8 KB
  record), and the booleans produce ~18 000-point polygons, so they must be split. Any
  boolean after the split merges the pieces back.
- **`margin` (box) or `width` (collar) is the seam-to-sidewall distance.** Shrinking the
  fine tiers moves seams closer to sidewalls. At 10 µm a seam is outside forward-scatter
  range but inside the ~30 µm backscatter range; at 2 µm it is inside both. Then the
  sidewall dose also depends on the coarse tier's dose, and **proximity correction is
  required**. Large margins cost little: `merge_slack` (µm) fills gaps between boxes
  narrower than its value, so boxes that grow into each other merge.
- **A collar's frame is `protect.sized(width)`, which includes the pattern** — not
  `sized − protect`. Then `frame − protect` gives the ribbon, tiers still share edges,
  and the coverage guard works. A ribbon-only frame does not contain `protect`, so the
  guard would always fire.
- **Printed or raised text must be ASCII.** On this machine an em-dash encodes as cp1252
  byte `0x97`, which cuts the message off and makes the output invalid UTF-8; `grep` then
  reports "Binary file matches" and hides the text. Comments and docstrings may use any
  characters.

Check any inverted build with `python -m src.scripts.verify_inverse_tone <gds>`. It reads
the GDS back, recomputes the tiers for each chiplet independently, and checks **every pair**
of tiers for overlap. Sub-nanometre residuals on a few checks are expected: splitting
polygons snaps vertices to the 1 nm grid, while the positive geometry is drawn much finer
(`pulley_n_segments = 2048` gives 15 nm segments on a 5 µm ring; 512 segments would
already be within 0.09 nm of the true circle).

### Overlay budget is set by the MLA150, not the e-beam

The EBPG places features to < 20 nm, but it aligns to markers written by the MLA150, which
aligns to < 500 nm. So photonic-to-gate alignment error is ~500 nm. If a design needs
photonic structures within a few hundred nm of a local gate or a flake, say it is at the
limit of this process; do not assume 20 nm.

### Other MLA150 constraints

- Max exposure area 150 × 150 mm; the 100 mm wafer fits.
- Min substrate 5 × 5 × 0.1 mm. The pneumatic autofocus needs a clear 5 × 5 mm area on
  the surface, which matters if a diced 12 × 12 mm chiplet is ever exposed again.
- Accepts `.gds`, `.cif`, `.dxf`. The repo writes GDSII directly.
- Lasers: 405 nm and 375 nm.

### Not published — ask CMI before relying on it

The EBPG5000 page does not give write-field size, stitching accuracy, beam current range,
or accepted file formats. Field size and stitching matter most: a ring or long waveguide
that crosses a write-field boundary gets a stitching error. Do not assume a device fits in
one field.

## Hard rule: `--edit` or nothing

Every entry point (`src/chips/*_mask.py`, `src/assembly/*_mask.py`) takes `--edit`.
Without it, the script calls `next_wafer()`, which **permanently increments
`masks/.registry.json`**; there is no decrement. Never run a production build unless asked.
Use `--edit` for every build while iterating.

`src/scripts/generate_run.py` is interactive and uses up run numbers. Never run it to test
anything.

## Two toolkits, one wafer

- **`gdstk`**: standard and local-gates masks (`chiplet_mask.py`,
  `chiplet_local_gates_mask.py`, all of `src/assembly/`, `src/components/markers.py`,
  `src/utils/`).
- **`gdsfactory`**: the photonic chiplet only (`src/chips/photonic_chiplet_*.py`,
  `src/components/photonics/`).

The photonic chiplet is placed on the wafer by `_photonic_chiplet_builder`
(`src/assembly/photonic_wafer_mask.py:63`). It builds the `gf.Component`, writes it to a
temporary GDS, reads that back with `gdstk`, flattens it, and adds it to the library. Two
lines in that function must stay:

- `gf.clear_cache()` before **every** placement. The photonic helpers use fixed cell names
  (`CORNER_MARKER_3x3`, `BIG_PAD_SQUARE`, …) and kfactory (the layout library under
  gdsfactory) keeps one global cell registry, so the next chiplet's cells would collide
  with the previous one's.
- `top.flatten()`. Without it, device sub-cell names (rings, gratings) end up in the shared
  `gdstk` library and collide between placements.

Call `gf.gpdk.PDK.activate()` before building anything photonic. The entry points and
`generate_run.py` already do.

## The chiplet_builder contract

`build_wafer_mask` (`src/assembly/wafer_mask.py:381`) places chiplets across the wafer and
is used unchanged by every wafer variant. Anything passed to it as `chiplet_builder` must
have this signature:

```python
builder(lib: gdstk.Library, chip_cfg, cell_name: str) -> gdstk.Cell
```

The photonic adapter works because it matches this signature. A new mask type needs a new
builder with this signature plus a `chiplet_cell_prefix`, not a copy of `build_wafer_mask`.

## Cell builders return existing cells

Component factories (`src/components/markers.py`, via `_get_or_create`) and chiplet
builders (`chiplet_mask.py:405`) return the existing cell if one with that name is already
in the library. Keep this in new builders: `build_wafer_mask` relies on it so that each
chiplet cell is defined once and referenced at every placement.

## Layers

`src/config/layers.py` is the **single source of truth**. The layer table in `README.md`
is out of date (it names layer 22 `dicing_lanes` where the code has `dicing_crosses`, and
lacks the newer photonic layers).

Access differs by toolkit:

```python
# gdstk: unpack the LAYERS dict as keyword arguments
cell.add(gdstk.rectangle(p0, p1, **LAYERS["wg_core"]))

# gdsfactory: needs a (layer, datatype) tuple
from src.components.photonics.technology import _l, LAYER
c.add_polygon(pts, layer=_l("pad_markers"))   # or LAYER.WG_CORE
```

`metal1` and `local_gates` are two names for layer 70. `wg_core` and `wg_clad` share a
layer number and differ only in datatype (0 vs 1).

Datatypes: `0` = fabricated geometry, `1` = simulation/reference only, `2` = process
compensation.

## Units and library settings

Everything is in **micrometres**. Libraries are always created as:

```python
gdstk.Library(unit=1e-6, precision=1e-9)
```

Wafer-scale values are also µm (`wafer_diameter = 100_000.0` is 100 mm). Only printed
summaries convert to mm.

## Config dataclass contract

Every config is a `@dataclass` with `to_dict()`, `save(path)` and `load(path)`. A JSON
copy of the config is written next to every GDS, so the GDS can be regenerated.

When adding a parameter:

- Make it a **dataclass field**, not a module-level constant, or it will not be in the
  JSON.
- Mutable defaults use `field(default_factory=...)`.
- A config containing another config needs a hand-written `load` that rebuilds the inner
  one; see `WaferConfig.load` (`wafer_mask.py:131`) and `PhotonicWaferConfig.load`.
- `build_wafer_mask` creates each chiplet's config with
  `cfg.chiplet.__class__(**{**cfg.chiplet.to_dict(), "chiplet_number": n})`, so every
  chiplet config must be constructible from its own `to_dict()` alone.

The chip centre is at `(0, 0)` everywhere. The position helpers in
`src/chips/layout_geometry.py` import neither gdstk nor gdsfactory, so both kinds of
chiplet use them.

## Import direction

`components` → `chips` → `assembly`. Each level imports only from levels before it. The
gdsfactory chiplet imports `layout_geometry` and `utils.text` from the gdstk side, which is
allowed because both are lower levels. The reverse is not allowed.

## Writing style — docstrings, comments, and replies

Applies to code text and to chat replies alike. Length is not the problem; empty lines
are. **Every line must tell the reader something they did not know from the previous
lines or from the code itself.** A long docstring where each line carries a fact is fine.
A short one that says nothing ("handles the inversion logic") is not.

Test each line: if it were deleted, would the reader lose a fact, a definition, a unit, a
reason, or a constraint? If not, delete it.

- **Name the concrete thing.** Every term refers to something you can point at: a
  variable (`protect`), a layer (`inv_t1`, 81), a value with units (30 µm, 5 nA). Not
  "the pattern" when you mean `protect` = union of `wg_core`, `ring`, `grating`, `notes`.
- **Define a term once, where it first appears**, by what it is in the code. If a word
  (e.g. "zone", "frame", "tier") has a specific meaning here, say it in one line.
- **No filler or metaphor**: "load-bearing", "earns its keep", "the whole idea", "under
  the hood", "crucially", "robust", "seamless", "leverage", "simply", "note that".
- **Docstring = what it does, inputs with units, return value, and any non-obvious
  constraint with its reason in one sentence.** No design history, no alternatives
  that were rejected, no restating what the code plainly shows.
- **Define every field, even obvious ones.** When a docstring names a structure (a dict,
  a config, a parameter list), give every key one line: what it is, its unit, and an
  example value.
- Numbers in examples are the real defaults or measured values, never invented.
