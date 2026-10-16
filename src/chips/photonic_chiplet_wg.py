"""
photonic_chiplet_wg.py

Photonic chiplet carrying a stack of long parallel straight waveguides for
cross-section SEM. The waveguides run along x and are stacked in y; cleaving
the chip anywhere across them (a cleave line along y, within
|x - wg_x_offset| < wg_length/2) exposes every waveguide's cross-section in the same facet. The frame (markers,
pads, ID, inverse tone, CLI) lives in ``photonic_chiplet_base``.

Usage
-----
    python -m src.chips.photonic_chiplet_wg          # writes to masks/experimental/
    python -m src.chips.photonic_chiplet_wg --edit   # fixed filename for iteration
"""

from __future__ import annotations

from dataclasses import dataclass

import gdsfactory as gf

from src.chips.photonic_chiplet_base import (
    PhotonicChipletBaseConfig,
    build_chip_frame,
    finish_chip,
    run_cli,
)
from src.components.photonics.technology import LAYER, CROSS_SECTIONS

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class PhotonicWgChipletConfig(PhotonicChipletBaseConfig):
    """
    All parameters needed to reproduce the waveguide photonic chiplet.
    Infrastructure fields are inherited from ``PhotonicChipletBaseConfig``.
    Waveguide width comes from ``cross_section`` (SIN_VIS: 0.5 µm).
    """

    # ── Waveguide stack (cross-section SEM) ───────────────────────────────
    wg_count:       int   = 5
    wg_length:      float = 4000.0  # µm, along x
    # x of the stack's centre. Shifted right of the chip centre (x = 0) so the
    # lines sit in the right half: x = 500 ... 4500 µm with the defaults.
    wg_x_offset:    float = 1500.0
    # Centre-to-centre in y. 100 µm keeps each line outside its neighbours'
    # ~30 µm e-beam backscatter range, so all five see the same dose as an
    # isolated waveguide, while the whole stack still fits in one SEM view.
    wg_pitch:       float = 100.0
    wg_label_size:  float = 15.0    # µm text height
    wg_label_gap:   float = 20.0    # µm between label and waveguide end
    sample_id : str = "Si3N4-2610-C05"


# =============================================================================
# PHOTONIC DEVICE BUILDER  (gdsfactory)
# =============================================================================

def build_photonic_wg_chiplet(
    cfg: PhotonicWgChipletConfig,
    cell_name: str = None,
):
    if cell_name is None:
        cell_name = f"PHOTONIC_WG_CHIPLET_{cfg.chiplet_number:03d}"
    c = build_chip_frame(cfg, cell_name)

    xs = CROSS_SECTIONS[cfg.cross_section]
    wg = gf.components.straight(length=cfg.wg_length, cross_section=xs)

    sample_label = gf.components.text(
        text = cfg.sample_id,
        size = 350,
        layer = LAYER.SAMPLE_ID
    )

    lbl = c << sample_label
    lbl.center= (-3000, 0)
    lbl.rotate(90, center=lbl.center)

    for i in range(cfg.wg_count):
        # Stack centred on y = 0, W1 at the bottom.
        y = (i - (cfg.wg_count - 1) / 2) * cfg.wg_pitch

        dev = c << wg
        dev.x = cfg.wg_x_offset
        dev.y = y

        lbl = c << gf.components.text(
            text=f"W{i + 1}",
            size=cfg.wg_label_size,
            layer=LAYER.NOTES,
        )
        lbl.xmax = dev.xmin - cfg.wg_label_gap
        lbl.y = y

    return finish_chip(c, cfg)


if "__main__" == __name__:
    run_cli(PhotonicWgChipletConfig, build_photonic_wg_chiplet, stem="photonic_chiplet_wg")
