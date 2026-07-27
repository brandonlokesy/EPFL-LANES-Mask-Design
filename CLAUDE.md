# CLAUDE.md

Operational context for working in this repo. `README.md` covers project structure,
installation, the run/registry workflow, and how to add a new mask type — read it for
those. This file covers what the README doesn't.

## What these masks are for

LANES (STI-IEM, EPFL) works on the optoelectronics and photonics of transition metal
dichalcogenides. Materials are currently **exfoliated flakes**; the trajectory is toward
wafer-scale grown or transferred films. The group works at **device level** — one
heterostructure, one ring resonator, one cavity — not integrated systems.

Mask families and their purpose:

| Mask | Purpose |
|------|---------|
| `wafer_mask.py` | Template chip patterns across a wafer. Substrate for exfoliating flakes (hBN, graphene). |
| `wafer_local_gates_mask.py` | Local back gates under the heterostructure device stack. |
| `photonic_wafer_mask.py` | SiN photonics. **Current goal: demonstrate we can fabricate SiN devices at all** — process qualification, not a functioning system. |

### The GDS is a template, not a finished device

This is the most important thing to understand before changing anything. These masks
define what is lithographically patterned *before and around* the 2D material. The device
is completed by hand downstream:

- Flakes are exfoliated or transferred onto the patterned substrate.
- **Top gates and contacts are drawn manually**, by aligning microscope images against the
  GDS, because flakes are irregularly shaped and can't be modelled in gdstk.

So: don't attempt to generate contacts, top gates, or any geometry that has to conform to
a flake. Don't treat an absent contact layer as an oversight. The layout stops where the
manual step begins, and that boundary is deliberate.

### The position grid is a coordinate system

The 31×31 marker grid on `pos_markers` (layer 12) exists so a flake can be located and
relocated under a microscope, and so a measured device can be traced back to a position.
`grid_style`, `grid_spacing`, and the label scheme are a **measurement index that humans
read optically** — treat changes to them as breaking, not cosmetic. The same applies to
the per-chiplet wafer-ID stamp and the chiplet ID number.

### What this means for photonic work right now

The photonic chiplet is a **device zoo for process qualification**. Concretely:

- Parameter sweeps and dose tests are the point, not a detour. The list-valued config
  fields (`ap_radii`, `ad_radii`, `rt_gaps`) and the labelled array pattern are core.
- **Traceability matters**: every device needs a label that maps back to its parameters
  via the JSON sidecar. If you add devices, add labels.
- Devices are self-contained — extend, bend, terminate in grating couplers, as
  `pulley_with_leads` does. Don't add routing between devices, don't expose ports on the
  chiplet, don't floorplan for a system.
- Don't propose integration refactors. Photonics and electronics converge into an E–O
  system later, at device level first and wafer scale after that. Building for it now is
  premature.

The default cross-section is `SIN_VIS` (780 nm), consistent with coupling to TMDC exciton
emission rather than telecom. `LNOI` and `BTO` cross-sections exist in `technology.py` but
SiN is the active platform.

## Process constraints — two tools, and the layer tells you which

Patterning is split across two CMI tools. **Which layer a feature lands on determines
which tool writes it, and therefore which design rules apply.** A 300 nm gap is routine on
layer 40 and unbuildable on layer 70.

