"""
chiplet_local_gates_mask.py
===========================
Extends the standard chiplet mask with a local-gates pattern:
a square array of T-shaped gate electrodes, each varying in width
and height across the array.

Usage:
    from src.chips.chiplet_local_gates_mask import (
        LocalGatesChipletConfig, build_local_gates_mask
    )
"""

import gdstk
import numpy as np
from dataclasses import dataclass
import json
from pathlib import Path

from src.chips.chiplet_mask import ChipletConfig, build_chiplet_mask
from src.config.layers import LAYERS
from src.config.paths import STANDARD_DIR


@dataclass
class LocalGatesChipletConfig(ChipletConfig):
    local_gate_sq_number:            int   = 7      # gates per side of the square array
    local_gate_contact_width:        float = 10.0   # um
    local_gate_min_height:           float = 20.0   # um
    local_gate_max_height:           float = 50.0   # um
    local_gate_min_height_clearance: float = 30.0   # um
    local_gate_array_margin:         float = 250.0  # um
    local_gate_array_spacing:        float = 1000.0 # um

    @classmethod
    def load(cls, path: Path) -> "LocalGatesChipletConfig":
        with open(Path(path)) as f:
            return cls(**json.load(f))


# =============================================================================
# INTERNAL BUILDERS
# =============================================================================

def _draw_local_gate(cell: gdstk.Cell,
                     cx: float, cy: float,
                     row_idx: int, col_idx: int,
                     cfg: LocalGatesChipletConfig) -> None:
    """
    Draws a single T-shaped local gate electrode centred on (cx, cy).
    Width varies with row_idx, height varies with col_idx.
    """
    dims   = np.linspace(cfg.local_gate_min_height,
                         cfg.local_gate_max_height,
                         cfg.local_gate_sq_number)
    width  = dims[row_idx]
    height = dims[col_idx]

    full_width  = width  + cfg.local_gate_contact_width
    full_height = height + cfg.local_gate_min_height_clearance

    cw = cfg.local_gate_contact_width

    vtx = [
        (full_width/2 - cw - width + cx,  full_height/2 + cy),
        (full_width/2 - cw - width + cx,  full_height/2 - height + cy),
        (full_width/2 - cw + cx,          -full_height/2 + cfg.local_gate_min_height_clearance + cy),
        (full_width/2 - cw + cx,          -full_height/2 + cy),
        (full_width/2 + cx,               -full_height/2 + cy),
        (full_width/2 + cx,                full_height/2 + cy),
    ]

    cell.add(gdstk.Polygon(vtx, **LAYERS["local_gates"]))


def _add_local_gates(cell: gdstk.Cell,
                     cfg: LocalGatesChipletConfig) -> None:
    """Places the full local gate array onto the cell."""
    hw = cfg.chip_width  / 2
    hh = cfg.chip_height / 2

    array_outer_x = hw - cfg.pad_sq_margin - cfg.pad_sq_size/2 - cfg.grid_inset
    array_outer_y = hh - cfg.pad_sq_margin - cfg.pad_sq_size/2 - cfg.grid_inset

    x_start = -array_outer_x + cfg.grid_inset * 5/2
    y_start =  array_outer_y - cfg.grid_inset * 5/2
    sp      = cfg.grid_spacing * 4

    for row_idx in range(cfg.local_gate_sq_number):
        for col_idx in range(cfg.local_gate_sq_number):
            _draw_local_gate(
                cell,
                x_start + col_idx * sp,
                y_start - row_idx * sp,
                row_idx, col_idx, cfg
            )


# =============================================================================
# PUBLIC API
# =============================================================================

def build_local_gates_mask(lib: gdstk.Library,
                            cfg: LocalGatesChipletConfig,
                            cell_name: str = None) -> gdstk.Cell:
    """
    Builds a chiplet cell with the standard base mask plus local gate electrodes.

    Parameters
    ----------
    lib       : gdstk.Library
    cfg       : LocalGatesChipletConfig
    cell_name : optional GDS cell name override

    Returns
    -------
    gdstk.Cell
    """
    if cell_name is None:
        cell_name = f"CHIPLET_LG_{cfg.chiplet_number:03d}"

    existing = next((c for c in lib.cells if c.name == cell_name), None)
    if existing:
        return existing

    cell      = lib.new_cell(cell_name)
    base_name = f"BASE_{cell_name}"
    base_cell = build_chiplet_mask(lib, cfg, cell_name=base_name)

    cell.add(gdstk.Reference(base_cell, origin=(0, 0)))
    _add_local_gates(cell, cfg)

    return cell


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a local gates chiplet mask.")
    parser.add_argument("--edit", action="store_true")
    args = parser.parse_args()

    cfg = LocalGatesChipletConfig(chiplet_id=1, chiplet_number=7, grid_style="excel")

    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    stem     = "chiplet_local_gates_EDIT" if args.edit else f"chiplet_local_gates_{cfg.chiplet_id:03d}"
    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_local_gates_mask(lib, cfg)
    lib.write_gds(gds_path)
    cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"Written: {cfg_path}")
    print(f"  Chip size:      {cfg.chip_width} x {cfg.chip_height} um")
    print(f"  Chiplet ID:     {cfg.chiplet_id}")
    print(f"  Chiplet number: {cfg.chiplet_number:02d}")
    print(f"  Grid:           {cfg.grid_rows} rows x {cfg.grid_cols} cols")