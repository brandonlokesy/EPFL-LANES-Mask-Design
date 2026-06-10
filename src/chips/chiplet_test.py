"""
chiplet_test.py
===============
Test variant of the local-gates chiplet:
  - Position grid uses filled circles (radius = marker_radius) instead of text
  - Gate array uses 10 x 10 um squares instead of T-shaped electrodes
  - Array is centred on the chip origin

Usage:
    python -m src.chips.chiplet_test          # writes to masks/standard/
    python -m src.chips.chiplet_test --edit   # fixed filename for iteration
"""

import gdstk
import numpy as np
from dataclasses import dataclass
import json
from pathlib import Path

from src.chips.chiplet_mask import (
    ChipletConfig,
    _add_corner_markers,
    _add_big_pads,
    _add_rectangular_pad_array,
)
from src.chips.chiplet_local_gates_mask import LocalGatesChipletConfig
from src.config.layers import LAYERS
from src.config.paths import STANDARD_DIR


@dataclass
class ChipletTestConfig(LocalGatesChipletConfig):
    marker_radius: float = 10.0  # um — radius of position-grid dots

    @classmethod
    def load(cls, path: Path) -> "ChipletTestConfig":
        with open(Path(path)) as f:
            return cls(**json.load(f))


# =============================================================================
# INTERNAL BUILDERS
# =============================================================================

def _add_circle_position_grid(cell: gdstk.Cell,
                               cfg: ChipletTestConfig) -> None:
    """Position grid using filled circles instead of text labels."""
    hw = cfg.chip_width  / 2
    hh = cfg.chip_height / 2

    pad_outer_x = hw - cfg.pad_sq_margin - cfg.pad_sq_size / 2
    pad_outer_y = hh - cfg.pad_sq_margin - cfg.pad_sq_size / 2

    x_start = -pad_outer_x + cfg.grid_inset
    y_start =  pad_outer_y - cfg.grid_inset
    sp      = cfg.grid_spacing

    lp = LAYERS["pos_markers"]
    for row_idx in range(cfg.grid_rows):
        for col_idx in range(cfg.grid_cols):
            cx = x_start + col_idx * sp
            cy = y_start - row_idx * sp
            cell.add(gdstk.ellipse(
                (cx, cy), cfg.marker_radius,
                layer=lp["layer"], datatype=lp["datatype"],
            ))


def _add_test_squares(cell: gdstk.Cell,
                      cfg: ChipletTestConfig) -> None:
    """10 x 10 um squares centred on each gate position."""
    n  = cfg.local_gate_sq_number
    sp = cfg.grid_spacing * 3

    x_start = -((n - 1) * sp) / 2 - cfg.grid_spacing / 2
    y_start =  ((n - 1) * sp) / 2 + cfg.grid_spacing / 2

    h  = 5.0  # half of 10 um
    lp = LAYERS["local_gates"]
    for row_idx in range(n):
        for col_idx in range(n):
            cx = x_start + col_idx * sp
            cy = y_start - row_idx * sp
            cell.add(gdstk.rectangle(
                (cx - h, cy - h), (cx + h, cy + h),
                layer=lp["layer"], datatype=lp["datatype"],
            ))


# =============================================================================
# PUBLIC API
# =============================================================================

def build_chiplet_test_mask(lib: gdstk.Library,
                             cfg: ChipletTestConfig,
                             cell_name: str = None) -> gdstk.Cell:
    if cell_name is None:
        cell_name = f"CHIPLET_TEST_{cfg.chiplet_number:03d}"

    existing = next((c for c in lib.cells if c.name == cell_name), None)
    if existing:
        return existing

    cell = lib.new_cell(cell_name)

    if cfg.draw_boundary:
        cell.add(gdstk.rectangle(
            (-cfg.chip_width/2, -cfg.chip_height/2),
            ( cfg.chip_width/2,  cfg.chip_height/2),
            **LAYERS["chip_boundary"],
        ))

    if cfg.draw_active_area:
        hw    = cfg.chip_width  / 2
        hh    = cfg.chip_height / 2
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        cell.add(gdstk.rectangle(
            (-hw + inset, -hh + inset),
            ( hw - inset,  hh - inset),
            **LAYERS["chip_active_area"],
        ))

    _add_corner_markers(cell, lib, cfg)
    _add_big_pads(cell, lib, cfg)
    _add_rectangular_pad_array(cell, lib, cfg)
    _add_circle_position_grid(cell, cfg)
    _add_test_squares(cell, cfg)

    return cell


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a test chiplet mask.")
    parser.add_argument("--edit", action="store_true")
    args = parser.parse_args()

    cfg = ChipletTestConfig(chiplet_id=1, chiplet_number=7)

    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    stem     = "chiplet_test_EDIT" if args.edit else f"chiplet_test_{cfg.chiplet_id:03d}"
    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_chiplet_test_mask(lib, cfg)
    lib.write_gds(gds_path)
    cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"  Chip size:    {cfg.chip_width} x {cfg.chip_height} um")
    print(f"  Chiplet ID:   {cfg.chiplet_id}")
    print(f"  Gate array:   {cfg.local_gate_sq_number} x {cfg.local_gate_sq_number}")
    print(f"  Gate spacing: {cfg.grid_spacing * 3} um")
