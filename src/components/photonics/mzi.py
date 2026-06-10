"""
mzi.py
======
Mach-Zehnder interferometer components for the LANES SiN photonic platform.

Two splitter variants are provided:

``mzi_mmi``
    Uses a 1×2 MMI as both the splitter and combiner.  MMIs produce a
    broadband, fabrication-tolerant 50:50 split and are the standard
    starting point for SiN MZIs.

``mzi_dc``
    Uses a directional coupler (DC) as the splitter and combiner.  The DC
    split ratio is wavelength-dependent, which is a deliberate feature when
    the goal is to characterise the coupler itself or to design a
    coupler-based filter.  Gap and coupling length set the coupling at the
    design wavelength.

Both variants accept a ``delta_length`` parameter that sets the arm length
difference ΔL.  The key relationship is:

    FSR  ≈  λ² / (n_g · ΔL)

where n_g is the group index of the waveguide mode.  For SiN (~400 nm thick)
at 1550 nm, n_g ≈ 1.9.  Examples:
    ΔL = 10  µm → FSR ≈ 127 nm
    ΔL = 50  µm → FSR ≈  25 nm
    ΔL = 100 µm → FSR ≈  13 nm

The phase condition for a transmission minimum:
    Δφ = (2π/λ) · n_eff · ΔL = (2m+1)π

Geometry notes
--------------
- ``delta_length`` : arm length difference ΔL, µm.  Sets the FSR.
- ``arm_spacing``  : transverse (y) separation between the two arms, µm.
                     Pure layout parameter; does not affect the optical
                     response.
- ``splitter``-specific for DC variant:
  - ``gap``              : edge-to-edge coupling gap, µm.
  - ``coupling_length``  : length of the parallel coupling region, µm.

Components
----------
mzi_mmi          – MZI with MMI 1×2 splitters
mzi_dc           – MZI with directional-coupler splitters
from_config      – dispatch from an MZIConfig instance
make_mzi_sweep   – row of MZIs sweeping delta_length

Usage
-----
    from src.components.photonics.mzi import mzi_mmi, MZIConfig

    c = mzi_mmi(delta_length=50.0)
    c.write_gds("mzi.gds")
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

import gdsfactory as gf

from src.components.photonics.technology import LAYER, xs_wg


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class MZIConfig:
    """Serialisable parameter container for an MZI."""

    # ── shared ────────────────────────────────────────────────────────────
    splitter_type:   str   = "mmi"    # "mmi" or "dc"
    delta_length:    float = 10.0     # arm length difference ΔL, µm
    arm_spacing:     float = 2.0      # transverse arm separation, µm
    wg_width:        float = 0.8      # waveguide width, µm

    # ── DC-splitter specific ───────────────────────────────────────────────
    gap:             float = 0.2      # coupling gap, µm
    coupling_length: float = 10.0     # DC interaction length, µm

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# =============================================================================
# COMPONENTS
# =============================================================================

def mzi_mmi(
    delta_length:  float = 10.0,
    arm_spacing:   float = 2.0,
    wg_width:      float = 0.8,
) -> gf.Component:
    """Mach-Zehnder interferometer with 1×2 MMI splitters.

    The MMI provides a broadband, fabrication-tolerant 50:50 split ratio.
    FSR ≈ λ²/(n_g · delta_length).

    Ports
    -----
    o1  input
    o2  output
    """
    xs = xs_wg(width=wg_width)
    return gf.components.mzi(
        delta_length=delta_length,
        length_y=arm_spacing,
        length_x=0.1,
        splitter="mmi1x2",
        cross_section=xs,
    )


def mzi_dc(
    delta_length:    float = 10.0,
    arm_spacing:     float = 4.0,
    gap:             float = 0.2,
    coupling_length: float = 10.0,
    wg_width:        float = 0.8,
) -> gf.Component:
    """Mach-Zehnder interferometer with directional-coupler splitters.

    The DC split ratio is wavelength-dependent, coupling coefficient:
        κ = sin²(κ₀ · coupling_length)
    At the design wavelength choose coupling_length for 50:50 (κ = 0.5).

    FSR ≈ λ²/(n_g · delta_length).

    Ports
    -----
    o1  input  (lower port of input DC)
    o2  output (lower port of output DC)
    o3  unused input port of input DC
    o4  unused output port of output DC
    """
    xs = xs_wg(width=wg_width)
    dc_spec = partial(
        gf.components.coupler,
        gap=gap,
        length=coupling_length,
        cross_section=xs,
    )
    return gf.components.mzi(
        delta_length=delta_length,
        length_y=arm_spacing,
        length_x=0.1,
        splitter=dc_spec,
        port_e1_splitter="o3",
        port_e0_splitter="o4",
        port1="o1",
        port2="o2",
        cross_section=xs,
    )


# =============================================================================
# DISPATCH
# =============================================================================

def from_config(cfg: MZIConfig) -> gf.Component:
    """Return the appropriate MZI component for a given MZIConfig."""
    if cfg.splitter_type == "dc":
        return mzi_dc(
            delta_length=cfg.delta_length,
            arm_spacing=cfg.arm_spacing,
            gap=cfg.gap,
            coupling_length=cfg.coupling_length,
            wg_width=cfg.wg_width,
        )
    return mzi_mmi(
        delta_length=cfg.delta_length,
        arm_spacing=cfg.arm_spacing,
        wg_width=cfg.wg_width,
    )


# =============================================================================
# SWEEPS
# =============================================================================

def make_mzi_sweep(
    delta_lengths: list[float],
    splitter_type: str   = "mmi",
    arm_spacing:   float = 2.0,
    gap:           float = 0.2,
    coupling_length: float = 10.0,
    wg_width:      float = 0.8,
    spacing:       float = 80.0,
) -> gf.Component:
    """Arrange a row of MZIs sweeping delta_length for FSR characterisation.

    Parameters
    ----------
    delta_lengths : list of float
        ΔL values in µm, one per MZI instance.
    splitter_type : str
        ``"mmi"`` or ``"dc"`` — applies to all instances in the sweep.
    spacing : float
        Centre-to-centre x spacing between MZIs, µm.

    Returns
    -------
    gf.Component
        Row of MZIs labelled MZI0, MZI1, … on the NOTES layer.
    """
    cfg_list = [
        MZIConfig(
            delta_length=dl,
            splitter_type=splitter_type,
            arm_spacing=arm_spacing,
            gap=gap,
            coupling_length=coupling_length,
            wg_width=wg_width,
        )
        for dl in delta_lengths
    ]
    top = gf.Component()
    x = 0.0
    for i, cfg in enumerate(cfg_list):
        ref = top.add_ref(from_config(cfg))
        ref.move((x, 0))
        top.add_label(f"MZI{i}", position=(x, 0), layer=LAYER.NOTES)
        x += spacing
    return top
