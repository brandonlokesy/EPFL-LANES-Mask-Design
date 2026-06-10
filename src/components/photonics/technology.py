"""
technology.py
=============
PDK, layer constants, and cross-section functions for the LANES SiN photonic
platform.

A custom PDK is created at import time, overriding ``'strip'`` with our SiN
waveguide parameters (800 nm wide, layer 40/0).  This propagates automatically
into every gdsfactory built-in component (mmi1x2, coupler, bend_euler, …) so
callers never need to thread ``cross_section`` through every function call.
The generic PDK's cells are inherited, so all standard component factories
remain available.

Layer numbers mirror ``src/config/layers.py`` — photonic range 40–49.

Usage
-----
    from src.components.photonics.technology import LAYER, xs_wg, xs_ring, PDK
"""

import gdsfactory as gf

from src.config.layers import LAYERS as _LAYERS


def _l(key: str) -> tuple:
    """Convert a ``LAYERS`` dict entry to the ``(layer, datatype)`` tuple
    that gdsfactory cross-sections and component calls expect."""
    e = _LAYERS[key]
    return (e["layer"], e["datatype"])


# =============================================================================
# LAYER CONSTANTS
# =============================================================================

class LAYER:
    """
    ``(layer, datatype)`` tuples for the LANES SiN photonic process.
    Derived from ``src/config/layers.py`` — that file is the single source
    of truth for all layer numbers.
    """
    # ── Photonic structures ────────────────────────────────────────────────
    WG_CORE          = _l("wg_core")          # bus waveguides, MZI arms, tapers
    WG_CLAD          = _l("wg_clad")          # simulation / reference — not fabricated
    RING             = _l("ring")             # ring / racetrack resonator cores
    GRATING          = _l("grating")          # grating coupler teeth
    PHOTONIC_CRYSTAL = _l("photonic_crystal") # photonic crystal features
    HEATER           = _l("heater")           # TiN thermo-optic heater
    METAL_CONTACT    = _l("metal_contact")    # contacts to heater

    # ── Annotation ────────────────────────────────────────────────────────
    CHIP_BOUNDARY    = _l("chip_boundary")
    ACTIVE_AREA      = _l("chip_active_area")
    NOTES            = _l("notes")


# =============================================================================
# CROSS-SECTION FUNCTIONS
# =============================================================================
# These are *callables*, not CrossSection objects, so they can be registered
# in the PDK and called with keyword overrides (e.g. width=0.5 for a taper).

def xs_wg(width: float = 0.8, layer: tuple = LAYER.WG_CORE, **kwargs) -> gf.CrossSection:
    """SiN strip waveguide cross-section (800 nm default, layer WG_CORE 40/0).

    Registered as both ``'strip'`` and ``'xs_wg'`` in the LANES PDK, so all
    built-in gdsfactory components use SiN geometry by default.
    """
    return gf.cross_section.strip(width=width, layer=layer, **kwargs)


def xs_ring(width: float = 0.8, layer: tuple = LAYER.RING, **kwargs) -> gf.CrossSection:
    """SiN ring waveguide cross-section (800 nm default, layer RING 41/0).

    Use when your process doses ring structures separately from bus waveguides
    (e.g. different e-beam write fields or proximity corrections).
    If rings and bus guides share an etch step, use ``xs_wg`` for both and
    leave the RING layer unused.
    """
    return gf.cross_section.strip(width=width, layer=layer, **kwargs)


# Convenience objects — pre-called instances for use as explicit cross-section
# arguments when you need a CrossSection object rather than a spec callable.
XS_WG  = xs_wg()
XS_RING = xs_ring()


# =============================================================================
# PDK
# =============================================================================

_generic = gf.gpdk.PDK

PDK = gf.Pdk(
    name="LANES_SiN",
    cross_sections={
        **_generic.cross_sections,  # inherit all generic cross-sections
        "strip":   xs_wg,           # override default strip → SiN 800 nm
        "xs_wg":   xs_wg,
        "xs_ring": xs_ring,
    },
    cells=_generic.cells,           # inherit all generic component factories
)

PDK.activate()
