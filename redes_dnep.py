"""redes_dnep — cargador de la base de datos de redes de distribución para DNEP.

Uso rápido:

    import redes_dnep as rd

    rd.list_networks()                  # ['red23', 'red27', 'red417', 'red54']
    net = rd.load_network("red54")
    net.buses, net.lines, net.loads     # pandas.DataFrame
    print(net.summary())

    net.hourly_loads(stage=3)           # carga de cada barra en las 24 h (curvas estándar)
    net.lines_with_impedance()          # R y X en ohm de cada corredor según su conductor
    lines, subs = net.topology(stage=2, case="camargo")   # solución de la tesis en la etapa 2
    rd.export_excel("red54", "red54.xlsx")      # una hoja por tabla (requiere openpyxl)
    rd.export_sqlite("redes.sqlite")            # todas las redes en una base SQLite

Solo depende de pandas (y de openpyxl si exporta a Excel).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

_TABLES = ["buses", "loads", "lines", "conductors", "substations"]
_OPTIONAL_TABLES = ["recond_cost", "line_costs", "consumers"]


@dataclass
class Network:
    """Una red de distribución: parámetros (`system`) y tablas como DataFrames."""

    name: str
    system: dict
    buses: pd.DataFrame
    loads: pd.DataFrame
    lines: pd.DataFrame
    conductors: pd.DataFrame
    substations: pd.DataFrame
    recond_cost: Optional[pd.DataFrame] = None
    line_costs: Optional[pd.DataFrame] = None
    consumers: Optional[pd.DataFrame] = None
    reliability: Optional[dict] = None
    solution: Optional[dict] = None
    _curves: Optional[pd.DataFrame] = field(default=None, repr=False)

    # ------------------------------------------------------------------ vistas
    def tables(self) -> dict[str, pd.DataFrame]:
        """Todas las tablas presentes, por nombre."""
        out = {t: getattr(self, t) for t in _TABLES}
        out.update({t: getattr(self, t) for t in _OPTIONAL_TABLES if getattr(self, t) is not None})
        return out

    def summary(self) -> str:
        s, b, ln = self.system, self.buses, self.lines
        lines = [
            f"{self.name}: {s['V_kV']} kV, {s['stages']} etapa(s) de {s['years_per_stage']} año(s), moneda {s['currency']}",
            f"  barras: {len(b)} ({', '.join(f'{k}={v}' for k, v in b.type.value_counts().items())})",
            f"  corredores: {len(ln)} (existentes={int((ln.status == 'existing').sum())}, "
            f"candidatos={int((ln.status == 'candidate').sum())}), {ln.length_km.sum():.2f} km",
            f"  conductores: {len(self.conductors)} tipos; opciones de subestación: {len(self.substations)}",
        ]
        for st, g in self.loads.groupby("stage"):
            lines.append(f"  etapa {st}: P = {g.P_kW.sum() / 1000:.2f} MW, Q = {g.Q_kvar.sum() / 1000:.2f} Mvar")
        extras = [t for t in _OPTIONAL_TABLES if getattr(self, t) is not None]
        if self.reliability is not None:
            extras.append("reliability")
        if extras:
            lines.append(f"  datos adicionales: {', '.join(extras)}")
        return "\n".join(lines)

    def peak_loads(self, stage: int) -> pd.DataFrame:
        """Carga pico (P_kW, Q_kvar) de cada barra en una etapa."""
        self._check_stage(stage)
        return self.loads[self.loads.stage == stage].reset_index(drop=True)

    def hourly_loads(self, stage: int, curves: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Carga horaria de cada barra: P(h) = P_pico · curva[clase](h), igual para Q.

        `curves` permite usar curvas propias (columnas: hour, res, com, ind, ... en p.u.).
        """
        curves = load_curves() if curves is None else curves
        peak = self.peak_loads(stage).merge(self.buses[["bus", "load_class"]], on="bus")
        missing = set(peak.load_class) - set(curves.columns)
        if missing:
            raise ValueError(f"faltan curvas para las clases {sorted(missing)}")
        rows = []
        for _, r in peak.iterrows():
            f = curves[r.load_class].to_numpy()
            rows.append(pd.DataFrame({"bus": r.bus, "stage": stage, "hour": curves.hour,
                                      "P_kW": r.P_kW * f, "Q_kvar": r.Q_kvar * f}))
        return pd.concat(rows, ignore_index=True)

    def lines_with_impedance(self, conductor: Optional[int] = None) -> pd.DataFrame:
        """Corredores con R_ohm y X_ohm.

        Usa el conductor instalado (existentes) o, si se indica, `conductor` para todos.
        Los candidatos sin conductor quedan con NaN salvo que se pase `conductor`.
        En redes con `line_model = per_circuit` (red27) length_km = 1 y R/X ya son por circuito.
        """
        ln = self.lines.copy()
        ln["conductor_eval"] = conductor if conductor is not None else ln.conductor.where(ln.conductor > 0)
        cd = self.conductors.rename(columns={"type": "conductor_eval"})
        ln = ln.merge(cd[["conductor_eval", "R_ohm_km", "X_ohm_km", "Imax_A"]], on="conductor_eval", how="left")
        ln["R_ohm"] = ln.R_ohm_km * ln.length_km
        ln["X_ohm"] = ln.X_ohm_km * ln.length_km
        return ln

    def topology(self, stage: int = 1, case: str = "camargo") -> tuple[pd.DataFrame, pd.DataFrame]:
        """Topología de una etapa: (líneas en servicio con su conductor, SE activas con su capacidad).

        case = "base"    -> caso 0: solo circuitos y SE existentes (opción 0); `stage` no cambia la red.
        case = "camargo" -> solución publicada en la tesis (data/<red>/solution_camargo/).
        Cada línea devuelta lleva `state`: existente | recondutorada | nueva.
        """
        self._check_stage(stage)
        ln, ss = self.lines, self.substations
        if case == "base":
            act = ln[ln.status == "existing"].copy()
            se = ss[(ss.status == "existing") & (ss.option == 0)]
        elif case == "camargo":
            if self.solution is None:
                raise ValueError(f"{self.name} no tiene solución de referencia")
            top = self.solution["lines"]
            top = top[(top.stage == stage) & (top.conductor > 0)][["line", "conductor"]]
            act = ln.rename(columns={"conductor": "conductor_original"}).merge(top, on="line")
            sel = self.solution["substations"]
            se = ss.merge(sel[sel.stage == stage][["bus", "option"]], on=["bus", "option"])
        else:
            raise ValueError("case debe ser 'base' o 'camargo'")
        if "conductor_original" not in act:
            act["conductor_original"] = act.conductor
        act["state"] = "nueva"
        act.loc[(act.status == "existing") & (act.conductor == act.conductor_original), "state"] = "existente"
        act.loc[(act.status == "existing") & (act.conductor != act.conductor_original), "state"] = "recondutorada"
        cols = ["line", "from", "to", "length_km", "status", "conductor_original", "conductor", "state"]
        return act[cols].reset_index(drop=True), se.reset_index(drop=True)

    def _check_stage(self, stage: int) -> None:
        if not 1 <= stage <= self.system["stages"]:
            raise ValueError(f"{self.name} tiene etapas 1..{self.system['stages']}")


