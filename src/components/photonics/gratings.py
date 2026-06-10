"""
gratings.py
===========
Grating coupler components for the LANES SiN photonic platform.

Two variants are provided:

``grating_elliptical``
    Physics-first parametrization.  You supply the modal effective index,
    cladding index, wavelength, and fiber angle; gdsfactory solves the
    phase-matching condition internally and draws elliptical grating arcs.
    Use this when you have simulation data for your waveguide mode.

    Phase-matching condition (Bragg):
        Λ = λ / (n_eff − n_clad · sin θ_fiber)

``grating_rectangular``
    Explicit geometry parametrization.  You supply the period and fill
    factor directly.  The grating teeth are rectangular lines, simpler to
    analyse and sufficient for initial device studies.

For both variants, geometry defaults are chosen for a SiN ridge waveguide
~400 nm thick, 800 nm wide, targeting λ = 1550 nm with a 10° cleaved-fibre
angle.  Calibrate ``neff`` (and ``period`` for rectangular) with your own
mode solver before committing to a mask.

Geometry notes
--------------
- ``neff``          : effective index of the guided mode.  Adjust for your
                      waveguide geometry / wavelength (start point: ~1.85).
- ``nclad``         : top cladding index (1.443 for SiO2 at 1550 nm).
- ``wavelength``    : target free-space wavelength, µm.
- ``fiber_angle``   : fibre-to-chip angle from normal, degrees.
                      8–15° is typical for SiN designs.
- ``grating_line_width`` : width of each grating bar, µm.  Lower fill
                      (narrower bar relative to Λ) typically produces more
                      uniform amplitude apodisation across the aperture.
- ``n_periods``     : number of grating periods.  More teeth → narrower
                      bandwidth and higher peak coupling.
- ``taper_angle``   : half-angle of the grating fan, degrees.  Wider fan
                      matches the fibre mode better (Gaussian overlap).
- ``taper_length``  : length of the waveguide-to-grating taper, µm.

Components
----------
grating_elliptical   – phase-matched elliptical arcs (physics-first)
grating_rectangular  – straight rectangular teeth (geometry-first)
from_config          – dispatch from a GratingConfig instance
make_gc_sweep        – row of gratings for comparative measurement

Usage
-----
    from src.components.photonics.gratings import grating_elliptical, GratingConfig

    gc = grating_elliptical(neff=1.85, fiber_angle=10.0)
    gc.write_gds("gc.gds")
"""

from __future__ import annotations

from dataclasses import dataclass

import gdsfactory as gf

from src.components.photonics.technology import LAYER, xs_wg


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class GratingConfig:
    """Serialisable parameter container for a grating coupler."""

    # ── shared ────────────────────────────────────────────────────────────
    variant:         str   = "elliptical"   # "elliptical" or "rectangular"
    n_periods:       int   = 20             # number of grating teeth
    taper_length:    float = 16.6           # waveguide taper length, µm
    taper_angle:     float = 40.0           # grating aperture half-angle, deg
    wg_width:        float = 0.8            # waveguide width, µm

    # ── elliptical-specific ────────────────────────────────────────────────
    neff:            float = 1.85           # guided mode effective index
    nclad:           float = 1.443          # cladding index (SiO2 at 1550 nm)
    wavelength:      float = 1.55           # target wavelength, µm
    fiber_angle:     float = 10.0           # fibre angle from normal, deg
    grating_line_width: float = 0.343       # grating bar width, µm

    # ── rectangular-specific ──────────────────────────────────────────────
    period:          float = 0.97           # grating period, µm
    fill_factor:     float = 0.5            # fraction of period that is waveguide
    width_grating:   float = 11.0           # grating aperture width (transverse), µm

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# =============================================================================
# COMPONENTS
# =============================================================================

