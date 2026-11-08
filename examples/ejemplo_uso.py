"""Ejemplo de uso de la base de datos. Ejecutar desde la raíz del repositorio:

    python examples/ejemplo_uso.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redes_dnep as rd  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # acentos correctos en la consola de Windows
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Ver qué redes hay y un resumen de cada una
for name in rd.list_networks():
    print(rd.load_network(name).summary(), end="\n\n")

# 2. Trabajar con una red concreta
net = rd.load_network("red54")

# Barras de carga con mayor demanda en la última etapa
last = net.system["stages"]
top = net.peak_loads(last).sort_values("P_kW", ascending=False).head(5)
print(f"Barras con mayor demanda en la etapa {last} de {net.name}:\n{top}\n")

# Corredores existentes con su impedancia (conductor instalado)
existing = net.lines_with_impedance()
print(existing[existing.status == "existing"][["line", "from", "to", "length_km", "conductor", "R_ohm", "X_ohm"]].head(), "\n")

# 3. Carga horaria (curvas estándar de 24 h) y demanda total del sistema por hora
h = net.hourly_loads(stage=1)
print("Demanda total por hora (etapa 1, MW):")
print((h.groupby("hour").P_kW.sum() / 1000).round(2).to_string(), "\n")

# 4. Exportar a SQLite para consultarla como base de datos
db = rd.export_sqlite(Path(__file__).resolve().parents[1] / "redes.sqlite")
print(f"Base SQLite creada en: {db}")
