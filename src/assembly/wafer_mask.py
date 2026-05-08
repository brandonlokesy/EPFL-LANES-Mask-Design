"""
wafer_mask.py
=============
Wafer-level mask assembly. Places chiplets on a wafer grid and adds:
  - Wafer boundary circle
  - Dicing lane crosses
  - Multi-scale cross + square alignment markers
  - Stepped L-shaped pad markers
  - Wafer ID and lab label text

Usage:
    from src.assembly.wafer_mask import WaferConfig, build_wafer_mask
    import gdstk

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cfg = WaferConfig()
    build_wafer_mask(lib, cfg, wafer_ID_str="STD-R01-W01")
    lib.write_gds("wafer.gds")
"""

import gdstk
import numpy as np
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path
from datetime import datetime

from src.chips.chiplet_mask import ChipletConfig, build_chiplet_mask
from src.config.layers import LAYERS
from src.config.paths import STANDARD_DIR
from src.config.run_registry import next_wafer
from src.utils.deplof_font import deplof_text
from src.components.markers import (
    make_cross_marker,
    make_dicing_lane_cross,
    make_square_marker,
    make_L_shaped_wafer_pad,
)
from src.config.user_config import USER_ID

try:
    from gdsfactory.constants import _width, _indent
except ImportError as e:
    raise ImportError(
        "gdsfactory is required for wafer label rendering. "
        "Install it with: pip install gdsfactory"
    ) from e


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class WaferConfig:
    # --- Wafer geometry ---
    wafer_diameter:  float = 100_000.0   # um  (100 mm = 4 inch)

    # --- Dicing lane cross ---
    cross_length:    float = 2000.0
    cross_width:     float = 100.0

    # --- Multi-scale alignment crosses (large → medium → small) ---
    # Each scale has a cross and a square marker placed beside it.
    cross_lg_length: float = 400.0
    cross_lg_width:  float = 20.0
    cross_lg_offset: float = 3800.0       # distance from chip-array edge
    square_lg_size:  float = 200.0
    square_lg_inset: float = 500.0        # distance from cross centre to square centre

    cross_md_length: float = 200.0
    cross_md_width:  float = 10.0
    square_md_size:  float = 100.0
    square_md_inset: float = 250.0
    cross_md_offset_from_lg: float = 1150.0

    cross_sm_length: float = 100.0
    cross_sm_width:  float = 5.0
    square_sm_size:  float = 50.0
    square_sm_inset: float = 125.0
    cross_sm_offset_from_md: float = 575.0

    # --- Stepped L-pad ---
    L_pad_height1:   float = 150.0
    L_pad_height2:   float = 250.0
    L_pad_height3:   float = 500.0
    L_pad_length1:   float = 1000.0
    L_pad_length2:   float = 3000.0
    L_pad_length3:   float = 6000.0
    L_pad_h_offset:  float = 950.0
    L_pad_v_offset:  float = 3800.0

    # --- Run / wafer identity ---
    run_number:      int   = 0
    wafer_number:    int   = 0

    # --- Chip arrangement ---
    row_config:      list  = field(default_factory=lambda: [6, 6, 6, 6, 6, 6])
    draw_boundary:   bool  = True

    # --- Wafer ID label ---
    wafer_label_ID_x_pos: float =     0.0
    wafer_label_ID_y_pos: float = -43000.0
    wafer_label_ID_size:  float =   800.0

    # --- Secondary lab label ---
    wafer_small_label_xpos: float =  16000.0
    wafer_small_label_ypos: float = -40500.0
    wafer_small_label_size: float =    600.0

    # --- Chiplet config (nested) ---
    chiplet: ChipletConfig = field(default_factory=ChipletConfig)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chiplet"] = self.chiplet.to_dict()
        return d

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "WaferConfig":
        with open(Path(path)) as f:
            d = json.load(f)
        d["chiplet"] = ChipletConfig(**d["chiplet"])
        return cls(**d)


# =============================================================================
# INTERNAL BUILDERS
# =============================================================================