def grating_elliptical(
    neff:               float = 1.85,
    nclad:              float = 1.443,
    wavelength:         float = 1.55,
    fiber_angle:        float = 10.0,
    grating_line_width: float = 0.343,
    n_periods:          int   = 20,
    taper_angle:        float = 40.0,
    taper_length:       float = 16.6,
    wg_width:           float = 0.8,
) -> gf.Component:
    """Grating coupler with phase-matched elliptical grating arcs.

    gdsfactory solves the Bragg condition
    ``Λ = λ / (n_eff − n_clad · sin θ)`` internally and places each grating
    arc on the corresponding ellipse.  Set ``neff`` from your mode solver.

    Ports
    -----
    o1  waveguide port (connects to bus waveguide)
    o2  fibre port     (virtual — marks the fibre coupling position)
    """
    return gf.components.grating_coupler_elliptical(
        polarization="te",
        taper_length=taper_length,
        taper_angle=taper_angle,
        wavelength=wavelength,
        fiber_angle=fiber_angle,
        grating_line_width=grating_line_width,
        neff=neff,
        nclad=nclad,
        n_periods=n_periods,
        layer_slab=None,            # SiN has no partial-etch slab
        cross_section=xs_wg(width=wg_width),
    )


def grating_rectangular(
    period:         float = 0.97,
    fill_factor:    float = 0.5,
    n_periods:      int   = 20,
    width_grating:  float = 11.0,
    taper_length:   float = 150.0,
    fiber_angle:    float = 10.0,
    wavelength:     float = 1.55,
    wg_width:       float = 0.8,
) -> gf.Component:
    """Grating coupler with straight rectangular grating teeth.

    Grating teeth are drawn on ``LAYER.GRATING`` (42/0); the input taper
    uses the ``xs_wg`` cross-section on ``LAYER.WG_CORE`` (40/0).

    The grating period should satisfy the Bragg condition for your geometry:
    ``period = wavelength / (neff − nclad · sin θ_fiber)``

    Ports
    -----
    o1  waveguide port
    o2  fibre port
    """
    return gf.components.grating_coupler_rectangular(
        n_periods=n_periods,
        period=period,
        fill_factor=fill_factor,
        width_grating=width_grating,
        length_taper=taper_length,
        polarization="te",
        wavelength=wavelength,
        fiber_angle=fiber_angle,
        layer_slab=None,
        layer_grating=LAYER.GRATING,
        cross_section=xs_wg(width=wg_width),
    )


# =============================================================================
# DISPATCH
# =============================================================================

def from_config(cfg: GratingConfig) -> gf.Component:
    """Return the appropriate grating coupler component for a given GratingConfig."""
    if cfg.variant == "rectangular":
        return grating_rectangular(
            period=cfg.period,
            fill_factor=cfg.fill_factor,
            n_periods=cfg.n_periods,
            width_grating=cfg.width_grating,
            taper_length=cfg.taper_length,
            fiber_angle=cfg.fiber_angle,
            wavelength=cfg.wavelength,
            wg_width=cfg.wg_width,
        )
    return grating_elliptical(
        neff=cfg.neff,
        nclad=cfg.nclad,
        wavelength=cfg.wavelength,
        fiber_angle=cfg.fiber_angle,
        grating_line_width=cfg.grating_line_width,
        n_periods=cfg.n_periods,
        taper_angle=cfg.taper_angle,
        taper_length=cfg.taper_length,
        wg_width=cfg.wg_width,
    )


# =============================================================================
# SWEEPS
# =============================================================================

def make_gc_sweep(
    cfg_list: list[GratingConfig],
    spacing:  float = 80.0,
) -> gf.Component:
    """Arrange a list of grating coupler configs in a row.

    Useful for sweeping neff estimates, fill factors, or fibre angles across
    a single chip to find the optimal coupling condition experimentally.

    Parameters
    ----------
    cfg_list : list of GratingConfig
        One entry per grating variant.
    spacing : float
        Centre-to-centre x spacing between gratings, µm.

    Returns
    -------
    gf.Component
        A single component containing all grating coupler references,
        labelled GC0, GC1, … on the NOTES layer.
    """
    top = gf.Component()
    x = 0.0
    for i, cfg in enumerate(cfg_list):
        ref = top.add_ref(from_config(cfg))
        ref.move((x, 0))
        top.add_label(f"GC{i}", position=(x, 0), layer=LAYER.NOTES)
        x += spacing
    return top
