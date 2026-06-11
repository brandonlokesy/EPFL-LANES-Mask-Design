from __future__ import annotations

import gdsfactory as gf
from src.config.layers import LAYERS as _LAYERS


def _l(key: str) -> tuple:
    e = _LAYERS[key]
    return (e["layer"], e["datatype"])


class LAYER:
    WG_CORE          = _l("wg_core")
    WG_CLAD          = _l("wg_clad")
    RING             = _l("ring")
    GRATING          = _l("grating")
    PHOTONIC_CRYSTAL = _l("photonic_crystal")
    HEATER           = _l("heater")
    METAL_CONTACT    = _l("metal_contact")
    CHIP_BOUNDARY    = _l("chip_boundary")
    ACTIVE_AREA      = _l("chip_active_area")
    NOTES            = _l("notes")


XS_SIN = gf.cross_section.strip(width=0.8, layer=LAYER.WG_CORE)