def _compute_chip_positions(row_config: list,
                             chip_w: float,
                             chip_h: float) -> list[tuple[float, float, int]]:
    """
    Returns [(x_centre, y_centre, chiplet_number), ...] for every chip.
    Array is centred on the wafer origin. Numbering is left-to-right,
    bottom-to-top (row 0 = bottom row, chip 0 = leftmost).
    """
    n_rows   = len(row_config)
    total_h  = n_rows * chip_h
    y_origin = -total_h / 2

    positions      = []
    chiplet_number = 0

    for row_idx, n_cols in enumerate(row_config):
        total_w  = n_cols * chip_w
        x_origin = -total_w / 2
        y_centre = y_origin + row_idx * chip_h + chip_h / 2

        for col_idx in range(n_cols):
            x_centre = x_origin + col_idx * chip_w + chip_w / 2
            positions.append((x_centre, y_centre, chiplet_number))
            chiplet_number += 1

    return positions


def _add_dicing_lanes(lib: gdstk.Library,
                      cell: gdstk.Cell,
                      cfg: WaferConfig) -> None:
    """Places dicing-lane crosses at every internal chip boundary intersection."""
    cross_cell = make_dicing_lane_cross(lib, cfg.cross_length, cfg.cross_width)

    chip_w = cfg.chiplet.chip_width
    chip_h = cfg.chiplet.chip_height
    n      = max(cfg.row_config)

    positions = [
        (-chip_h*2 + j*chip_h, -chip_w*2 + i*chip_w)
        for i in range(n - 1)
        for j in range(n - 1)
    ]
    for x, y in positions:
        cell.add(gdstk.Reference(cross_cell, origin=(x, y)))


def _array_dimensions(cfg: WaferConfig) -> tuple[float, float]:
    """Returns (half_width, half_height) of the full chip array footprint."""
    n   = max(cfg.row_config)
    hw  = cfg.chiplet.chip_width  * n
    hh  = cfg.chiplet.chip_height * n
    return hw, hh


def _add_cross_scale(lib: gdstk.Library,
                     cell: gdstk.Cell,
                     positions: list[tuple[float, float]],
                     cross_cell: gdstk.Cell,
                     square_cell: gdstk.Cell,
                     square_inset: float) -> None:
    """
    Places a cross and four flanking squares at each position.
    The squares sit at ±square_inset in x and y from each cross centre.
    """
    for x, y in positions:
        cell.add(gdstk.Reference(cross_cell, origin=(x, y)))
        for dx in (+square_inset, -square_inset):
            cell.add(gdstk.Reference(square_cell, origin=(x + dx, y)))
        for dy in (+square_inset, -square_inset):
            cell.add(gdstk.Reference(square_cell, origin=(x, y + dy)))


def _add_alignment_markers(lib: gdstk.Library,
                            cell: gdstk.Cell,
                            cfg: WaferConfig) -> None:
    """
    Places three scales of cross+square alignment markers outside the chip array.
    Large markers are at the four cardinal positions. Medium and small markers
    are stacked above the top cardinal position only.
    """
    hw, hh = _array_dimensions(cfg)

    # ── Large scale ────────────────────────────────────────────────────────────
    cross_lg  = make_cross_marker(lib, "CROSS_LG",  cfg.cross_lg_length, cfg.cross_lg_width)
    square_lg = make_square_marker(lib, "SQUARE_LG", cfg.square_lg_size)

    lg_positions = [
        (-hw/2 - cfg.cross_lg_offset, 0),
        ( hw/2 + cfg.cross_lg_offset, 0),
        (0, -hh/2 - cfg.cross_lg_offset),
        (0,  hh/2 + cfg.cross_lg_offset),
    ]

    md_positions = [
        (-hw/2 - cfg.cross_lg_offset - cfg.cross_md_offset_from_lg, 0),
        ( hw/2 + cfg.cross_lg_offset + cfg.cross_md_offset_from_lg, 0),
        (0,  hh/2 + cfg.cross_lg_offset + cfg.cross_md_offset_from_lg),
    ]

    sm_positions = [
        (-hw/2 - cfg.cross_lg_offset - cfg.cross_md_offset_from_lg - cfg.cross_sm_offset_from_md, 0),
        ( hw/2 + cfg.cross_lg_offset + cfg.cross_md_offset_from_lg + cfg.cross_sm_offset_from_md, 0),
        (0,  hh/2 + cfg.cross_lg_offset + cfg.cross_md_offset_from_lg + cfg.cross_sm_offset_from_md),
    ]
    
    _add_cross_scale(lib, cell, lg_positions, cross_lg, square_lg, cfg.square_lg_inset)

    # ── Medium scale (above top large marker only) ─────────────────────────────
    cross_md  = make_cross_marker(lib, "CROSS_MD",  cfg.cross_md_length, cfg.cross_md_width)
    square_md = make_square_marker(lib, "SQUARE_MD", cfg.square_md_size)

    _add_cross_scale(lib, cell, md_positions, cross_md, square_md, cfg.square_md_inset)

    # ── Small scale ────────────────────────────────────────────────────────────
    cross_sm  = make_cross_marker(lib, "CROSS_SM",  cfg.cross_sm_length, cfg.cross_sm_width)
    square_sm = make_square_marker(lib, "SQUARE_SM", cfg.square_sm_size)

    _add_cross_scale(lib, cell, sm_positions, cross_sm, square_sm, cfg.square_sm_inset)


