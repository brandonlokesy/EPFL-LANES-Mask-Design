from __future__ import annotations

from typing import Any

import gdsfactory as gf
import klayout.db as kdb
import numpy as np
from gdsfactory.typings import ComponentSpec, CrossSectionSpec, LayerSpec

from src.components.photonics.technology import LAYER


@gf.cell
def coupler_pulley_closed(
    radius: float = 10.0,
    ring_width: float | None = None,
    n_segments: int = 128,
    layer: LayerSpec = "WG",
    **kwargs: Any,
) -> gf.Component:
    """
    ``gf.components.coupler_pulley`` with the ring actually closed.

    gdsfactory 9.41 draws the annulus as one keyhole polygon (outer circle CCW,
    radial cut in, inner circle CW, radial cut out), with both circles sampled by
    ``linspace(0, 2pi, 2n, endpoint=False)``. Both loops therefore stop at
    2pi - dtheta, the two cuts land on different rays (-dtheta and 0), and the
    annular sector between them is never enclosed: the ring is a "C" with a slit
    of width 2 pi R / (2n) at theta = 0. Raising n_segments only narrows it.

    The fix: the missing sector is the quadrilateral on the four vertices
    gdsfactory already places at the ends of the two cuts. Between adjacent
    vertices the "circle" is a straight chord, so the quadrilateral fits exactly.
    OR it into the ring layer and merge: the result is one polygon with a hole.

    Once upstream samples with ``endpoint=True`` the cuts coincide and the
    sector has zero area -- this wrapper becomes a no-op and can be dropped.
    All other arguments pass through to ``coupler_pulley`` unchanged.
    """
    c = gf.Component()
    ref = c << gf.components.coupler_pulley(
        radius=radius, ring_width=ring_width, n_segments=n_segments,
        layer=layer, **kwargs,
    )
    c.add_ports(ref.ports)
    c.flatten()

    if ring_width is None:
        return c  # solid disc: a single closed loop, drawn correctly upstream

    # Same float expressions as upstream, so the corners snap to the same grid
    # points as the ring's own cut vertices.
    last = np.linspace(0, 2 * np.pi, n_segments * 2, endpoint=False)[-1]
    r_in = radius - ring_width
    sector = kdb.DPolygon([
        kdb.DPoint(radius * np.cos(last), radius * np.sin(last)),
        kdb.DPoint(radius, 0.0),
        kdb.DPoint(r_in, 0.0),
        kdb.DPoint(r_in * np.cos(last), r_in * np.sin(last)),
    ])

    shapes = c.shapes(gf.get_layer(layer))
    ring = kdb.Region(shapes)
    ring.insert(sector.to_itype(c.kcl.dbu))
    ring.merge()
    shapes.clear()
    shapes.insert(ring)
    return c


@gf.cell
def pulley_with_leads(
    pulley: ComponentSpec = gf.components.coupler_pulley,
    extend_ports_length: float | dict[str, float] = 0.0,
    bends: dict[str, ComponentSpec] | None = None,
    cross_section: CrossSectionSpec | None = None,
    terminations: dict[str, ComponentSpec] | None = None,
) -> gf.Component:
    """
    Parameters
    ----------
    pulley
        The pulley coupler component or spec.
    extend_ports_length
        Length of straight lead on each port. Float applies to all ports;
        dict keys are port names for per-port control.
    bends
        Per-port bend specs, keyed by port name.
        Applied after the straight extension (if any).
        Example: {"o1": gf.components.bend_euler, "o2": dict(component="bend_euler", settings=dict(radius=20))}
    cross_section
        Cross-section for all straights and bends. If None, uses component defaults.
    """
    c = gf.Component()
    p = gf.get_component(pulley)
    pref = c << p

    if isinstance(extend_ports_length, (int, float)):
        lengths = {port.name: extend_ports_length for port in p.ports}
    else:
        lengths = extend_ports_length

    xs_kwargs = {} if cross_section is None else {"cross_section": cross_section}

    # Track the outermost free port on each lead after straights and bends
    free_ports: dict[str, gf.Port] = {}

    for port in p.ports:
        name = port.name
        length = lengths.get(name, 0.0)
        if length > 0:
            s = c << gf.components.straight(length=length, **xs_kwargs)
            s.connect("o1", pref.ports[name])
            free_ports[name] = s.ports["o2"]
        else:
            free_ports[name] = pref.ports[name]

    if bends:
        for port_name, bend_spec in bends.items():
            b = c << gf.get_component(bend_spec, **xs_kwargs)
            b.connect("o1", free_ports[port_name])
            free_ports[port_name] = b.ports["o2"]
    
    if terminations:
        for port_name, termination_spec in terminations.items():
            t = c << gf.get_component(termination_spec, **xs_kwargs)
            t.connect("o1", free_ports[port_name])
            free_ports[port_name] = t.ports["o2"]

    for name, port in free_ports.items():
        c.add_port(name=name, port=port)

    return c
