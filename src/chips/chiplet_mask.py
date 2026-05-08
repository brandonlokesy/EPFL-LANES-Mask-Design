"""
chiplet_mask.py
===============
Standard chiplet mask containing:
  - Chip boundary and active-area annotation
  - Corner markers (2x2 / 2x1x2 / 3x3 square arrays)
  - Big pad markers (square + L-shaped)
  - Small top pad array
  - Rectangular pad array
  - Position marker grid (matrix / excel / binary label styles)
  - Block-letter chiplet ID number

Usage:
    from src.chips.chiplet_mask import ChipletConfig, build_chiplet_mask
    import gdstk

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cfg  = ChipletConfig(chiplet_number=1)
    cell = build_chiplet_mask(lib, cfg)
    lib.write_gds("chiplet_01.gds")
"""

import gdstk
import numpy as np
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from src.config.layers import LAYERS
from src.config.paths import STANDARD_DIR
from src.utils.deplof_font import deplof_text
from src.components.markers import (
    make_corner_marker,
    make_big_pad_square,
    make_big_pad_L,
    make_small_pad,
    make_rectangular_pad,
)
from src.components.verniers import VernierConfig, add_vernier_set, vernier_set_width, vernier_set_height


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ChipletConfig:
    # --- Chip dimensions ---
    chip_width:               float = 12000.0
    chip_height:              float = 12000.0

    # --- Corner markers ---
    corner_marker_style:      str   = "3x3"       # "2x2" | "3x3" | "2x1x2"
    marker_x_size:            float = 50.0
    marker_x_width:           float = 10.0
    corner_sq_size:           float = 20.0
    corner_sq_gap:            float = 180.0
    corner_margin:            float = 1000.0

    # --- Big pad markers ---
    pad_sq_size:              float = 500.0
    pad_sq_margin:            float = 1750.0
    pad_L_margin:             float = 2000.0      # reserved
    pad_L_length:             float = 1000.0

    # --- Position marker grid ---
    grid_rows:                int   = 31
    grid_cols:                int   = 31
    grid_spacing:             float = 250.0
    grid_inset:               float = 250.0
    grid_marker_size:         float = 5.0
    grid_style:               str   = "excel"     # "matrix" | "excel" | "binary"
    pos_text_size:            float = 26.0
    bin_sq_size:              float = 10.0
    bin_rect_w:               float = 10.0
    bin_rect_h:               float = 20.0

    # --- Top pad array ---
    top_pads_size:            float = 10.0
    top_pads_margin:          float = 445.0       # reserved
    top_pads_number_sq:       int   = 15
    top_pads_spacing:         float = 70.0

    # --- Rectangular pad array ---
    rec_pad_length:           float = 100.0
    rec_pad_width:            float = 40.0
    rec_pad_margin_from_big_pad: float = 450.0
    rec_pad_gap:              float = 400.0

    # --- Chiplet ID label ---
    chiplet_id:               int   = 1           # used for GDS cell name only
    chiplet_number:           int   = 0           # printed on chip
    chiplet_id_text_size:     float = 1400.0
    chiplet_id_stroke_ratio:  float = 0.12
    chiplet_id_char_w_ratio:  float = 0.6
    chiplet_id_gap_ratio:     float = 0.15
    chiplet_id_chamfer_ratio: float = 0.35
    chiplet_id_centre_y:      float = 1250.0

    # --- Misc ---
    draw_boundary:            bool  = True
    draw_active_area:         bool  = True

    # --- Verniers ---
    draw_verniers:            bool  = False      # set False to suppress all verniers
    vernier_bar_length:       float = 50.0       # um
    vernier_bar_width:        float = 3.0        # um
    vernier_pitch_ref:        float = 10.0       # um — reference grating pitch
    vernier_pitch_delta:      float = 1.0        # um — pitch difference = resolution
    vernier_n_bars:           int   = 5          # bars per side (total = 2n+1)
    vernier_grating_gap:      float = 10.0       # um — gap between ref and aligned gratings
    vernier_pair_gap:         float = 20.0       # um — gap between H and V in a pair
    vernier_group_gap:        float = 40.0       # um — gap between exposure groups
    vernier_label_size:       float = 20.0       # um — DEPLOF label height
    vernier_label_gap:        float = 8.0        # um — gap between pair and label

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ChipletConfig":
        with open(Path(path)) as f:
            return cls(**json.load(f))


