"""
rings.py
========
Ring and racetrack resonator components for the LANES SiN photonic platform.

All component functions return a ``gf.Component`` whose geometry is cached
by gdsfactory — repeated calls with identical parameters return the same cell.

Geometry notes
--------------
- ``radius``          : bend radius to the waveguide centre-line (µm).
                        Determines the FSR via FSR ≈ λ²/(n_g · L).
- ``gap``             : edge-to-edge coupling gap between bus and ring (µm).
                        Controls the power coupling coefficient κ.
- ``wg_width``        : waveguide width (µm).  Adjust if you need to match
                        a specific effective index or mode confinement.
- ``coupling_length`` : (racetrack only) length of the straight coupling
                        section.  Increases κ without reducing radius.
- ``drop_gap``        : (add-drop only) gap at the drop-port bus; defaults
                        to ``gap`` for symmetric coupling.

Components
----------
ring_single     – all-pass ring resonator (one bus)
ring_double     – add-drop ring resonator (two buses)
racetrack       – all-pass racetrack (straight coupling section)
from_config     – dispatch from a RingConfig instance
make_ring_sweep – arrange a list of configs in a row for measurement

Usage
-----
    from src.components.photonics.rings import ring_single, RingConfig

    # Single component
    c = ring_single(radius=10.0, gap=0.15)
    c.write_gds("ring.gds")

    # Parameter sweep
    from src.components.photonics.rings import make_ring_sweep
    configs = [RingConfig(radius=r, gap=0.15) for r in [8, 10, 12, 15, 20]]
    sweep = make_ring_sweep(configs, spacing=60.0)
    sweep.write_gds("ring_sweep.gds")
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gdsfactory as gf

from src.components.photonics.technology import LAYER, xs_wg, xs_ring


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class RingConfig:
    """Serialisable parameter container for a single ring/racetrack resonator."""
    radius:          float      = 10.0    # bend radius, µm
    gap:             float      = 0.15    # coupling gap, µm
    wg_width:        float      = 0.8     # waveguide width, µm
    coupling_length: float      = 0.0     # straight coupler length; 0 → circular ring
    add_drop:        bool       = False   # True → add-drop (ring_double)
    drop_gap:        float|None = None    # drop-port gap; None → same as gap

    def to_dict(self) -> dict:
        return {
            "radius":          self.radius,
            "gap":             self.gap,
            "wg_width":        self.wg_width,
            "coupling_length": self.coupling_length,
            "add_drop":        self.add_drop,
            "drop_gap":        self.drop_gap,
        }


# =============================================================================
# COMPONENTS
# =============================================================================

def ring_single(
    radius:   float = 10.0,
    gap:      float = 0.15,
    wg_width: float = 0.8,
) -> gf.Component:
    """All-pass ring resonator.

    Ports
    -----
    o1  input  (west side of bus)
    o2  through (east side of bus)
    """
    return gf.components.ring_single(
        gap=gap,
        radius=radius,
        length_x=0,
        length_y=0,
        cross_section=xs_wg(width=wg_width),
    )


def ring_double(
    radius:   float      = 10.0,
    gap:      float      = 0.15,
    drop_gap: float|None = None,
    wg_width: float      = 0.8,
) -> gf.Component:
    """Add-drop ring resonator.

    Ports
    -----
    o1  input   (west, bottom bus)
    o2  through  (east, bottom bus)
    o3  drop     (east, top bus)
    o4  add      (west, top bus)
    """
    return gf.components.ring_double(
        gap=gap,
        gap_bot=drop_gap if drop_gap is not None else gap,
        radius=radius,
        length_x=0,
        length_y=0,
        cross_section=xs_wg(width=wg_width),
    )


def racetrack(
    radius:          float = 10.0,
    gap:             float = 0.15,
    coupling_length: float = 5.0,
    wg_width:        float = 0.8,
) -> gf.Component:
    """All-pass racetrack resonator with a straight coupling section.

    Resonator length: L = 2π·radius + 2·coupling_length.

    Ports
    -----
    o1  input
    o2  through
    """
    return gf.components.ring_single(
        gap=gap,
        radius=radius,
        length_x=coupling_length,
        length_y=0,
        cross_section=xs_wg(width=wg_width),
    )


# =============================================================================
# DISPATCH
# =============================================================================

def from_config(cfg: RingConfig) -> gf.Component:
    """Return the appropriate ring component for a given RingConfig."""
    if cfg.coupling_length > 0:
        return racetrack(radius=cfg.radius, gap=cfg.gap,
                         coupling_length=cfg.coupling_length, wg_width=cfg.wg_width)
    if cfg.add_drop:
        return ring_double(radius=cfg.radius, gap=cfg.gap,
                           drop_gap=cfg.drop_gap, wg_width=cfg.wg_width)
    return ring_single(radius=cfg.radius, gap=cfg.gap, wg_width=cfg.wg_width)


# =============================================================================
# SWEEPS
# =============================================================================

def make_ring_sweep(
    cfg_list: list[RingConfig],
    spacing:  float = 60.0,
) -> gf.Component:
    """Arrange a list of ring configs in a row for comparative measurements.

    Each ring is placed at ``spacing``-µm intervals along x and labelled
    R0, R1, … on the NOTES layer.

    Parameters
    ----------
    cfg_list : list of RingConfig
        One entry per ring variant (e.g. a radius or gap sweep).
    spacing : float
        Centre-to-centre x spacing between rings in µm.

    Returns
    -------
    gf.Component
        A single component containing all ring references.
    """
    top = gf.Component()
    x = 0.0
    for i, cfg in enumerate(cfg_list):
        ref = top.add_ref(from_config(cfg))
        ref.move((x, 0))
        top.add_label(f"R{i}", position=(x, 0), layer=LAYER.NOTES)
        x += spacing
    return top