| Tool | Writes | Min feature | Placement / alignment |
|------|--------|-------------|----------------------|
| [MLA150](https://www.epfl.ch/research/facilities/cmi/equipment/photolithography/mla-150/) maskless aligner | Wafer + chip markers, pads, IDs, local gates, top gates | **1 µm** | FSA < 500 nm; BSA < 1000 nm |
| [Raith EBPG5000](https://www.epfl.ch/research/facilities/cmi/equipment/ebeam-lithography/raith-ebpg5000/) e-beam | Photonic structures | **< 10 nm** | < 20 nm placement |

Layer → tool:

- **Layers 10–13, 21–23, 70–73** → MLA150. Nothing below **1 µm**.
- **Layers 40–45** (`wg_core`, `ring`, `grating`, `photonic_crystal`, `heater`,
  `metal_contact`) → EBPG5000. Sub-micron is expected here.
- **Layers 1–3, 9, 100–102** → never exposed. The GDS deliberately contains non-fabricated
  annotation; layer selection happens at job setup, not in the file.

Current designs check out against these limits. The smallest MLA150-layer features are
5 µm (`local_gate_contact_width`, `grid_marker_size`, `cross_sm_width`) — 5× margin. The
smallest photonic features are 150 nm (`ap_gap`) and 180 nm (`grating_line_width`) — far
above the EBPG floor. Keep it that way: when adding geometry, check which layer it lands
on before choosing dimensions.

### Overlay budget is set by the MLA150, not the e-beam

The EBPG places to < 20 nm, but it aligns to markers *written by the MLA150*, whose own
front-side alignment is < 500 nm. So photonics-to-gates overlay is dominated by the
~500 nm MLA150 term. Any design whose function depends on photonic structures landing
within a few hundred nm of a local gate or a flake is at the edge of what this process
flow can deliver — say so rather than assuming the 20 nm figure applies.

### Other MLA150 constraints

- Max exposure area 150 × 150 mm; the 100 mm wafer fits comfortably.
- Min substrate 5 × 5 × 0.1 mm, and pneumatic autofocus needs a clear 5 × 5 mm square on
  the surface — relevant if diced 12 × 12 mm chiplets are ever re-exposed.
- Accepts `.gds`, `.cif`, `.dxf`. The repo writes GDSII, so no conversion step.
- 405 nm and 375 nm laser diodes.

### Not published — confirm with CMI before it matters

The EBPG5000 page gives resolution and placement accuracy but **not** field size,
stitching accuracy, beam current range, or accepted file formats. Field size and stitching
are the ones that could bite: a resonator or a long waveguide straddling a write-field
boundary picks up stitching error. Don't assume a device fits in one field.

## Hard rule: `--edit` or nothing

Every entry point (`src/chips/*_mask.py`, `src/assembly/*_mask.py`) takes `--edit`.
Without it, the script calls `next_wafer()` and **permanently increments
`masks/.registry.json`**. There is no decrement. Never run a production build unless
explicitly asked to; default to `--edit` for every build you do while iterating.

`src/scripts/generate_run.py` is interactive and consumes run numbers — don't invoke it
to test anything.

## Two toolkits, one wafer

- **`gdstk`** — standard and local-gates masks (`chiplet_mask.py`, `chiplet_local_gates_mask.py`,
  all of `src/assembly/`, `src/components/markers.py`, `src/utils/`).
- **`gdsfactory`** — the photonic chiplet only (`src/chips/photonic_chiplet_mask.py`,
  `src/components/photonics/`).

The photonic chiplet reaches the wafer through an adapter at
`src/assembly/photonic_wafer_mask.py:63` (`_photonic_chiplet_builder`): build the
`gf.Component`, write it to a temp GDS, read it back with `gdstk`, flatten, add to the
library. Two constraints live in that function and are easy to break:

- `gf.clear_cache()` must run before **every** placement. The photonic helpers use fixed
  cell names (`CORNER_MARKER_3x3`, `BIG_PAD_SQUARE`, …) and kfactory's layout registry is
  global, so rebuilding for the next chiplet collides without it.
- The `top.flatten()` is what stops per-device sub-cell names (rings, gratings) leaking
  into the shared library and colliding between placements. Don't remove it.

`gf.gpdk.PDK.activate()` must be called before building anything photonic — the entry
points and `generate_run.py` do this explicitly.

## The chiplet_builder contract

`wafer_mask.build_wafer_mask` (`src/assembly/wafer_mask.py:381`) is the generic tiler and
is reused unchanged by every wafer variant. Anything passed as `chiplet_builder` must
match:

```python
builder(lib: gdstk.Library, chip_cfg, cell_name: str) -> gdstk.Cell
```

The photonic path only works because the adapter conforms to this signature. A new mask
type means a new builder with this shape plus a `chiplet_cell_prefix` — not a fork of
`build_wafer_mask`.

## Idempotent cell builders

Component factories (`src/components/markers.py`, via `_get_or_create`) and chiplet
builders (`chiplet_mask.py:405`) check whether a cell of that name already exists in the
library and return it rather than rebuilding. Preserve this when adding builders — the
wafer tiler relies on it to share master cells across placements.

## Layers

`src/config/layers.py` is the **single source of truth**. The layer table in `README.md`
has drifted from it and should not be trusted (it names layer 22 `dicing_lanes` where the
code defines `dicing_crosses`, and omits the photonic layers added since).

Two different access idioms, by toolkit:

```python
# gdstk — LAYERS values splat directly as kwargs
cell.add(gdstk.rectangle(p0, p1, **LAYERS["wg_core"]))

# gdsfactory — needs a (layer, datatype) tuple
from src.components.photonics.technology import _l, LAYER
c.add_polygon(pts, layer=_l("pad_markers"))   # or LAYER.WG_CORE
```

`metal1` and `local_gates` are the same layer (70) — an alias, not two layers. Same for
`wg_core` / `wg_clad`, which differ only by datatype (0 vs 1).

Datatype convention: `0` = fabricated geometry, `1` = simulation/reference only,
`2` = process compensation.

## Units and library settings

Everything is in **micrometres**. Libraries are always created as:

```python
gdstk.Library(unit=1e-6, precision=1e-9)
```

Wafer-scale numbers are still µm (`wafer_diameter = 100_000.0` is 100 mm). Only the print
summaries divide by 1000 for display.

## Config dataclass contract

Every config is a `@dataclass` with `to_dict()` / `save(path)` / `load(path)`, and a JSON
sidecar is written next to every GDS for reproducibility.

Consequences when adding a parameter:

- It must be a **dataclass field**, not a module-level constant, or it won't reach the
  JSON record.
- Mutable defaults use `field(default_factory=...)`.
- Nested configs need a hand-written `load` that rebuilds the child — see
  `WaferConfig.load` (`wafer_mask.py:131`) and `PhotonicWaferConfig.load`.
- `build_wafer_mask` reconstructs each chiplet config via
  `cfg.chiplet.__class__(**{**cfg.chiplet.to_dict(), "chiplet_number": n})`, so every
  chiplet config must be constructible purely from its own `to_dict()`.

Coordinate convention throughout: chip centre at `(0, 0)`. Position helpers in
`src/chips/layout_geometry.py` are pure functions with no toolkit dependency, which is why
both the gdstk and gdsfactory chiplets can share them.

## Import direction

`components` → `chips` → `assembly`. Each level imports only from levels below it. The
gdsfactory chiplet reuses `layout_geometry` and `utils.text` from the gdstk side; that's
fine (both are below it). The reverse would not be.