# =============================================================================
# BLOCK LETTER DIGIT FONT
# =============================================================================
#
# Each digit is a hollow block outline:
#   outer boundary  MINUS  inner cutout(s)  via gdstk.boolean("not")
#
# All coordinates are normalised to a unit grid (x,y ∈ [0,1]) and scaled
# to (char_w, char_h) at draw time.
#
# sw  = stroke_width
# c   = outer chamfer size
# ci  = inner chamfer size  (= c * 0.5)

def _chamfer_poly(x0: float, y0: float,
                  x1: float, y1: float,
                  c_tl: float, c_tr: float,
                  c_br: float, c_bl: float) -> gdstk.Polygon:
    """
    Rectangle with independent 45° chamfers on each corner.
    Pass 0 for a sharp (unchamfered) corner.
    """
    pts = []
    if c_bl > 0:
        pts += [(x0 + c_bl, y0), (x0, y0 + c_bl)]
    else:
        pts += [(x0, y0)]
    if c_tl > 0:
        pts += [(x0, y1 - c_tl), (x0 + c_tl, y1)]
    else:
        pts += [(x0, y1)]
    if c_tr > 0:
        pts += [(x1 - c_tr, y1), (x1, y1 - c_tr)]
    else:
        pts += [(x1, y1)]
    if c_br > 0:
        pts += [(x1, y0 + c_br), (x1 - c_br, y0)]
    else:
        pts += [(x1, y0)]
    return gdstk.Polygon(pts)


def _draw_digit(cell: gdstk.Cell, digit: str,
                x0: float, y0: float,
                char_w: float, char_h: float,
                stroke_w: float, chamfer: float,
                layer: dict) -> None:
    """
    Draws a single block-letter digit as a hollow chamfered outline.
    Uses gdstk.boolean("not") so there is no double-exposure — correct
    for lithographic masks.
    """
    if digit not in "0123456789":
        return

    lp  = {"layer": layer["layer"], "datatype": layer["datatype"]}
    sw  = stroke_w
    c   = chamfer
    ci  = chamfer * 0.5
    W   = char_w
    H   = char_h

    def outer():
        return _chamfer_poly(x0, y0, x0+W, y0+H, c, c, c, c)

    def inner_box(left=True, right=True, top=True, bottom=True):
        ix0 = x0 + sw  if left   else x0 - sw
        ix1 = x0+W-sw  if right  else x0+W+sw
        iy0 = y0 + sw  if bottom else y0 - sw
        iy1 = y0+H-sw  if top    else y0+H+sw
        c_tl = ci if (left  and top)    else 0
        c_tr = ci if (right and top)    else 0
        c_br = ci if (right and bottom) else 0
        c_bl = ci if (left  and bottom) else 0
        return _chamfer_poly(ix0, iy0, ix1, iy1, c_tl, c_tr, c_br, c_bl)

    def hbar(yb, yt):
        return _chamfer_poly(x0, yb, x0+W, yt, ci, ci, ci, ci)

    mid   = y0 + H * 0.5
    midy0 = mid - sw * 0.5
    midy1 = mid + sw * 0.5

    if digit == "0":
        result = gdstk.boolean([outer()], [inner_box()], "not", **lp)

    elif digit == "1":
        result = gdstk.boolean(
            [_chamfer_poly(x0+W-sw, y0, x0+W, y0+H, c, c, c, c)], [], "or", **lp)

    elif digit == "2":
        top_bar = _chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        r_upper = _chamfer_poly(x0+W-sw, midy1, x0+W, y0+H-sw, 0, 0, 0, 0)
        mid_bar = _chamfer_poly(x0, midy0, x0+W, midy1, c, 0, 0, 0)
        l_lower = _chamfer_poly(x0, y0+sw, x0+sw, midy0, 0, 0, 0, 0)
        bot_bar = _chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, r_upper, mid_bar, l_lower, bot_bar], [], "or", **lp)

    elif digit == "3":
        top_bar = _chamfer_poly(x0, y0+H-sw, x0+W, y0+H, ci, c, c, ci)
        r_vert  = _chamfer_poly(x0+W-sw, y0, x0+W, y0+H, ci, ci, ci, ci)
        mid_bar = hbar(midy0, midy1)
        bot_bar = _chamfer_poly(x0, y0, x0+W, y0+sw, c, ci, ci, c)
        result  = gdstk.boolean([top_bar, r_vert, mid_bar, bot_bar], [], "or", **lp)

    elif digit == "4":
        l_upper = _chamfer_poly(x0, midy0, x0+sw, y0+H, c, ci, ci, ci)
        mid_bar = hbar(midy0, midy1)
        r_vert  = _chamfer_poly(x0+W-sw, y0, x0+W, y0+H, c, c, c, c)
        result  = gdstk.boolean([l_upper, mid_bar, r_vert], [], "or", **lp)

    elif digit == "5":
        top_bar = _chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        l_upper = _chamfer_poly(x0, midy1, x0+sw, y0+H-sw, 0, 0, 0, 0)
        mid_bar = _chamfer_poly(x0, midy0, x0+W, midy1, 0, 0, 0, 0)
        r_lower = _chamfer_poly(x0+W-sw, y0+sw, x0+W, midy0, 0, 0, 0, 0)
        bot_bar = _chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, l_upper, mid_bar, r_lower, bot_bar], [], "or", **lp)

    elif digit == "6":
        top_bar = _chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        l_vert  = _chamfer_poly(x0, y0, x0+sw, y0+H, 0, 0, 0, 0)
        mid_bar = _chamfer_poly(x0+sw, midy0, x0+W, midy1, 0, c, 0, 0)
        r_lower = _chamfer_poly(x0+W-sw, y0+sw, x0+W, midy0, 0, 0, 0, 0)
        bot_bar = _chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, l_vert, mid_bar, r_lower, bot_bar], [], "or", **lp)

    elif digit == "7":
        top_bar = _chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, ci, ci)
        r_vert  = _chamfer_poly(x0+W-sw, y0, x0+W, y0+H, ci, ci, c, c)
        result  = gdstk.boolean([top_bar, r_vert], [], "or", **lp)

    elif digit == "8":
        win_h     = (H - 3*sw) / 2
        mid_y0    = y0 + sw + win_h
        mid_y1    = mid_y0 + sw
        upper_cut = _chamfer_poly(x0+sw, mid_y1,  x0+W-sw, y0+H-sw, ci, ci, ci, ci)
        lower_cut = _chamfer_poly(x0+sw, y0+sw,   x0+W-sw, mid_y0,  ci, ci, ci, ci)
        mid_bar   = _chamfer_poly(x0,    mid_y0,  x0+W,    mid_y1,   0,  0,  0,  0)
        shell  = gdstk.boolean([outer()], [upper_cut, lower_cut], "not", **lp)
        result = gdstk.boolean(shell, [mid_bar], "or", **lp)

    elif digit == "9":
        top_half  = _chamfer_poly(x0, midy0, x0+W, y0+H, c, c, ci, ci)
        inner_top = _chamfer_poly(x0+sw, midy1, x0+W-sw, y0+H-sw, ci, ci, ci, ci)
        r_lower   = _chamfer_poly(x0+W-sw, y0, x0+W, midy1, ci, ci, ci, ci)
        bot_bar   = _chamfer_poly(x0, y0, x0+W, y0+sw, c, ci, ci, c)
        result    = gdstk.boolean([top_half, r_lower, bot_bar], [inner_top], "not", **lp)

    for poly in result:
        cell.add(poly)


