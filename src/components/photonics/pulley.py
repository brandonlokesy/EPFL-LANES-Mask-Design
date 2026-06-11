from __future__ import annotations

import gdsfactory as gf
from gdsfactory.typings import ComponentSpec

from src.components.photonics.technology import LAYER, XS_SIN


@gf.cell
def pulley_with_leads(
    radius:         float              = 10.0,
    ring_width:     float              = 0.2,
    gap:            float              = 0.2,
    coupling_angle: float              = 5.0,
    wg_length:      float              = 75.0,
    wg_height:      float              = 4.0,
    lead_length:    float              = 50.0,
    n_segments:     int                = 128,
    cross_section                      = XS_SIN,
    bend:           ComponentSpec | None = None,
    terminator:     ComponentSpec | None = None,
) -> gf.Component:
    """Pulley ring coupler with straight leads and optional bend/terminator at each port.

    Ports
    -----
    o1  west output (present only when terminator is None)
    o2  east output (present only when terminator is None)

    Examples
    --------
    pulley_with_leads()                                          # straight leads, open ports
    pulley_with_leads(bend="bend_euler")                         # euler bends, open ports
    pulley_with_leads(bend="bend_euler", terminator="grating_coupler_elliptical")
    """
    c = gf.Component()

    pulley = c << gf.components.coupler_pulley(
        radius=radius,
        ring_width=ring_width,
        gap=gap,
        coupling_angle=coupling_angle,
        wg_length=wg_length,
        wg_height=wg_height,
        n_segments=n_segments,
        cross_section=cross_section,
        layer=LAYER.RING,
    )

    lead = gf.components.straight(length=lead_length, cross_section=cross_section)

    for port_name in ("o1", "o2"):
        s = c << lead
        if port_name == "o1":
            s.connect("o2", pulley.ports["o1"])
        else:
            s.connect("o1", pulley.ports["o2"])
        tip = s.ports["o1"] if port_name == "o1" else s.ports["o2"]

        if bend is not None:
            b = c << gf.get_component(bend)
            b.connect("o2", tip)
            tip = b.ports["o1"]

        if terminator is not None:
            t = c << gf.get_component(terminator)
            t.connect("o2", tip)
        else:
            c.add_port(port_name, port=tip)

    return c
