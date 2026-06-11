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


XS_SIN      = gf.cross_section.strip(width=0.8,  layer=LAYER.WG_CORE)  # SiN @ 1550 nm
XS_SIN_VIS  = gf.cross_section.strip(width=0.5,  layer=LAYER.WG_CORE)  # SiN @ 780 nm
XS_LNOI     = gf.cross_section.strip(width=0.9,  layer=LAYER.WG_CORE)  # LNOI @ 1550 nm
XS_BTO      = gf.cross_section.strip(width=0.7,  layer=LAYER.WG_CORE)  # BTO @ 1550 nm

CROSS_SECTIONS: dict = {
    "SIN":     XS_SIN,
    "SIN_VIS": XS_SIN_VIS,
    "LNOI":    XS_LNOI,
    "BTO":     XS_BTO,
}
