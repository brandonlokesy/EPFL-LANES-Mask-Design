# EPFL LANES Mask Suite

A Python-based GDS mask design tool for lithographic patterning at the LANES lab (STI-IEM), EPFL. Built on [`gdstk`](https://heitzmann.github.io/gdstk/) and [`gdsfactory`](https://gdsfactory.github.io/gdsfactory/).

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Viewing GDS Files in KLayout](#viewing-gds-files-in-klayout)
5. [Key Parameters](#key-parameters)
6. [Generating a Production Run](#generating-a-production-run)
7. [Adding a New Mask Type](#adding-a-new-mask-type)
8. [Layer Reference](#layer-reference)

---

## Project Structure

```
EPFL-LANES-Mask/
├── masks/
│   ├── .registry.json          # Run and wafer counter — tracked by git
│   ├── standard/               # Production GDS outputs (not tracked by git)
│   └── experimental/           # One-off / experimental outputs (not tracked by git)
├── assets/
│   └── fonts/
│       └── DEPLOF.gds          # Stroke font for labels
└── src/
    ├── assembly/               # Wafer-level mask builders
    │   ├── wafer_mask.py
    │   └── wafer_local_gates_mask.py
    ├── chips/                  # Chiplet-level mask builders
    │   ├── chiplet_mask.py
    │   └── chiplet_local_gates_mask.py
    ├── components/             # Reusable geometric primitives
    │   ├── markers.py          # Corner markers, crosses, pads
    │   └── verniers.py         # Vernier alignment structures
    ├── config/                 # Project-wide configuration
    │   ├── layers.py           # GDS layer definitions
    │   ├── paths.py            # Centralised file paths
    │   └── run_registry.py     # Run and wafer number tracking
    ├── scripts/
    │   └── generate_run.py     # Interactive batch wafer generator
    └── utils/
        └── deplof_font.py      # DEPLOF stroke font renderer
```

**The hierarchy is:** `components` → `chips` → `assembly`. Each level only imports from levels below it, never above.

---

## Installation

### Prerequisites

- [Anaconda](https://www.anaconda.com/download) or Miniconda
- [Git](https://git-scm.com/)
- [KLayout](https://www.klayout.de/build.html) for viewing GDS files
- [VSCode](https://code.visualstudio.com/) (recommended editor)

### 1. Clone the repository

```bash
git clone https://github.com/your-org/epfl-lanes-mask.git
cd epfl-lanes-mask
```

### 2. Create the conda environment

```bash
conda create -n cad-gds-layout python=3.12
conda activate cad-gds-layout
```

### 3. Install dependencies

```bash
pip install gdstk gdsfactory numpy
```

### 4. Install the project as a package

This step is required so that Python can resolve imports across the `src/` folder from any script.

```bash
pip install -e .
```

You only need to run this once. After this, all `from src.x.y import ...` imports will work correctly.

### 5. Set up VSCode (recommended)

Open the project root folder in VSCode (not a subfolder). Create `.vscode/settings.json`:

```json
{
    "terminal.integrated.cwd": "${workspaceFolder}",
    "python.terminal.executeInFileDir": false,
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe"
}
```

Use **Ctrl+Shift+D** to open the Run & Debug panel and select a named launch configuration. Always run scripts from the project root, not from inside `src/`.

---

## Quick Start

### Generate a single chiplet (for layout inspection)

Run from the terminal at project root:

```bash
python src/chips/chiplet_mask.py --edit
```

This writes `masks/standard/chiplet_EDIT.gds` without consuming a run number. Open it in KLayout to inspect the layout.

### Generate a single wafer

```bash
# Standard wafer — edit mode
python src/assembly/wafer_mask.py --edit

# Local gates wafer — edit mode
python src/assembly/wafer_local_gates_mask.py --edit
```

Edit mode is safe for layout iteration. It writes e.g. `STD-LG-EDIT-MODE.gds` and does not increment the run counter.

### Generate a production wafer

Omit `--edit` to consume a real run number from the registry:

```bash
python src/assembly/wafer_mask.py
```

This writes e.g. `masks/standard/STD-R01-W01.gds` and permanently increments the wafer counter.

> **Important:** Only run without `--edit` when you are ready to commit to a real lithography run. Run numbers cannot be decremented automatically.

### Generate multiple wafers for a lithography run

Use the interactive batch script:

```bash
python src/scripts/generate_run.py
```

This will prompt you to:
- Choose the mask type (`std` or `lg`)
- Start a new run number or continue the current one
- Enter how many wafers to generate
- Confirm before anything is written

---

## Viewing GDS Files in KLayout

### Opening a file

Launch KLayout, then **File → Open** and select a `.gds` file from `masks/standard/` or `masks/experimental/`.

### Setting up layer colours

Each layer number in the GDS corresponds to a named layer in `src/config/layers.py`. KLayout will show layer numbers by default — assign colours so the layers are immediately readable.

In the **Layers** panel (right side), right-click each layer entry and choose **Select Color** and **Select Stipple** (fill pattern). Recommended settings:

| Layer | Name | Suggested colour | Fill |
|-------|------|-----------------|------|
| 1 | `chip_boundary` | White | Outline only |
| 2 | `chip_active_area` | Grey | Outline only |
| 3 | `wafer_boundary` | White | Outline only |
| 10 | `corner_markers` | Cyan | Solid |
| 11 | `pad_markers` | Cyan | Solid |
| 12 | `pos_markers` | Blue | Solid |
| 13 | `chiplet_id` | Blue | Solid |
| 21 | `wafer_markers` | Green | Solid |
| 22 | `dicing_lanes` | Green | Hatched |
| 23 | `wafer_id` | Green | Solid |
| 70 | `local_gates` | Red | Solid |
| 71 | `top_gates` | Orange | Solid |

### Saving layer properties for reuse

Once configured, save your colour scheme so you don't have to repeat this:

**File → Save Layer Properties** → save as `layers.lyp` in the project root.

To reload next time: **File → Load Layer Properties**.

Share `layers.lyp` with your colleagues so everyone uses the same colour scheme. You can add it to the repository if you want it version-controlled.

### Useful KLayout shortcuts

| Shortcut | Action |
|----------|--------|
| `F` | Fit view to cell |
| `Ctrl + scroll` | Zoom in / out |
| Middle-click drag | Pan |
| `K` | Measure distance between two points |
| `Shift + F2` | Show cell hierarchy panel |
| `Escape` | Cancel current tool / deselect |
| `Ctrl + F` | Find and select a named cell |

### Navigating the cell hierarchy

A wafer GDS contains a hierarchy of cells: the top `WAFER` cell references individual `CHIPLET_XX` cells, each of which references a `BASE_CHIPLET_XX` cell. To navigate:

- Open **View → Cell List** (or press `Shift+F2`)
- Double-click a cell name to make it the active view
- Press `F` to fit the view to that cell

This is useful when you want to inspect a single chiplet without the full wafer around it.

---

## Key Parameters

All parameters live in dataclasses in `chiplet_mask.py`, `chiplet_local_gates_mask.py`, and `wafer_mask.py`. They are passed as keyword arguments when instantiating a config object and are saved to a `.json` file alongside every GDS output for reproducibility.

### Position marker grid

Defined in `ChipletConfig` in `src/chips/chiplet_mask.py`.

```python
cfg = ChipletConfig(
    grid_rows    = 31,       # number of rows in the position grid
    grid_cols    = 31,       # number of columns
    grid_spacing = 250.0,    # um — centre-to-centre spacing between markers
    grid_style   = "excel",  # label style: "excel" (A1, B2...) | "matrix" (00p00) | "binary"
)
```

> If you increase `grid_rows` or `grid_cols`, markers may overflow the active area. Reduce `grid_spacing` proportionally, or reduce the count.

### Local gate array

Defined in `LocalGatesChipletConfig` in `src/chips/chiplet_local_gates_mask.py`.

```python
cfg = LocalGatesChipletConfig(
    local_gate_sq_number    = 7,     # gates per side — full array is N×N
    local_gate_min_height   = 20.0,  # um — smallest gate in the sweep
    local_gate_max_height   = 50.0,  # um — largest gate in the sweep
    local_gate_contact_width = 10.0, # um — width of the contact lead
    local_gate_min_height_clearance = 30.0,  # um — vertical clearance below each gate
)
```

Gate dimensions are linearly swept from `local_gate_min_height` to `local_gate_max_height` across both axes of the array. Increasing `local_gate_sq_number` adds more steps to the sweep and more total gates. The array spacing is controlled by:

```python
local_gate_array_margin  = 250.0   # um — margin from the grid edge
local_gate_array_spacing = 1000.0  # um — spacing between array groups
```

### Chip size

```python
cfg = ChipletConfig(
    chip_width  = 12000.0,  # um  (12 mm)
    chip_height = 12000.0,  # um  (12 mm)
)
```

> If you change chip dimensions, verify that `pad_sq_margin`, `corner_margin`, and `grid_spacing` still place all features within the chip boundary by inspecting the output in KLayout.

### Wafer layout

Defined in `WaferConfig` in `src/assembly/wafer_mask.py`.

```python
cfg = WaferConfig(
    wafer_diameter = 100_000.0,           # um — 100 mm (4 inch)
    row_config     = [6, 6, 6, 6, 6, 6], # chips per row, ordered bottom to top
)
```

`row_config` controls how many chips sit in each row. The full array is always centred on the wafer origin. A more circular footprint can be achieved with e.g. `[4, 6, 6, 6, 6, 4]`.

### Vernier alignment structures

Defined in `ChipletConfig`. These sit in the bottom-right corner of each chip, between the active area and the chip edge.

```python
cfg = ChipletConfig(
    draw_verniers       = True,   # set False to suppress entirely
    vernier_pitch_ref   = 10.0,   # um — reference grating pitch
    vernier_pitch_delta = 1.0,    # um — resolution (minimum detectable misalignment)
    vernier_n_bars      = 5,      # bars per side → measurement range = ±n_bars × delta
    vernier_bar_length  = 50.0,   # um — length of each bar
    vernier_bar_width   = 3.0,    # um — width of each bar
    vernier_grating_gap = 10.0,   # um — gap between reference and aligned gratings
)
```

With the defaults: 1 µm resolution, ±5 µm range — appropriate for the MLA150.

To change which layers are compared against the reference (`pad_markers`), edit the `exposures` list in `_add_verniers` inside `src/chips/chiplet_mask.py`:

```python
exposures = [
    ("1", L["local_gates"]),  # label "1" — local gates vs pad_markers
    ("2", L["top_gates"]),    # label "2" — top gates vs pad_markers
    ("3", L["pos_markers"]),  # label "3" — pos markers vs pad_markers
]
```

Each entry is a `(label_string, layer_dict)` tuple. Add or remove entries to change the number of vernier pairs.

---

## Generating a Production Run

The run registry in `masks/.registry.json` tracks run and wafer numbers for each mask type. **This file is tracked by git.** Commit it after every production run so the counters stay in sync across the team.

### Naming convention

A filename like `STD-R02-W03-LG.gds` means:

| Field | Value | Meaning |
|-------|-------|---------|
| `STD` | — | Standard mask suite |
| `R02` | Run 2 | Second lithography campaign |
| `W03` | Wafer 3 | Third wafer in that run |
| `LG` | — | Local gates variant |

### When to start a new run

Start a **new run** when you are beginning a fresh lithography campaign — a new process flow, new sample batch, or new experiment. **Continue** the current run when you are patterning more wafers as part of the same ongoing process, even if it spans multiple days.

### Workflow for a new production run

```bash
# 1. Launch the batch generator
python src/scripts/generate_run.py

# 2. Follow the prompts:
#    Mask type  → std or lg
#    Run        → new (to start a new run number)
#    Wafers     → e.g. 5
#    Confirm    → yes

# 3. Commit the updated registry so colleagues see the new run numbers
git add masks/.registry.json
git commit -m "Run 02: 5x local gates wafers"
```

---

## Adding a New Mask Type

Follow this pattern whenever you want to add a new device layer or process step.

### 1. Add a layer entry

In `src/config/layers.py`, add your new layer with an appropriate number from the band that matches its purpose (see [Layer Reference](#layer-reference)):

```python
"mesa_etch": {"layer": 30, "datatype": 0},
```

### 2. Create a chiplet file in `src/chips/`

Use `chiplet_local_gates_mask.py` as a template:

```python
# src/chips/chiplet_mesa_mask.py
from src.chips.chiplet_mask import ChipletConfig, build_chiplet_mask
from src.config.layers import LAYERS
from dataclasses import dataclass
import gdstk

@dataclass
class MesaChipletConfig(ChipletConfig):
    mesa_width:  float = 100.0  # um — add your own parameters here
    mesa_height: float = 200.0  # um

def _add_mesa(cell: gdstk.Cell, cfg: MesaChipletConfig) -> None:
    # Draw your geometry here using the appropriate LAYERS entry
    cell.add(gdstk.rectangle(
        (-cfg.mesa_width/2, -cfg.mesa_height/2),
        ( cfg.mesa_width/2,  cfg.mesa_height/2),
        **LAYERS["mesa_etch"]
    ))

def build_mesa_mask(lib: gdstk.Library,
                    cfg: MesaChipletConfig,
                    cell_name: str = None) -> gdstk.Cell:
    if cell_name is None:
        cell_name = f"CHIPLET_MESA_{cfg.chiplet_number:03d}"

    existing = next((c for c in lib.cells if c.name == cell_name), None)
    if existing:
        return existing

    cell      = lib.new_cell(cell_name)
    base_cell = build_chiplet_mask(lib, cfg, cell_name=f"BASE_{cell_name}")
    cell.add(gdstk.Reference(base_cell, origin=(0, 0)))

    _add_mesa(cell, cfg)
    return cell
```

### 3. Create a wafer file in `src/assembly/`

```python
# src/assembly/wafer_mesa_mask.py
from dataclasses import dataclass, field
import gdstk
from src.assembly.wafer_mask import WaferConfig, build_wafer_mask
from src.chips.chiplet_mesa_mask import MesaChipletConfig, build_mesa_mask

@dataclass
class MesaWaferConfig(WaferConfig):
    chiplet: MesaChipletConfig = field(default_factory=MesaChipletConfig)

def build_mesa_wafer_mask(lib, cfg, cell_name="WAFER_MESA", wafer_ID_str=""):
    return build_wafer_mask(
        lib, cfg,
        cell_name=cell_name,
        chiplet_builder=build_mesa_mask,
        chiplet_cell_prefix="CHIPLET_MESA",
        wafer_ID_str=wafer_ID_str,
    )
```

### 4. Add reusable components (optional)

If your geometry is a self-contained shape that could be reused across mask types, add a function to `src/components/` rather than inlining it in the chiplet file. Follow the pattern in `src/components/markers.py`:

- Accept `lib: gdstk.Library` as the first argument
- Check whether a cell with that name already exists before creating it
- Return a named `gdstk.Cell` centred on `(0, 0)`
- Keep the function stateless — no side effects beyond adding to `lib`

### 5. Add launch configs

Add edit and production entries to `.vscode/launch.json` following the existing pattern so the new scripts are runnable from the debug panel.

### 6. Update `generate_run.py`

Add your new mask type to the `MASK_TYPES` dict in `src/scripts/generate_run.py`:

```python
MASK_TYPES = {
    "std":  ("STD", _build_standard_wafer),
    "lg":   ("STD", _build_local_gates_wafer),
    "mesa": ("STD", _build_mesa_wafer),      # ← add this
}
```

And add a corresponding builder function following the pattern of `_build_standard_wafer`.

---

## Layer Reference

Full layer table as defined in `src/config/layers.py`.

| Layer | Name | Description | Fabricated |
|-------|------|-------------|------------|
| 1 | `chip_boundary` | Chip outline rectangle | No |
| 2 | `chip_active_area` | Active device area boundary | No |
| 3 | `wafer_boundary` | Wafer circle outline | No |
| 9 | `notes` | Freeform text comments | No |
| 10 | `corner_markers` | Square arrays at chip corners | Yes |
| 11 | `pad_markers` | Square pads, L-marker, rectangular arrays | Yes |
| 12 | `pos_markers` | Position grid markers and labels | Yes |
| 13 | `chiplet_id` | Block-letter chiplet number | Yes |
| 21 | `wafer_markers` | Cross and square alignment markers | Yes |
| 22 | `dicing_lanes` | Cross markers in dicing streets | Yes |
| 23 | `wafer_id` | Wafer ID and lab label text | Yes |
| 30 | `mesa_etch` | Mesa etch (reserved) | — |
| 31 | `n_implant` | N-type implant (reserved) | — |
| 32 | `p_implant` | P-type implant (reserved) | — |
| 40 | `wg_core` | Waveguide core (reserved) | — |
| 41 | `ring` | Ring resonators (reserved) | — |
| 50 | `dielectric` | Dielectric deposition (reserved) | — |
| 51 | `dielectric_etch` | Dielectric etch openings (reserved) | — |
| 60 | `contact` | Ohmic contact (reserved) | — |
| 61 | `via1` | Contact to metal 1 (reserved) | — |
| 70 | `local_gates` / `metal1` | Local gate electrodes | Yes |
| 71 | `top_gates` | Top gate electrodes | Yes |
| 72 | `metal3` | Power/ground rails (reserved) | — |
| 73 | `bond_pads` | Wire bond pads (reserved) | — |
| 90 | `tlm` | Transmission line method structures (reserved) | — |
| 91 | `van_der_pauw` | Sheet resistance structures (reserved) | — |
| 100 | `keepout` | Keep-out exclusion zones | No |
| 101 | `dicing` | Dicing street outlines | No |
| 102 | `write_field` | E-beam / stepper write fields | No |

**Layer numbering bands:**

| Band | Purpose |
|------|---------|
| 1–9 | Annotation — never fabricated |
| 10–19 | Chip-level markers |
| 20–29 | Wafer-level markers |
| 30–39 | Substrate / implant |
| 40–49 | Photonic structures |
| 50–59 | Dielectric |
| 60–69 | Contacts and vias |
| 70–79 | Metal |
| 90–99 | Test structures |
| 100–109 | Do not fabricate |