def _draw_chiplet_number(cell: gdstk.Cell,
                         number: int,
                         cfg: ChipletConfig) -> None:
    """
    Draws the chiplet number (0–99) as a zero-padded block-letter label,
    horizontally centred at x=0, vertically at -chip_height/2 + chiplet_id_centre_y.
    """
    label    = f"{number:02d}"
    char_h   = cfg.chiplet_id_text_size
    char_w   = char_h * cfg.chiplet_id_char_w_ratio
    stroke_w = char_h * cfg.chiplet_id_stroke_ratio
    gap      = char_h * cfg.chiplet_id_gap_ratio
    chamfer  = stroke_w * cfg.chiplet_id_chamfer_ratio

    n       = len(label)
    total_w = n * char_w + (n - 1) * gap

    cx = 0.0
    cy = -cfg.chip_height / 2 + cfg.chiplet_id_centre_y
    x0 = cx - total_w / 2
    y0 = cy - char_h  / 2

    for i, ch in enumerate(label):
        _draw_digit(cell, ch,
                    x0 + i * (char_w + gap), y0,
                    char_w, char_h, stroke_w, chamfer,
                    LAYERS["chiplet_id"])


# =============================================================================
# INTERNAL BUILDERS
# =============================================================================

def _add_corner_markers(cell: gdstk.Cell,
                        lib: gdstk.Library,
                        cfg: ChipletConfig) -> None:
    """Places one corner marker reference at each of the four chip corners."""
    cm_cell = make_corner_marker(lib, cfg.corner_sq_size,
                                 cfg.corner_sq_gap, cfg.corner_marker_style)
    hw    = cfg.chip_width  / 2
    hh    = cfg.chip_height / 2
    inset = cfg.corner_margin

    for cx, cy in [(-hw+inset, -hh+inset), ( hw-inset, -hh+inset),
                   (-hw+inset,  hh-inset), ( hw-inset,  hh-inset)]:
        cell.add(gdstk.Reference(cm_cell, origin=(cx, cy)))