def _add_L_pads(lib: gdstk.Library,
                cell: gdstk.Cell,
                cfg: WaferConfig) -> None:
    """
    Places stepped L-shaped pads at the four cardinal positions of the chip array,
    each rotated and reflected to face inward.
    """
    L_cell = make_L_shaped_wafer_pad(
        lib,
        heights=(cfg.L_pad_height1, cfg.L_pad_height2, cfg.L_pad_height3),
        lengths=(cfg.L_pad_length1, cfg.L_pad_length2, cfg.L_pad_length3),
    )
    hw, hh = _array_dimensions(cfg)

    for p in (1, -1):
        state = 0 if p == 1 else 1

        # Right
        cell.add(gdstk.Reference(L_cell,
            origin=(hw/2 + cfg.L_pad_v_offset, p * cfg.L_pad_h_offset),
            x_reflection=bool(state)))
        cell.add(gdstk.Reference(L_cell,
            origin=(hw/2 + cfg.L_pad_v_offset, p * cfg.L_pad_h_offset),
            rotation=p * np.pi/2, x_reflection=not bool(state)))

        # Left
        cell.add(gdstk.Reference(L_cell,
            origin=(-hw/2 - cfg.L_pad_v_offset, p * cfg.L_pad_h_offset),
            rotation=np.pi, x_reflection=not bool(state)))
        cell.add(gdstk.Reference(L_cell,
            origin=(-hw/2 - cfg.L_pad_v_offset, p * cfg.L_pad_h_offset),
            rotation=p * np.pi/2, x_reflection=bool(state)))

        # Top
        cell.add(gdstk.Reference(L_cell,
            origin=(p * cfg.L_pad_h_offset, hh/2 + cfg.L_pad_v_offset),
            rotation=bool(state) * np.pi, x_reflection=bool(state)))
        cell.add(gdstk.Reference(L_cell,
            origin=(p * cfg.L_pad_h_offset, hh/2 + cfg.L_pad_v_offset),
            rotation=np.pi/2, x_reflection=not bool(state)))

        # Bottom
        cell.add(gdstk.Reference(L_cell,
            origin=(p * cfg.L_pad_h_offset, -hh/2 - cfg.L_pad_v_offset),
            x_reflection=not bool(state), rotation=bool(state) * np.pi))

def _draw_wafer_label(cell: gdstk.Cell,
                      txt: str,
                      size: float,
                      origin: tuple[float, float]) -> None:
    """
    Renders multi-line text centred on *origin*.
    Each line is individually x-centred. Lines stack top-to-bottom.
    """
    layer        = LAYERS["wafer_id"]
    scale        = size / 1000.0
    cx, cy       = origin
    lines        = txt.split("\n")
    line_spacing = size * 1.5
    y_top        = cy + line_spacing * (len(lines) - 1) / 2

    for i, line in enumerate(lines):
        if not line:
            continue
        line_width = sum(
            (_width.get(ord(c), 500) + _indent.get(ord(c), 0)) * scale
            for c in line if c != " "
        ) + sum(500 * scale for c in line if c == " ")

        deplof_text(cell, line, size=size,
                    origin=(cx - line_width / 2, y_top - i * line_spacing),
                    layer=layer)


# =============================================================================
# PUBLIC API
# =============================================================================

