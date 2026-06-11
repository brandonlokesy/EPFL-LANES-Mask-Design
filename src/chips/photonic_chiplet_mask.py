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
from src.components.photonics.technology import LAYER, CROSS_SECTIONS, _l
from src.components.photonics.pulley import pulley_with_leads


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

    # ── Process / cross-section ────────────────────────────────────────────
    cross_section:  str   = "SIN_VIS"   # key into technology.CROSS_SECTIONS

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

    # ── Row H: pulley coupler ──────────────────────────────────────────────
    pulley_radius:        float = 5.0
    pulley_gap:           float = 0.3
    pulley_coupling_angle: float = 20.0   # degrees → controls coupling length
    pulley_extend_leads:  float = 10.0
    pulley_wg_length :    float = 75.0
    pulley_wg_height :    float = 1.0
    pulley_ring_width :   float = 0.5
    pulley_n_segments:    int   = 2048    # high value closes the polygon gap in coupler_pulley

    # ── Pulley array (3×3 dose test) ──────────────────────────────────────
    pulley_array_col_pitch:  float = 300.0   # µm — tune after checking device bbox
    pulley_array_row_pitch:  float = 500.0   # µm — tune after checking device bbox
    pulley_array_label_size: float = 15.0    # µm text height

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
    c = gf.Component(f"CORNER_MARKER_{array}")
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
    c = gf.Component("BIG_PAD_SQUARE")
    h = size / 2
    c.add_polygon([(-h, -h), (h, -h), (h, h), (-h, h)], layer=_l("pad_markers"))
    return c


def _make_big_pad_L(pad_size: float, arm_length: float) -> gf.Component:
    """L-shaped pad with inner corner at (0, 0), arms extending in +x and +y."""
    c = gf.Component("BIG_PAD_L")
    T, L = pad_size, arm_length
    c.add_polygon([(0,0),(L,0),(L,T),(T,T),(T,L),(0,L)], layer=_l("pad_markers"))
    return c


def _make_rectangular_pad(length: float, width: float, orientation: str) -> gf.Component:
    c = gf.Component(f"RECTANGULAR_PAD_{orientation.upper()}")
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


def _chiplet_number_component(number: int, cfg) -> gf.Component:
    """Adapter: renders the gdstk chiplet-number label into a gf.Component."""
    tmp_cell = gdstk.Library().new_cell("_tmp")
    draw_chiplet_number(tmp_cell, number, cfg)
    c = gf.Component("CHIPLET_ID")
    for poly in tmp_cell.polygons:
        c.add_polygon(poly.points, layer=_l("chiplet_id"))
    return c


def build_photonic_chiplet_mask(
    cfg: PhotonicChipletConfig,
    cell_name: str = None,
):
    if cell_name is None:
        cell_name = f"PHOTONIC_CHIPLET_{cfg.chiplet_number:03d}"
    c = gf.Component(cell_name)
    
    if cfg.draw_boundary:
        bg = c << gf.components.rectangle(size=(cfg.chip_width, cfg.chip_height), layer=LAYERS["chip_boundary"]["layer"], centered=True)

    if cfg.draw_active_area:
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        aa = c << gf.components.rectangle(size=(cfg.chip_width - 2*inset, cfg.chip_height - 2*inset), layer=LAYERS["chip_active_area"]["layer"], centered=True)
    
    _add_corner_markers(c, cfg)
    _add_big_pads(c, cfg)
    _add_rectangular_pad_array(c, cfg)
    c.add_ref(_chiplet_number_component(cfg.chiplet_number, cfg))

    xs = CROSS_SECTIONS[cfg.cross_section]

    grating_coupler_settings_dict = dict(
        polarization="te",
        wavelength=0.75,          # µm, not nm
        fiber_angle=20.0,         # degrees from normal
        neff=1.6,                 # SiN @ 750 nm — tune from simulation
        nclad=1.46,               # SiO2 @ 750 nm (slightly higher than 1550 nm value)
        grating_line_width=0.18,  # ~half the period for 50% duty cycle
        taper_length=20.0,
        taper_angle=40.0,         # flare angle — wider = easier fiber alignment
        n_periods=30,
        layer_slab=None,          # set to None unless you have a slab etch layer
        cross_section=xs,
    )

    bends_settings_dict = dict(
        dict(angle = 180, radius = 30)
    )
    # Build device once — @gf.cell caches it, all 9 placements share the same master cell
    device = pulley_with_leads(
        pulley=dict(
            component="coupler_pulley",
            settings=dict(
                radius=cfg.pulley_radius,
                gap=cfg.pulley_gap,
                coupling_angle=cfg.pulley_coupling_angle,
                wg_length=cfg.pulley_wg_length,
                wg_height=cfg.pulley_wg_height,
                ring_width=cfg.pulley_ring_width,
                n_segments=cfg.pulley_n_segments,
                cross_section=xs,
                layer=LAYER.RING,
            ),
        ),
        extend_ports_length=cfg.pulley_extend_leads,
        bends={
            "o1": dict(component="bend_euler", settings=bends_settings_dict),
            "o2": dict(component="bend_euler", settings=bends_settings_dict),
        },
        terminations={
            "o1": dict(component="grating_coupler_elliptical", settings=grating_coupler_settings_dict),
            "o2": dict(component="grating_coupler_elliptical", settings=grating_coupler_settings_dict),
        },
        cross_section=xs,
    )

    # y of label anchor: just below device bottom edge
    label_y_offset = device.bbox().bottom - cfg.pulley_array_label_size

    for row in range(3):
        for col in range(3):
            x = (col - 1) * cfg.pulley_array_col_pitch
            y = (row - 1) * cfg.pulley_array_row_pitch

            (c << device).move((x, y))

            lbl = c << gf.components.text(
                text=f"R{row}C{col}",
                size=cfg.pulley_array_label_size,
                layer=LAYER.NOTES,
            )
            lbl.move((x, y + label_y_offset))

    return c

if "__main__" == __name__:
    gf.gpdk.PDK.activate()
    cfg = PhotonicChipletConfig()
    c = build_photonic_chiplet_mask(cfg)
    EXPERIMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    # stem     = "chiplet_test_EDIT" if args.edit else f"chiplet_test_{cfg.chiplet_id:03d}"
    stem = "photonic_chiplet_test"
    gds_path = EXPERIMENTAL_DIR / f"{stem}.gds"
    cfg_path = EXPERIMENTAL_DIR / f"{stem}.json"
    c.write_gds(gds_path)
    cfg.save(cfg_path)
    print(f"GDS  → {gds_path}")
    print(f"JSON → {cfg_path}")
    c.show()
