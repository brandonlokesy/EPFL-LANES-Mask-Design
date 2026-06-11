from __future__ import annotations

import gdsfactory as gf
from gdsfactory.typings import ComponentSpec, CrossSectionSpec

from src.components.photonics.technology import LAYER


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
