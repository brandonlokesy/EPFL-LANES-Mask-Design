"""
photonic_chiplet_mask.py

Photonic chiplet carrying a 3x3 pulley-coupler dose-test array. The frame
(markers, pads, ID, inverse tone, CLI) lives in ``photonic_chiplet_base``.

Usage
-----
    python -m src.chips.photonic_chiplet_mask          # writes to masks/experimental/
    python -m src.chips.photonic_chiplet_mask --edit   # fixed filename for iteration
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gdsfactory as gf

from src.chips.photonic_chiplet_base import (
    PhotonicChipletBaseConfig,
    build_chip_frame,
    finish_chip,
    run_cli,
)
from src.components.photonics.technology import LAYER, CROSS_SECTIONS
from src.components.photonics.pulley import pulley_with_leads, coupler_pulley_closed
from src.components.photonics.grating_coupler import grating_coupler_vis_settings


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PhotonicChipletConfig(PhotonicChipletBaseConfig):
    """
    All parameters needed to reproduce the pulley-coupler photonic chiplet.
    Infrastructure fields are inherited from ``PhotonicChipletBaseConfig``.
    """

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
    # Points per curved section; each ring circle gets 2x this. Sets smoothness
    # only (coupler_pulley_closed closes the ring): max deviation from a true
    # circle is R(1 - cos(pi / 2n)), 0.09 nm at R = 5 um and n = 256.
    pulley_n_segments:    int   = 256

    # ── Pulley array (3×3 dose test) ──────────────────────────────────────
    pulley_array_col_pitch:  float = 500.0   # µm — tune after checking device bbox
    pulley_array_row_pitch:  float = 300.0   # µm — tune after checking device bbox
    pulley_array_label_size: float = 15.0    # µm text height


# =============================================================================
# PHOTONIC DEVICE BUILDER  (gdsfactory)
# =============================================================================

def build_photonic_chiplet_mask(
    cfg: PhotonicChipletConfig,
    cell_name: str = None,
):
    if cell_name is None:
        cell_name = f"PHOTONIC_CHIPLET_{cfg.chiplet_number:03d}"
    c = build_chip_frame(cfg, cell_name)

    xs = CROSS_SECTIONS[cfg.cross_section]

    grating_coupler_settings_dict = grating_coupler_vis_settings(xs)

    bends_settings_dict_right = dict(
        dict(angle = 90, radius = 30)
    )
    bends_settings_dict_left = dict(
        dict(angle = -90, radius = 30)
    )
    # Build device once — @gf.cell caches it, all 9 placements share the same master cell
    device = pulley_with_leads(
        pulley=coupler_pulley_closed(
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

    return finish_chip(c, cfg)

if "__main__" == __name__:
    run_cli(PhotonicChipletConfig, build_photonic_chiplet_mask, stem="photonic_chiplet")
