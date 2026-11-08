"""redes_dnep_opendss — modelos OpenDSS de las redes y flujo de potencia.

    import redes_dnep_opendss as rdo

    rdo.write_dss("red54", case="camargo")          # escribe opendss/red54/camargo/master_e{s}.dss
    r = rdo.simulate("red54", case="camargo", stage=2)
    r["losses_kW"], r["vmin_pu"], r["sources"]       # resultados del flujo

    python redes_dnep_opendss.py            # regenera la carpeta opendss/ para todas las redes

Casos:
  base     caso 0: red inicial (solo circuitos y SE existentes) con la demanda de la etapa indicada.
  camargo  solución publicada en Camargo (2014) para cada etapa (data/<red>/solution_camargo/).

Modelo: equivalente trifásico balanceado; cada SE activa es un Vsource rígido; líneas con R1 = R0 y
X1 = X0 del conductor, sin capacitancia, normamps = Imax; cargas de potencia constante (model=1) en el
pico de la etapa. Solo se modela la parte conectada a alguna SE activa: las cargas sin alimentación se
informan en `unserved_loads` (y en no_energizadas_e{s}.csv).

Escribir los .dss solo requiere pandas y networkx; `simulate` requiere py-dss-interface (Windows).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

import redes_dnep as rd

ROOT = Path(__file__).resolve().parent
DSS_DIR = ROOT / "opendss"
CASES = ("base", "camargo")


def _b(n: int) -> str:
    return f"b{n}"


def _energized(lines: pd.DataFrame, sources) -> set:
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(sources)
    g.add_edges_from(zip(lines["from"], lines["to"]))
    return set().union(*(nx.node_connected_component(g, n) for n in sources))


def write_dss(name: str, case: str = "camargo", out_dir: str | Path | None = None) -> Path:
    """Escribe los archivos .dss de una red y un caso (todas las etapas). Devuelve la carpeta."""
    if case not in CASES:
        raise ValueError(f"case debe ser uno de {CASES}")
    net = rd.load_network(name)
    kv = net.system["V_kV"]
    out = Path(out_dir) if out_dir else DSS_DIR / name / case
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "linecodes.dss", "w", encoding="utf-8") as f:
        f.write(f"! Conductores de {name} (data/{name}/conductors.csv)\n")
        for c in net.conductors.itertuples():
            f.write(f"New Linecode.C{c.type} nphases=3 units=km r1={c.R_ohm_km} x1={c.X_ohm_km} "
                    f"r0={c.R_ohm_km} x0={c.X_ohm_km} c1=0 c0=0 normamps={c.Imax_A} emergamps={c.Imax_A}\n")
    b = net.buses
    b.assign(bus=b.bus.map(_b))[["bus", "x", "y"]].to_csv(out / "buscoords.csv", index=False, header=False)

    for s in range(1, net.system["stages"] + 1):
        act, se = net.topology(s, case)
        energ = _energized(act, se.bus)
        act = act[act["from"].isin(energ)]
        ld = net.loads[(net.loads.stage == s) & (net.loads.P_kW > 0)]
        ld[~ld.bus.isin(energ)].to_csv(out / f"no_energizadas_e{s}.csv", index=False)
        ld = ld[ld.bus.isin(energ)]
        with open(out / f"fuentes_e{s}.dss", "w", encoding="utf-8") as f:
            for k, r in enumerate(se.itertuples()):
                cmd = f"New Circuit.{name}" if k == 0 else f"New Vsource.SE{r.bus}"
                f.write(f"{cmd} bus1={_b(r.bus)} basekv={kv} pu=1.0 phases=3 angle=0 MVAsc3=1000000 "
                        f"MVAsc1=1000000  ! SE {r.bus}, opción {r.option}, {r.cap_new_MVA} MVA\n")
        with open(out / f"lineas_e{s}.dss", "w", encoding="utf-8") as f:
            for r in act.itertuples():
                f.write(f"New Line.L{r.line} bus1={_b(r._2)} bus2={_b(r.to)} linecode=C{r.conductor} "
                        f"length={r.length_km} units=km  ! {r.state}\n")
        with open(out / f"cargas_e{s}.dss", "w", encoding="utf-8") as f:
            for r in ld.itertuples():
                f.write(f"New Load.LD{r.bus} bus1={_b(r.bus)} phases=3 kV={kv} kW={r.P_kW} kvar={r.Q_kvar} "
                        f"model=1 vminpu=0.7 vmaxpu=1.3\n")
        with open(out / f"master_e{s}.dss", "w", encoding="utf-8") as f:
            f.write(f"Clear\n! {name} - caso '{case}', etapa {s}. Generado por redes_dnep_opendss.py\n"
                    f"! Tensión de la fuente: pu=1.0 aquí; la que reproduce la tesis está en "
                    f"data/{name}/solution_camargo/reference.json (v_source_pu_opendss).\n"
                    f"Redirect fuentes_e{s}.dss\nRedirect linecodes.dss\nRedirect lineas_e{s}.dss\n"
                    f"Redirect cargas_e{s}.dss\nSet voltagebases=[{kv}]\nCalcVoltageBases\n"
                    f"Buscoords buscoords.csv\nSet maxiterations=100\nSolve\n")
    return out


def v_source_fitted(name: str) -> float:
    """Tensión de fuente (pu) con la que OpenDSS reproduce los resultados publicados."""
    net = rd.load_network(name)
    return float(net.solution["reference"]["v_source_pu_opendss"]) if net.solution else 1.0


def _names(lst) -> list[str]:
    return [n for n in lst if n and n.upper() != "NONE"]


def simulate(name: str, case: str = "camargo", stage: int = 1, v_source_pu: float | None = None) -> dict:
    """Flujo de potencia de una red, caso y etapa. Requiere py-dss-interface.

    v_source_pu: tensión de todas las SE; por defecto la ajustada contra la tesis (v_source_fitted).
    Devuelve: converged, losses_kW, losses_kvar, load_kW, vmin_pu/vmin_bus, vmax_pu/vmax_bus,
    voltages {bus: pu}, sources {SE: P_kW, Q_kvar, S_kVA}, lines {L: I_A, loading_pct},
    overloaded_lines, unserved_loads (DataFrame).
    """
    import py_dss_interface

    out = write_dss(name, case)
    master = os.path.abspath(out / f"master_e{stage}.dss")
    if not os.path.isfile(master):
        raise ValueError(f"{name} no tiene etapa {stage}")
    v = v_source_fitted(name) if v_source_pu is None else v_source_pu
    d = py_dss_interface.DSS()  # cambia el directorio de trabajo: usar rutas absolutas
    d.text(f"compile [{master}]")
    for src in _names(d.vsources.names):
        d.text(f"Vsource.{src}.pu={v}")
    d.text("solve")

    p_loss, q_loss = d.circuit.losses
    volt = {}
    for bus in d.circuit.buses_names:
        d.circuit.set_active_bus(bus)
        m = d.bus.vmag_angle_pu[0::2]
        volt[int(bus[1:])] = sum(m) / len(m)
    sources = {}
    for src in _names(d.vsources.names):
        d.circuit.set_active_element(f"vsource.{src}")
        pw = d.cktelement.powers
        n = len(pw) // 4
        p, q = -sum(pw[0:2 * n:2]), -sum(pw[1:2 * n:2])
        bus = int(d.cktelement.bus_names[0].split(".")[0][1:])
        sources[bus] = {"P_kW": p, "Q_kvar": q, "S_kVA": (p * p + q * q) ** 0.5}
    lines = {}
    for ln in _names(d.lines.names):
        d.lines.name = ln
        d.circuit.set_active_element(f"line.{ln}")
        i = d.cktelement.currents_mag_ang[0::2]
        imax = max(i[:len(i) // 2])
        lines[int(ln[1:])] = {"I_A": imax, "loading_pct": 100 * imax / d.lines.norm_amps}
    load_kW = 0.0
    for ld in _names(d.loads.names):
        d.circuit.set_active_element(f"load.{ld}")
        load_kW += sum(d.cktelement.powers[0::2])
    bmin, bmax = min(volt, key=volt.get), max(volt, key=volt.get)
    return {"network": name, "case": case, "stage": stage, "v_source_pu": v,
            "converged": bool(d.solution.converged), "losses_kW": p_loss / 1000, "losses_kvar": q_loss / 1000,
            "load_kW": load_kW, "vmin_pu": volt[bmin], "vmin_bus": bmin, "vmax_pu": volt[bmax], "vmax_bus": bmax,
            "voltages": volt, "sources": sources, "lines": lines,
            "overloaded_lines": sorted(k for k, x in lines.items() if x["loading_pct"] > 100),
            "unserved_loads": pd.read_csv(out / f"no_energizadas_e{stage}.csv")}


if __name__ == "__main__":
    for red in rd.list_networks():
        for c in CASES:
            print("escrito", write_dss(red, c).relative_to(ROOT))