def _add_big_pads(cell: gdstk.Cell,
                  lib: gdstk.Library,
                  cfg: ChipletConfig) -> None:
    """Places 3 square pads and 1 L-shaped pad at the chip corners."""
    sq_cell = make_big_pad_square(lib, cfg.pad_sq_size)
    l_cell  = make_big_pad_L(lib, cfg.pad_sq_size, cfg.pad_L_length)

    hw    = cfg.chip_width  / 2
    hh    = cfg.chip_height / 2
    inset = cfg.pad_sq_margin

    for cx, cy in [( hw-inset, -hh+inset),
                   (-hw+inset,  hh-inset),
                   ( hw-inset,  hh-inset)]:
        cell.add(gdstk.Reference(sq_cell, origin=(cx, cy)))

    cell.add(gdstk.Reference(
        l_cell,
        origin=(-hw + inset - cfg.pad_sq_size/2,
                -hh + inset - cfg.pad_sq_size/2)
    ))


def _add_top_pad_array(cell: gdstk.Cell,
                       lib: gdstk.Library,
                       cfg: ChipletConfig) -> None:
    """
    Places a top_pads_number_sq × top_pads_number_sq array of small pads,
    horizontally centred at x=0 and vertically at hh − corner_margin.
    """
    pad_cell = make_small_pad(lib, cfg.top_pads_size)

    size  = cfg.top_pads_size
    gap   = cfg.top_pads_spacing
    pitch = size + gap
    n     = cfg.top_pads_number_sq

    total_w = n * size + (n - 1) * gap
    total_h = n * size + (n - 1) * gap

    cx = 0.0
    cy = cfg.chip_height / 2 - cfg.corner_margin
    x0 = cx - total_w / 2 + size / 2
    y0 = cy - total_h / 2 + size / 2

    for row in range(n):
        for col in range(n):
            cell.add(gdstk.Reference(pad_cell,
                                     origin=(x0 + col * pitch,
                                             y0 + row * pitch)))


def _add_rectangular_pad_array(cell: gdstk.Cell,
                               lib: gdstk.Library,
                               cfg: ChipletConfig) -> None:
    """Adds vertical pads along the left edge and horizontal pads along the bottom edge."""
    v_pad = make_rectangular_pad(lib, cfg.rec_pad_length, cfg.rec_pad_width, "vertical")
    h_pad = make_rectangular_pad(lib, cfg.rec_pad_length, cfg.rec_pad_width, "horizontal")

    pitch = cfg.rec_pad_gap + cfg.rec_pad_length
    hw    = cfg.chip_width  / 2
    hh    = cfg.chip_height / 2

    # Vertical pads — left edge, top-to-bottom
    top_left_x = -hw + cfg.pad_sq_margin
    top_left_y =  hh - cfg.pad_sq_margin
    for i in range(14):
        cell.add(gdstk.Reference(
            v_pad,
            origin=(top_left_x + cfg.pad_sq_size/2 - cfg.rec_pad_width/2,
                    top_left_y - cfg.pad_sq_size/2 - cfg.rec_pad_margin_from_big_pad - i * pitch)
        ))

    # Horizontal pads — bottom edge, left-to-right (skip indices 4–8)
    skip = set(range(4, 9))
    bot_left_x = -hw + cfg.pad_sq_margin
    bot_left_y = -hh + cfg.pad_sq_margin
    for i in range(14):
        if i in skip:
            continue
        cell.add(gdstk.Reference(
            h_pad,
            origin=(bot_left_x + 3*cfg.pad_sq_size/2 + cfg.rec_pad_margin_from_big_pad + i * pitch,
                    bot_left_y + cfg.pad_sq_size/2 - cfg.rec_pad_width/2)
        ))


# =============================================================================
# POSITION GRID
# =============================================================================

