"""
photonic_chiplet_mask.py

Usage
-----
    python -m src.chips.photonic_chiplet_mask          # writes to masks/experimental/
    python -m src.chips.photonic_chiplet_mask --edit   # fixed filename for iteration
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path

import gdstk
import gdsfactory as gf

from src.config.layers import LAYERS
from src.config.paths import EXPERIMENTAL_DIR
from src.chips.layout_geometry import (
    corner_marker_positions,
    big_pad_square_positions,
    big_pad_L_origin,
    rectangular_pad_positions,
)
from src.utils.text import draw_chiplet_number
from src.components.photonics.technology import LAYER, _l
from src.components.photonics.rings import RingConfig, from_config as ring_from_config, make_ring_sweep
from src.components.photonics.gratings import GratingConfig, from_config as grating_from_config, make_gc_sweep
from src.components.photonics.mzi import MZIConfig, from_config as mzi_from_config, make_mzi_sweep


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PhotonicChipletConfig:
    """
    All parameters needed to reproduce the photonic chiplet.

    Infrastructure fields mirror ``ChipletConfig`` exactly so the shared
    helper functions (_add_corner_markers, etc.) work without modification.
    """

    # ── Chip dimensions ────────────────────────────────────────────────────
    chip_width:   float = 12000.0
    chip_height:  float = 12000.0

    # ── Corner markers (mirrors ChipletConfig) ─────────────────────────────
    corner_marker_style:  str   = "3x3"
    marker_x_size:        float = 50.0
    marker_x_width:       float = 10.0
    corner_sq_size:       float = 20.0
    corner_sq_gap:        float = 180.0
    corner_margin:        float = 1000.0

    # ── Big pad markers (mirrors ChipletConfig) ────────────────────────────
    pad_sq_size:          float = 500.0
    pad_sq_margin:        float = 1750.0
    pad_L_margin:         float = 2000.0
    pad_L_length:         float = 1000.0

    # ── Rectangular pad bars (mirrors ChipletConfig) ───────────────────────
    rec_pad_length:       float = 100.0
    rec_pad_width:        float = 40.0
    rec_pad_margin_from_big_pad: float = 450.0
    rec_pad_gap:          float = 400.0

    # ── Chiplet ID number (mirrors ChipletConfig) ──────────────────────────
    chiplet_number:           int   = 0
    chiplet_id_text_size:     float = 1400.0
    chiplet_id_stroke_ratio:  float = 0.12
    chiplet_id_char_w_ratio:  float = 0.6
    chiplet_id_gap_ratio:     float = 0.15
    chiplet_id_chamfer_ratio: float = 0.35
    chiplet_id_centre_y:      float = 1250.0

    # ── Annotation ─────────────────────────────────────────────────────────
    draw_boundary:  bool = True
    draw_active_area: bool = True

    # ── Global waveguide width ─────────────────────────────────────────────
    wg_width:       float = 0.8     # µm

    # ── Photonic device layout ─────────────────────────────────────────────
    row_spacing:    float = 200.0   # µm between bottom of one row and top of next
    block_gap:      float = 100.0   # µm between device blocks within a row

    # ── Row A: all-pass rings (radius sweep) ───────────────────────────────
    ap_radii:       list = field(default_factory=lambda: [5.0, 8.0, 10.0, 12.0, 15.0])
    ap_gap:         float = 0.15
    ap_spacing:     float = 55.0

    # ── Row B: add-drop rings (radius sweep) ──────────────────────────────
    ad_radii:       list = field(default_factory=lambda: [8.0, 10.0, 12.0])
    ad_gap:         float = 0.15
    ad_spacing:     float = 60.0

    # ── Row C: racetracks (coupling-length sweep) ─────────────────────────
    rt_radius:      float = 10.0
    rt_gaps:        list = field(default_factory=lambda: [3.0, 5.0, 10.0])
    rt_gap:         float = 0.15
    rt_spacing:     float = 70.0

    # ── Row D: MMI-MZI (delta_length sweep) ───────────────────────────────
    mmi_dls:        list = field(default_factory=lambda: [10.0, 25.0, 50.0, 100.0])
    mmi_spacing:    float = 120.0

    # ── Row E: DC-MZI (delta_length sweep) ────────────────────────────────
    dc_dls:         list = field(default_factory=lambda: [10.0, 50.0])
    dc_gap:         float = 0.20
    dc_cl:          float = 10.0
    dc_spacing:     float = 130.0

    # ── Row F: elliptical GC (neff sweep) ─────────────────────────────────
    gc_e_neff:      list = field(default_factory=lambda: [1.75, 1.85, 1.95])
    gc_e_nclad:     float = 1.443
    gc_e_wl:        float = 1.55
    gc_e_angle:     float = 10.0
    gc_e_spacing:   float = 60.0

    # ── Row G: rectangular GC (period sweep) ──────────────────────────────
    gc_r_periods:   list = field(default_factory=lambda: [0.88, 0.97, 1.05])
    gc_r_ff:        float = 0.5
    gc_r_spacing:   float = 250.0

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "PhotonicChipletConfig":
        with open(Path(path)) as f:
            return cls(**json.load(f))


# =============================================================================
# PHOTONIC DEVICE BUILDER  (gdsfactory)
# =============================================================================

def _make_corner_marker(sq_size: float, sq_gap: float, array: str = "3x3") -> gf.Component:
    c = gf.Component()
    half = sq_size / 2 + sq_gap / 2
    positions = {
        "2x2": [(-half, -half), ( half, -half), (-half,  half), ( half,  half)],
        "2x1x2": [(-half, -half), ( half, -half), (0, 0), (-half, half), ( half,  half)],
        "3x3": [
            (-2*half, -2*half), (0, -2*half), (2*half, -2*half),
            (-2*half,       0), (0,       0), (2*half,       0),
            (-2*half,  2*half), (0,  2*half), (2*half,  2*half),
        ],
    }
    if array not in positions:
        raise ValueError(f"Unknown array style '{array}'. Choose from: {list(positions)}")
    sq = sq_size / 2
    layer = _l("corner_markers")
    for ox, oy in positions[array]:
        c.add_polygon([(ox-sq, oy-sq), (ox+sq, oy-sq), (ox+sq, oy+sq), (ox-sq, oy+sq)], layer=layer)
    return c

def _add_corner_markers(c: gf.Component, cfg: PhotonicChipletConfig) -> None:
    marker = _make_corner_marker(cfg.corner_sq_size, cfg.corner_sq_gap, cfg.corner_marker_style)
    for cx, cy in corner_marker_positions(cfg.chip_width, cfg.chip_height, cfg.corner_margin):
        c.add_ref(marker).move((cx, cy))


def _make_big_pad_square(size: float) -> gf.Component:
    c = gf.Component()
    h = size / 2
    c.add_polygon([(-h, -h), (h, -h), (h, h), (-h, h)], layer=_l("pad_markers"))
    return c


def _make_big_pad_L(pad_size: float, arm_length: float) -> gf.Component:
    """L-shaped pad with inner corner at (0, 0), arms extending in +x and +y."""
    c = gf.Component()
    T, L = pad_size, arm_length
    c.add_polygon([(0,0),(L,0),(L,T),(T,T),(T,L),(0,L)], layer=_l("pad_markers"))
    return c


def _make_rectangular_pad(length: float, width: float, orientation: str) -> gf.Component:
    c = gf.Component()
    if orientation == "horizontal":
        c.add_polygon([(-length/2,-width/2),(length/2,-width/2),(length/2,width/2),(-length/2,width/2)], layer=_l("pad_markers"))
    else:
        c.add_polygon([(-width/2,-length/2),(width/2,-length/2),(width/2,length/2),(-width/2,length/2)], layer=_l("pad_markers"))
    return c


def _add_big_pads(c: gf.Component, cfg: PhotonicChipletConfig) -> None:
    """Places 3 square pads and 1 L-shaped pad at the chip corners."""
    sq    = _make_big_pad_square(cfg.pad_sq_size)
    l_pad = _make_big_pad_L(cfg.pad_sq_size, cfg.pad_L_length)

    for cx, cy in big_pad_square_positions(cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin):
        c.add_ref(sq).move((cx, cy))

    c.add_ref(l_pad).move(
        big_pad_L_origin(cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin, cfg.pad_sq_size)
    )


def _add_rectangular_pad_array(c: gf.Component, cfg: PhotonicChipletConfig) -> None:
    """Vertical pads along the left edge, horizontal pads along the bottom edge."""
    v_pad = _make_rectangular_pad(cfg.rec_pad_length, cfg.rec_pad_width, "vertical")
    h_pad = _make_rectangular_pad(cfg.rec_pad_length, cfg.rec_pad_width, "horizontal")

    v_positions, h_positions = rectangular_pad_positions(
        cfg.chip_width, cfg.chip_height, cfg.pad_sq_margin, cfg.pad_sq_size,
        cfg.rec_pad_length, cfg.rec_pad_width, cfg.rec_pad_margin_from_big_pad, cfg.rec_pad_gap,
    )
    for pos in v_positions:
        c.add_ref(v_pad).move(pos)
    for pos in h_positions:
        c.add_ref(h_pad).move(pos)


def build_photonic_chiplet_mask(
    cfg: PhotonicChipletConfig,
    cell_name = "PHOTONIC_CHIPLET",
):
    c = gf.Component()
    
    if cfg.draw_boundary:
        bg = c << gf.components.rectangle(size=(cfg.chip_width, cfg.chip_height), layer=LAYERS["chip_boundary"]["layer"], centered=True)

    if cfg.draw_active_area:
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        aa = c << gf.components.rectangle(size=(cfg.chip_width - 2*inset, cfg.chip_height - 2*inset), layer=LAYERS["chip_active_area"]["layer"], centered=True)
    
    _add_corner_markers(c, cfg)
    _add_big_pads(c, cfg)
    _add_rectangular_pad_array(c, cfg)

    return c

if "__main__" == __name__:
    cfg = PhotonicChipletConfig()
    c = build_photonic_chiplet_mask(cfg)
    c.show()
