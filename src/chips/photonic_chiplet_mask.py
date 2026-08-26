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
from src.components.photonics.inverse_tone import (
    add_inverse_tone_zones,
    write_time_s,
    fmt_duration,
    ZONES_PER_SITE,
    ZONES_PER_FEATURE,
)


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
    pulley_wg_length :    float = 150
    pulley_wg_height :    float = 1.0
    pulley_ring_width :   float = 0.5
    pulley_n_segments:    int   = 2048    # high value closes the polygon gap in coupler_pulley

    # ── Pulley array (3×3 dose test) ──────────────────────────────────────
    pulley_array_col_pitch:  float = 500.0   # µm — tune after checking device bbox
    pulley_array_row_pitch:  float = 300.0   # µm — tune after checking device bbox
    pulley_array_label_size: float = 15.0    # µm text height

    # ── Inverse-tone (negative) exposure ──────────────────────────────────
    # Etch everything except the rings and waveguides, fractured into tiers so
    # the EBPG can write each at its own spot size. See inverse_tone.py.
    invert_tone:            bool  = False
    invert_coarse_extent:   str   = "chip"       # "chip" | "active_area"
    invert_bias:            float = 0.0          # µm — dilate surviving geometry
    # Exposure tiers, FINEST FIRST — list order is precedence. Each zone needs
    # its own layer so the EBPG job can give it its own spot / beam current.
    # ZONES_PER_FEATURE splits grating couplers, ring, routing and text apart.
    invert_zones:           list  = field(default_factory=lambda: list(ZONES_PER_SITE))
    # Protected geometry covered by no zone would have its edges written by the
    # coarse beam. That is an error unless you mean it.
    invert_allow_uncovered: bool  = False
    invert_protect_layers:  list  = field(default_factory=lambda: [
        "wg_core", "ring", "grating", "notes",   # "notes" keeps the device labels
    ])
    # MLA150 features are patterned in a later step — leave film islands under
    # them. Set to [] to clear the whole chip instead.
    invert_exclude_layers:  list  = field(default_factory=lambda: [
        "corner_markers", "pad_markers", "chiplet_id",
    ])
    invert_exclude_margin:  float = 20.0         # µm around excluded footprints
    invert_draw_frames:     bool  = True         # tier outlines on inv_frame (103)
    # GDSII caps an XY record at 8 KB = 1024 points. Subtracting the curved
    # devices from a box otherwise yields ~18000-vertex polygons, which the
    # writer emits as records a strict reader rejects. 0 disables the split.
    invert_max_vertices:    int   = 1024

    # Write-time estimate only — recorded for traceability, not geometry.
    # Per-tier currents live in invert_zones; this is the coarse tier's.
    invert_dose_uC_cm2:       float = 300.0
    invert_coarse_current_nA: float = 500.0

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


def coarse_extent_box(cfg: PhotonicChipletConfig) -> tuple:
    """Outer extent of the inverse-tone exposure, as (x0, y0, x1, y1) centred on (0, 0)."""
    if cfg.invert_coarse_extent == "chip":
        inset = 0.0
    elif cfg.invert_coarse_extent == "active_area":
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
    else:
        raise ValueError(
            "invert_coarse_extent must be 'chip' or 'active_area', "
            f"got {cfg.invert_coarse_extent!r}"
        )
    hw = cfg.chip_width / 2 - inset
    hh = cfg.chip_height / 2 - inset
    return (-hw, -hh, hw, hh)


def _add_inverse_tone_tiers(c: gf.Component,
                            cfg: PhotonicChipletConfig,
                            sites: list) -> dict:
    """
    Boolean the negative of the photonic pattern into tiers, and stash the
    summary on ``c.info`` so the entry point can report it.
    """
    summary = add_inverse_tone_zones(
        c,
        zones=cfg.invert_zones,
        sites=sites,
        coarse_box=coarse_extent_box(cfg),
        protect_layers=cfg.invert_protect_layers,
        exclude_layers=cfg.invert_exclude_layers,
        exclude_margin=cfg.invert_exclude_margin,
        bias=cfg.invert_bias,
        max_vertices=cfg.invert_max_vertices,
        frame_layer="inv_frame" if cfg.invert_draw_frames else None,
        allow_uncovered_pattern=cfg.invert_allow_uncovered,
    )
    for tier in summary["tiers"]:
        current = tier["nA"] or cfg.invert_coarse_current_nA
        tier["current_nA"] = current
        tier["time_s"] = write_time_s(
            tier["area_um2"], cfg.invert_dose_uC_cm2, current
        )
    c.info["inv_summary"] = json.dumps(summary)
    return summary