def _excel_label(col: int) -> str:
    """Converts 0-based column index to Excel-style label: 0→A, 25→Z, 26→AA …"""
    label = ""
    n = col + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _draw_binary_marker(cell: gdstk.Cell,
                        cx: float, cy: float,
                        row: int, col: int,
                        cfg: ChipletConfig) -> None:
    """
    Binary position marker centred on (cx, cy).
    Row bits on top, column bits on bottom. MSB on left.
    0-bit = small square, 1-bit = tall rectangle.
    """
    n_bits  = 5
    sq_w    = cfg.bin_sq_size
    sq_h    = cfg.bin_sq_size
    rect_w  = cfg.bin_rect_w
    rect_h  = cfg.bin_rect_h
    lp      = LAYERS["pos_markers"]

    total_w = n_bits * rect_w
    row_h   = rect_h
    col_h   = rect_h
    ox      = cx - total_w / 2
    oy      = cy + (row_h + col_h) / 2

    for number, is_top in [(row, True), (col, False)]:
        bits = [(number >> (n_bits - 1 - i)) & 1 for i in range(n_bits)]
        for i, bit in enumerate(bits):
            bx     = ox + i * rect_w
            by_top = oy if is_top else oy - row_h / 2

            if bit == 1:
                if not is_top:
                    cell.add(gdstk.rectangle(
                        (bx, by_top - rect_h), (bx + rect_w, by_top), **lp))
                else:
                    cell.add(gdstk.rectangle(
                        (bx, by_top - sq_h), (bx + rect_w, by_top + rect_h - sq_h), **lp))
            else:
                x_off = (rect_w - sq_w) / 2
                cell.add(gdstk.rectangle(
                    (bx + x_off, by_top - sq_h),
                    (bx + x_off + sq_w, by_top), **lp))


def _add_position_grid(cell: gdstk.Cell, cfg: ChipletConfig) -> None:
    """
    Places a grid_rows × grid_cols array of position markers.
    Row 0 is at the top-left, increasing right and downward.
    Label style is controlled by cfg.grid_style.
    """
    hw = cfg.chip_width  / 2
    hh = cfg.chip_height / 2

    pad_outer_x = hw - cfg.pad_sq_margin - cfg.pad_sq_size / 2
    pad_outer_y = hh - cfg.pad_sq_margin - cfg.pad_sq_size / 2

    x_start = -pad_outer_x + cfg.grid_inset
    y_start =  pad_outer_y - cfg.grid_inset
    sp      = cfg.grid_spacing
    style   = cfg.grid_style.lower()

    for row_idx in range(cfg.grid_rows):
        for col_idx in range(cfg.grid_cols):
            cx = x_start + col_idx * sp
            cy = y_start - row_idx * sp

            if style == "matrix":
                label = f"{row_idx:02d}p{col_idx:02d}"
                cell.add(*gdstk.text(
                    label, cfg.pos_text_size,
                    (cx - len(label) * cfg.pos_text_size * 0.6 / 2, cy),
                    **LAYERS["pos_markers"]
                ))

            elif style == "excel":
                label = f"{_excel_label(col_idx)}{row_idx}"
                deplof_text(cell, label,
                            size=cfg.pos_text_size,
                            origin=(cx - len(label) * cfg.pos_text_size * 0.6 / 2, cy),
                            layer=LAYERS["pos_markers"])

            elif style == "binary":
                _draw_binary_marker(cell, cx, cy, row_idx, col_idx, cfg)