def build_wafer_mask(lib: gdstk.Library,
                     cfg: WaferConfig,
                     cell_name: str = "WAFER",
                     chiplet_builder=None,
                     chiplet_cell_prefix: str = "CHIPLET",
                     wafer_ID_str: str = "",
                     add_date: bool = True) -> gdstk.Cell:
    """
    Assembles and returns the top-level wafer cell.

    Parameters
    ----------
    lib                 : gdstk.Library
    cfg                 : WaferConfig
    cell_name           : GDS cell name for the wafer top cell
    chiplet_builder     : callable(lib, chip_cfg, cell_name) → gdstk.Cell
                          Defaults to build_chiplet_mask.
    chiplet_cell_prefix : prefix for per-chiplet cell names
    wafer_ID_str        : string rendered as the main wafer label
    add_date            : whether to append today's date to the lab label

    Returns
    -------
    gdstk.Cell
    """
    if chiplet_builder is None:
        chiplet_builder = build_chiplet_mask

    wafer_cell = lib.new_cell(cell_name)

    if cfg.draw_boundary:
        wafer_cell.add(gdstk.ellipse(
            (0, 0), cfg.wafer_diameter / 2,
            **LAYERS["wafer_boundary"]
        ))

    # Place chiplets
    positions = _compute_chip_positions(
        cfg.row_config, cfg.chiplet.chip_width, cfg.chiplet.chip_height)

    for x_centre, y_centre, chiplet_number in positions:
        chip_cfg = cfg.chiplet.__class__(
            **{**cfg.chiplet.to_dict(), "chiplet_number": chiplet_number}
        )
        chip_cell_name = f"{chiplet_cell_prefix}_{chiplet_number:02d}"
        existing   = next((c for c in lib.cells if c.name == chip_cell_name), None)
        chip_cell  = existing or chiplet_builder(lib, chip_cfg, cell_name=chip_cell_name)
        wafer_cell.add(gdstk.Reference(chip_cell, origin=(x_centre, y_centre)))

    # Wafer-level features
    _add_dicing_lanes(lib, wafer_cell, cfg)
    _add_alignment_markers(lib, wafer_cell, cfg)
    _add_L_pads(lib, wafer_cell, cfg)

    # Labels
    _draw_wafer_label(wafer_cell, wafer_ID_str,
                      size=cfg.wafer_label_ID_size,
                      origin=(cfg.wafer_label_ID_x_pos, cfg.wafer_label_ID_y_pos))

    lab_label = f"STI-IEM-LANES\nPrepared by {USER_ID}"
    if add_date:
        lab_label += "\n" + datetime.today().strftime("%Y-%m-%d")
    _draw_wafer_label(wafer_cell, lab_label,
                      size=cfg.wafer_small_label_size,
                      origin=(cfg.wafer_small_label_xpos, cfg.wafer_small_label_ypos))

    return wafer_cell


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a standard wafer mask.")
    parser.add_argument("--edit", action="store_true",
                        help="Edit mode — does not consume a run number.")
    args = parser.parse_args()

    if args.edit:
        run_num, wafer_num = 0, 0
        stem = "STD-EDIT-MODE"
    else:
        run_num, wafer_num = next_wafer("STD")
        stem = f"STD-R{run_num:02d}-W{wafer_num:02d}"

    wafer_cfg = WaferConfig(
        run_number   = run_num,
        wafer_number = wafer_num,
        chiplet      = ChipletConfig(grid_style="excel"),
    )

    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_wafer_mask(lib, wafer_cfg, wafer_ID_str=stem)
    lib.write_gds(gds_path)
    wafer_cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"Written: {cfg_path}")
    print(f"  Wafer diameter:  {wafer_cfg.wafer_diameter/1000:.0f} mm")
    print(f"  Run number:      {wafer_cfg.run_number}")
    print(f"  Wafer number:    {wafer_cfg.wafer_number:02d}")
    print(f"  Wafer ID:        {stem}")
    print(f"  Row config:      {wafer_cfg.row_config}  (bottom to top)")
    print(f"  Total chips:     {sum(wafer_cfg.row_config)}")
    print(f"  Chip size:       {wafer_cfg.chiplet.chip_width/1000:.1f} x "
          f"{wafer_cfg.chiplet.chip_height/1000:.1f} mm")
    print(f"  Grid style:      {wafer_cfg.chiplet.grid_style}")