def print_inverse_tone_summary(cfg: PhotonicChipletConfig, summary: dict) -> None:
    tiers = summary["tiers"]
    total_area = sum(t["area_um2"] for t in tiers)
    total_time = sum(t["time_s"] for t in tiers)
    finest = min(t["current_nA"] for t in tiers)
    naive = write_time_s(total_area, cfg.invert_dose_uC_cm2, finest)

    print(f"  Inverse tone:    ON  ({len(tiers)} tiers, "
          f"coarse extent = {cfg.invert_coarse_extent})")
    print(f"    {'tier':<10}{'layer':>10}{'regions':>9}{'area':>12}"
          f"{'current':>10}{'time':>10}")
    for tier in tiers:
        layer = LAYERS[tier["layer"]]["layer"]
        print(f"    {tier['name']:<10}{tier['layer'] + f' ({layer})':>10}"
              f"{tier['n_regions']:>9d}{tier['area_um2']/1e6:>9.3f} mm^2"
              f"{tier['current_nA']:>8g} nA{fmt_duration(tier['time_s']):>10}")
    print(f"    {'TOTAL':<10}{'':>10}{'':>9}{total_area/1e6:>9.3f} mm^2"
          f"{'':>10}{fmt_duration(total_time):>10}")
    print(f"    vs single-tier at {finest:g} nA: {fmt_duration(naive)}")
    print(f"    surviving      {summary['protect_area_um2']/1e6:8.3f} mm^2 protected, "
          f"{summary['excluded_area_um2']/1e6:8.3f} mm^2 excluded")
    print(f"    polygons       max {summary['max_vertices_out']} vertices "
          f"(GDSII record limit is 1024)")
    print(f"    NOTE beam-on estimate at {cfg.invert_dose_uC_cm2:g} uC/cm^2; "
          f"excludes settling, stage moves and PEC.")


def build_photonic_chiplet_mask(
    cfg: PhotonicChipletConfig,
    cell_name: str = None,
):
    if cell_name is None:
        cell_name = f"PHOTONIC_CHIPLET_{cfg.chiplet_number:03d}"
    c = gf.Component(cell_name)
    
    if cfg.draw_boundary:
        bg = c << gf.components.rectangle(size=(cfg.chip_width, cfg.chip_height), layer=_l("chip_boundary"), centered=True)

    if cfg.draw_active_area:
        inset = cfg.pad_sq_margin + cfg.pad_sq_size / 2
        aa = c << gf.components.rectangle(size=(cfg.chip_width - 2*inset, cfg.chip_height - 2*inset), layer=_l("chip_active_area"), centered=True)
    
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

    bends_settings_dict_right = dict(
        dict(angle = 90, radius = 30)
    )
    bends_settings_dict_left = dict(
        dict(angle = -90, radius = 30)
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
            "o1": dict(component="bend_euler", settings=bends_settings_dict_left),
            "o2": dict(component="bend_euler", settings=bends_settings_dict_right),
        },
        terminations={
            "o1": dict(component="grating_coupler_elliptical", settings=grating_coupler_settings_dict),
            "o2": dict(component="grating_coupler_elliptical", settings=grating_coupler_settings_dict),
        },
        cross_section=xs,
    )

    # y of label anchor: just below device bottom edge
    label_y_offset = device.bbox().bottom - cfg.pulley_array_label_size * 6

    sites: list = []

    for row in range(3):
        for col in range(3):
            x = (col - 1) * cfg.pulley_array_col_pitch
            y = (row - 1) * cfg.pulley_array_row_pitch

            dev = c << device
            dev.move((x, y))

            lbl = c << gf.components.text(
                text=f"R{row}C{col}",
                size=cfg.pulley_array_label_size,
                layer=LAYER.NOTES,
            )
            lbl.move((x, y + label_y_offset))

            # Hand the zone selectors the references, not boxes: a zone may
            # want the whole site, or just this device's grating couplers.
            sites.append({"device": dev, "label": lbl})

    if cfg.invert_tone:
        _add_inverse_tone_tiers(c, cfg, sites)

    return c

if "__main__" == __name__:
    import argparse

    parser = argparse.ArgumentParser(description="Build a standalone photonic chiplet mask.")
    parser.add_argument("--edit", action="store_true",
                        help="Edit mode — writes a fixed filename for iteration.")
    parser.add_argument("--invert", action="store_true",
                        help="Also build the two-tier inverse-tone (negative) "
                             "exposure layers: inv_fine (46) + inv_coarse (47).")
    parser.add_argument("--invert-extent", choices=("chip", "active_area"),
                        default="chip",
                        help="Outer extent of the coarse tier (default: chip).")
    parser.add_argument("--invert-zones", choices=("site", "feature"),
                        default="site",
                        help="Tiering: 'site' = one fine tier per device "
                             "(default); 'feature' = separate tiers for grating "
                             "couplers, ring, routing and text.")
    args = parser.parse_args()

    gf.gpdk.PDK.activate()
    cfg = PhotonicChipletConfig(
        invert_tone=args.invert,
        invert_coarse_extent=args.invert_extent,
        invert_zones=list(ZONES_PER_FEATURE if args.invert_zones == "feature"
                          else ZONES_PER_SITE),
    )
    c = build_photonic_chiplet_mask(cfg)
    EXPERIMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    stem = "photonic_chiplet_EDIT" if args.edit else f"photonic_chiplet_{cfg.chiplet_number:03d}"
    gds_path = EXPERIMENTAL_DIR / f"{stem}.gds"
    cfg_path = EXPERIMENTAL_DIR / f"{stem}.json"
    c.write_gds(gds_path)
    cfg.save(cfg_path)
    print(f"GDS  -> {gds_path}")
    print(f"JSON -> {cfg_path}")
    if cfg.invert_tone:
        print_inverse_tone_summary(cfg, json.loads(c.info["inv_summary"]))
    c.show()
