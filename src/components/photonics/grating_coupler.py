from __future__ import annotations

from gdsfactory.typings import CrossSectionSpec


def grating_coupler_vis_settings(cross_section: CrossSectionSpec) -> dict:
    """
    Settings for ``gf.components.grating_coupler_elliptical`` on SiN at ~750 nm.

    Shared by every photonic chiplet so all devices couple through the same
    grating. Pass as ``dict(component="grating_coupler_elliptical",
    settings=grating_coupler_vis_settings(xs))``.
    """
    return dict(
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
        cross_section=cross_section,
    )