def _add_verniers(cell: gdstk.Cell, cfg: ChipletConfig) -> None:
    """
    Places the vernier set in the bottom-right corner of the chip,
    in the margin band between the active area and the chip edge.

    The block is:
      - right-aligned to the active area right edge (with a safety margin)
      - vertically centred in the margin band between the active area
        bottom edge and the chip bottom edge
    """
    from src.config.layers import LAYERS as L

    vernier_cfg = VernierConfig(
        bar_length   = cfg.vernier_bar_length,
        bar_width    = cfg.vernier_bar_width,
        pitch_ref    = cfg.vernier_pitch_ref,
        pitch_delta  = cfg.vernier_pitch_delta,
        n_bars       = cfg.vernier_n_bars,
        grating_gap  = cfg.vernier_grating_gap,
        pair_gap     = cfg.vernier_pair_gap,
        group_gap    = cfg.vernier_group_gap,
        label_size   = cfg.vernier_label_size,
        label_gap    = cfg.vernier_label_gap,
        exposures    = [
            ("1", L["local_gates"]),
            ("2", L["top_gates"]),
            ("3", L["pos_markers"]),
        ],
    )

    hw = cfg.chip_width  / 2
    hh = cfg.chip_height / 2

    # Active area boundary
    inset         = cfg.pad_sq_margin + cfg.pad_sq_size / 2
    active_right  =  hw - inset
    active_bottom = -hh + inset

    # Bottom-right pad square centre
    pad_centre_x  =  hw - cfg.pad_sq_margin
    pad_centre_y  = -hh + cfg.pad_sq_margin
    pad_right     =  pad_centre_x + cfg.pad_sq_size / 2
    pad_top       =  pad_centre_y + cfg.pad_sq_size / 2

    v_width  = vernier_set_width(vernier_cfg)
    v_height = vernier_set_height(vernier_cfg)

    # Safety margin from both the active area edge and the pad square
    margin = 30.0   # um

    # Right-align to active area, but not closer than margin to the pad right edge
    origin_x = min(active_right - v_width,
                   pad_right    - v_width - margin)

    # Place in the band between active_bottom and chip bottom,
    # vertically centred, but not closer than margin above the pad top
    band_top    = active_bottom - margin
    band_bottom = -hh + margin
    origin_y    = max(band_bottom,
                      min(band_top - v_height,
                          pad_top + margin))

    add_vernier_set(cell, vernier_cfg, origin=(origin_x, origin_y))


# =============================================================================
# PUBLIC API
# =============================================================================

def build_chiplet_mask(lib: gdstk.Library,
                       cfg: ChipletConfig,
                       cell_name: str = None) -> gdstk.Cell:
    """
    Builds and returns a complete chiplet mask cell.

    Parameters
    ----------
    lib       : gdstk.Library to add the cell into
    cfg       : ChipletConfig
    cell_name : optional GDS cell name override;
                defaults to "CHIPLET_<chiplet_number:03d>"

    Returns
    -------
    gdstk.Cell — ready to be referenced in a parent layout
    """
    if cell_name is None:
        cell_name = f"CHIPLET_{cfg.chiplet_number:03d}"

    existing = next((c for c in lib.cells if c.name == cell_name), None)
    if existing:
        return existing

    cell = lib.new_cell(cell_name)

    # Annotation
    if cfg.draw_boundary:
        cell.add(gdstk.rectangle(
            (-cfg.chip_width/2,  -cfg.chip_height/2),
            ( cfg.chip_width/2,   cfg.chip_height/2),
            **LAYERS["chip_boundary"]
        ))

    # BUG FIX: original code used chip_width for both hw and hh in active area
    if cfg.draw_active_area:
        hw = cfg.chip_width  / 2
        hh = cfg.chip_height / 2
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        cell.add(gdstk.rectangle(
            (-hw + inset, -hh + inset),
            ( hw - inset,  hh - inset),
            **LAYERS["chip_active_area"]
        ))

    _add_corner_markers(cell, lib, cfg)
    _add_big_pads(cell, lib, cfg)
    _add_top_pad_array(cell, lib, cfg)
    _add_rectangular_pad_array(cell, lib, cfg)
    _add_position_grid(cell, cfg)
    _draw_chiplet_number(cell, cfg.chiplet_number, cfg)

    # if cfg.draw_verniers:
    #     _add_verniers(cell, cfg)

    return cell


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a standalone chiplet mask.")
    parser.add_argument("--edit", action="store_true", help="Edit mode — does not consume a run number.")
    args = parser.parse_args()

    cfg = ChipletConfig(chiplet_id=1, chiplet_number=7)

    STANDARD_DIR.mkdir(parents=True, exist_ok=True)
    stem     = "chiplet_EDIT" if args.edit else f"chiplet_{cfg.chiplet_id:03d}"
    gds_path = STANDARD_DIR / f"{stem}.gds"
    cfg_path = STANDARD_DIR / f"{stem}.json"

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    build_chiplet_mask(lib, cfg)
    lib.write_gds(gds_path)
    cfg.save(cfg_path)

    print(f"Written: {gds_path}")
    print(f"Written: {cfg_path}")
    print(f"  Chip size:      {cfg.chip_width} x {cfg.chip_height} um")
    print(f"  Chiplet ID:     {cfg.chiplet_id}")
    print(f"  Chiplet number: {cfg.chiplet_number:02d}")
    print(f"  Grid:           {cfg.grid_rows} rows x {cfg.grid_cols} cols")
    print(f"  Corner margin:  {cfg.corner_margin} um")