# ---------------------------------------------------------------------- API
def list_networks() -> list[str]:
    """Nombres de las redes disponibles en data/."""
    return sorted(p.name for p in DATA_DIR.iterdir() if (p / "system.json").exists())


def load_curves() -> pd.DataFrame:
    """Curvas de carga estándar de 24 h (p.u. del pico) por clase: res, com, ind."""
    return pd.read_csv(DATA_DIR / "load_curves.csv")


def load_network(name: str) -> Network:
    """Carga una red por nombre (p. ej. 'red54')."""
    d = DATA_DIR / name
    if not (d / "system.json").exists():
        raise FileNotFoundError(f"red '{name}' no encontrada; disponibles: {list_networks()}")
    kw = {"name": name, "system": json.loads((d / "system.json").read_text(encoding="utf-8"))}
    for t in _TABLES:
        kw[t] = pd.read_csv(d / f"{t}.csv")
    for t in _OPTIONAL_TABLES:
        p = d / f"{t}.csv"
        kw[t] = pd.read_csv(p) if p.exists() else None
    rel = d / "reliability.json"
    kw["reliability"] = json.loads(rel.read_text(encoding="utf-8")) if rel.exists() else None
    sol = d / "solution_camargo"
    if sol.exists():
        kw["solution"] = {"lines": pd.read_csv(sol / "lines.csv"),
                          "substations": pd.read_csv(sol / "substations.csv"),
                          "reference": json.loads((sol / "reference.json").read_text(encoding="utf-8"))}
    return Network(**kw)


def export_excel(name: str, path: str | Path) -> Path:
    """Exporta una red a Excel: una hoja por tabla + hoja 'system'. Requiere openpyxl."""
    net = load_network(name)
    path = Path(path)
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame([(k, str(v)) for k, v in net.system.items()], columns=["key", "value"]).to_excel(
            xw, sheet_name="system", index=False)
        for t, df in net.tables().items():
            df.to_excel(xw, sheet_name=t, index=False)
        if net.reliability:
            pd.DataFrame(list(net.reliability.items()), columns=["key", "value"]).to_excel(
                xw, sheet_name="reliability", index=False)
    return path


def export_sqlite(path: str | Path, networks: Optional[list[str]] = None) -> Path:
    """Exporta redes a una base SQLite. Cada tabla lleva una columna `network`.

    Tablas: system, buses, loads, lines, conductors, substations, recond_cost,
    line_costs, consumers, reliability, load_curves.
    """
    path = Path(path)
    if path.exists():
        path.unlink()
    frames: dict[str, list[pd.DataFrame]] = {}
    sys_rows, rel_rows = [], []
    for name in networks or list_networks():
        net = load_network(name)
        sys_rows.append({"network": name, **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                                             for k, v in net.system.items()}})
        for t, df in net.tables().items():
            frames.setdefault(t, []).append(df.assign(network=name))
        if net.reliability:
            rel_rows.append({"network": name, **net.reliability})
    with sqlite3.connect(path) as con:
        pd.DataFrame(sys_rows).to_sql("system", con, index=False)
        if rel_rows:
            pd.DataFrame(rel_rows).to_sql("reliability", con, index=False)
        for t, dfs in frames.items():
            pd.concat(dfs, ignore_index=True).to_sql(t, con, index=False)
        load_curves().to_sql("load_curves", con, index=False)
    return path
