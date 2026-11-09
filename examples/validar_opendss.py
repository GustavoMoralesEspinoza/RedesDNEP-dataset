"""Reproduce en OpenDSS las pérdidas y la tensión mínima publicadas (Camargo 2014; red18: Morales 2024).

    pip install py-dss-interface        (Windows)
    python examples/validar_opendss.py

Solo se ajusta la tensión de la fuente (reference.json -> v_source_pu_opendss); cargas, impedancias y
topologías son las de la base de datos. Tolerancias: pérdidas ±5 %, Vmin ±0,005 pu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redes_dnep as rd  # noqa: E402
import redes_dnep_opendss as rdo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ok_total = True
print(f"{'red':7} {'etapa':>5} {'V pu':>6} {'pérdidas kW':>12} {'tesis':>9} {'err %':>6} "
      f"{'Vmin pu':>8} {'tesis':>6} {'sin energía':>11}  ok")
for name in rd.list_networks():
    ref = rd.load_network(name).solution["reference"]
    for k, stage in enumerate(ref["stages"]):
        r = rdo.simulate(name, "reference", stage)
        e_loss = 100 * (r["losses_kW"] - ref["losses_kW"][k]) / ref["losses_kW"][k]
        vref = ref["vmin_pu"][k]  # red18: la tesis no publica Vmin -> se exige cumplir los límites de la red
        net_s = rd.load_network(name).system
        e_v = (r["vmin_pu"] - vref) if vref is not None else 0.0
        if vref is None and not (net_s["V_min_pu"] <= r["vmin_pu"] and r["vmax_pu"] <= net_s["V_max_pu"] + 1e-9):
            e_v = 1.0
        ok = r["converged"] and abs(e_loss) <= 5 and abs(e_v) <= 0.005 and r["unserved_loads"].empty
        ok_total &= ok
        print(f"{name:7} {stage:>5} {r['v_source_pu']:>6.3f} {r['losses_kW']:>12.2f} {ref['losses_kW'][k]:>9.2f} "
              f"{e_loss:>6.2f} {r['vmin_pu']:>8.4f} {'  —' if ref['vmin_pu'][k] is None else format(ref['vmin_pu'][k], '6.3f'):>6} {len(r['unserved_loads']):>11}  "
              f"{'sí' if ok else 'NO'}")

# Caso 0: la red inicial frente a la demanda de cada etapa
print("\nCaso 0 (red inicial, 1,00 pu):")
for name in rd.list_networks():
    for stage in range(1, rd.load_network(name).system["stages"] + 1):
        r = rdo.simulate(name, "base", stage, v_source_pu=1.0)
        print(f"  {name:7} etapa {stage}: pérdidas {r['losses_kW']:8.2f} kW, Vmin {r['vmin_pu']:.4f} pu, "
              f"{len(r['unserved_loads'])} cargas sin energía ({r['unserved_loads'].P_kW.sum():,.0f} kW), "
              f"{len(r['overloaded_lines'])} líneas sobrecargadas")

print("\nRESULTADO:", "todas las redes reproducen la tesis" if ok_total else "HAY DIFERENCIAS")
sys.exit(0 if ok_total else 1)
