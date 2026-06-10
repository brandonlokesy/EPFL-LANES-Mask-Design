"""
photonics
=========
gdsfactory-based photonic component library for the LANES SiN platform.

Importing this package activates the LANES SiN PDK — a side-effect that is
intentional and required for built-in component factories to use SiN geometry
by default.  It has no effect on the gdstk-based electronic mask modules.

Modules
-------
technology  – PDK, LAYER constants, cross-section functions
rings       – ring and racetrack resonators
gratings    – grating couplers (elliptical and rectangular)
mzi         – Mach-Zehnder interferometers (MMI and DC variants)

Quick start
-----------
    from src.components.photonics.rings import ring_single, RingConfig
    from src.components.photonics.gratings import grating_elliptical
    from src.components.photonics.mzi import mzi_mmi

    ring = ring_single(radius=10.0, gap=0.15)
    gc   = grating_elliptical(neff=1.85, fiber_angle=10.0)
    mzi  = mzi_mmi(delta_length=50.0)
"""

from src.components.photonics import rings, gratings, mzi
from src.components.photonics.rings import (
    RingConfig,
    ring_single,
    ring_double,
    racetrack,
    from_config as ring_from_config,
    make_ring_sweep,
)
from src.components.photonics.gratings import (
    GratingConfig,
    grating_elliptical,
    grating_rectangular,
    from_config as grating_from_config,
    make_gc_sweep,
)
from src.components.photonics.mzi import (
    MZIConfig,
    mzi_mmi,
    mzi_dc,
    from_config as mzi_from_config,
    make_mzi_sweep,
)

__all__ = [
    # modules
    "rings", "gratings", "mzi",
    # ring resonators
    "RingConfig", "ring_single", "ring_double", "racetrack",
    "ring_from_config", "make_ring_sweep",
    # grating couplers
    "GratingConfig", "grating_elliptical", "grating_rectangular",
    "grating_from_config", "make_gc_sweep",
    # MZIs
    "MZIConfig", "mzi_mmi", "mzi_dc",
    "mzi_from_config", "make_mzi_sweep",
]
