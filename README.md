# Redes de prueba para el planeamiento de la expansión de redes de distribución (DNEP)

Base de datos abierta, en formato tabular (CSV + JSON), con **cuatro redes de distribución de prueba**
listas para usarse como entrada de algoritmos de **planeamiento de la expansión de sistemas de
distribución** (*Distribution Network Expansion Planning*, DNEP): construcción y recondutoramiento de
circuitos, ampliación y construcción de subestaciones, planeamiento multietapa, confiabilidad y,
como extensión, incorporación de recursos energéticos distribuidos (DER).

*English summary:* four benchmark distribution systems (23, 27, 54 and 417 buses) for distribution
network expansion planning, digitized from the appendices of Camargo (2014) into a common CSV/JSON
schema, with a small Python loader and exports to Excel and SQLite.

---

## ¿Para qué sirve?

Las redes de prueba de planeamiento de distribución suelen estar solo en tablas de tesis y artículos
en PDF, cada una con su propio formato. Este repositorio las reúne en **una estructura común**, para que
cualquier persona pueda:

- usarlas directamente como entrada de modelos de optimización (MILP, metaheurísticas, etc.);
- comparar sus resultados con los publicados (cada red incluye su **resultado de referencia**);
- extenderlas: escenarios de crecimiento de carga, curvas horarias, ubicación de DER, etc.

## Origen de los datos

Todos los datos de red provienen de los anexos de la tesis doctoral:

> CAMARGO, Vera Lúcia Vieira de. **Algoritmo genético especializado aplicado ao planejamento da expansão
> de sistemas de distribuição de energia elétrica.** 2014. 175 f. Tese (Doutorado em Engenharia Elétrica) —
> Faculdade de Engenharia de Ilha Solteira, Universidade Estadual Paulista (UNESP), Ilha Solteira, 2014.
> Orientador: Rubén Augusto Romero Lázaro. Coorientadora: Marina Lavorato de Oliveira.

La tesis, a su vez, recopila sistemas de la literatura (las fuentes originales se indican en cada red).
Los datos se extrajeron por código desde el PDF y se verificaron contra los balances de potencia
publicados en la propia tesis. **Este repositorio no incluye la tesis**; consúltela en el repositorio
institucional de la UNESP.

## Las redes

| Red | Tensión | Barras | Corredores (exist./cand.) | Etapas | Tipo de problema | Fuente original |
|---|---|---|---|---|---|---|
| [`red23`](data/red23/README.md) | 34,5 kV | 23 | 0 / 35 | 1 × 20 años | Estático, red nueva | Oliveira (2010) |
| [`red27`](data/red27/README.md) | 13,8 kV | 27 | 8 / 31 | 3 × 1 año | Multietapa **+ confiabilidad** | Lotero y Contreras (2011) |
| [`red54`](data/red54/README.md) | 15 kV | 54 | 16 / 45 | 3 × 5 años | Multietapa | Miranda et al. (1994), Baquero (2012) |
| [`red417`](data/red417/README.md) | 10 kV | 417 | 88 / 385 | 3 × 5 años | Multietapa, gran escala | Bernal-Agustín (1998), Baquero (2012) |

| red23 | red27 |
|---|---|
| ![red23](figuras/red23.png) | ![red27](figuras/red27.png) |
| **red54** | **red417** |
| ![red54](figuras/red54.png) | ![red417](figuras/red417.png) |

Líneas sólidas: circuitos existentes. Líneas discontinuas: corredores candidatos. Cuadrados: subestaciones.

## Estructura del repositorio

```
data/
├── load_curves.csv          curvas de carga estándar de 24 h (res, com, ind)
├── red23/  red27/  red54/  red417/
│   ├── README.md            descripción, supuestos y resultado de referencia de la red
│   ├── system.json          parámetros: tensión, etapas, límites, economía
│   ├── buses.csv            barras: tipo, coordenadas, clase de carga, consumidores
│   ├── loads.csv            demanda pico P, Q por barra y etapa
│   ├── lines.csv            corredores existentes y candidatos, longitud, conductor
│   ├── conductors.csv       catálogo de conductores: R, X, Imax, costo
│   ├── substations.csv      subestaciones existentes/candidatas y sus alternativas
│   └── (opcionales)         recond_cost.csv, line_costs.csv, consumers.csv, reliability.json
docs/DICCIONARIO_DATOS.md    descripción de cada archivo y columna
figuras/                     dibujo de cada red
redes_dnep.py                cargador en Python (solo requiere pandas)
examples/ejemplo_uso.py      ejemplo completo
```

El detalle de cada columna y unidad está en **[docs/DICCIONARIO_DATOS.md](docs/DICCIONARIO_DATOS.md)**.

## Uso

### Sin programar
Los archivos son CSV: se abren directamente en Excel, LibreOffice, MATLAB (`readtable`), R (`read.csv`)
o cualquier otra herramienta.

### Con Python

```bash
pip install -r requirements.txt
python examples/ejemplo_uso.py
```

```python
import redes_dnep as rd

rd.list_networks()                      # ['red23', 'red27', 'red417', 'red54']
net = rd.load_network("red54")
print(net.summary())

net.buses, net.lines, net.loads         # pandas.DataFrame
net.system["V_kV"]                      # parámetros de system.json
net.peak_loads(stage=2)                 # demanda pico de la etapa 2
net.hourly_loads(stage=2)               # 24 h por barra con las curvas estándar
net.lines_with_impedance()              # R_ohm, X_ohm de cada corredor (conductor instalado)
net.lines_with_impedance(conductor=3)   # ... o evaluando todos con el conductor 3
```

### Como base de datos (SQLite o Excel)

```python
rd.export_sqlite("redes.sqlite")          # todas las redes; cada tabla con columna `network`
rd.export_excel("red27", "red27.xlsx")    # una hoja por tabla (requiere openpyxl)
```

```sql
-- demanda total por red y etapa
SELECT network, stage, SUM(P_kW)/1000 AS P_MW FROM loads GROUP BY network, stage;
```

## Supuestos y limitaciones (léase antes de usar)

- **Curvas de carga:** la tesis solo da la demanda pico. `data/load_curves.csv` contiene curvas **típicas
  elegidas para este conjunto de datos** (no provienen de la tesis); se pueden reemplazar.
- **Clase de carga y número de consumidores:** solo `red27` trae consumidores en la fuente. En las demás,
  `load_class` y `n_consumers` se estimaron con una regla fija (ver el diccionario de datos).
- **Coordenadas:** están en puntos de la figura del PDF; sirven para dibujar, no para medir distancias.
  En `red417` el reconocimiento de etiquetas se confirmó para el 84 % de los segmentos dibujados.
- **red27:** sin longitudes en la fuente; se usa un modelo por circuito (`length_km = 1`) y fp = 0,9 supuesto.
- **red54 y red417:** la tesis no informa el costo de la energía (`energy_cost_per_kWh = null`).
- Los costos están en la moneda original de cada red (US$ o R$) y no se convirtieron entre sí.

Los detalles de cada red están en su `README.md`.

## Cómo citar

Si usa estos datos, cite la tesis de origen (arriba) y las fuentes originales de cada red.
Ver también [`CITATION.cff`](CITATION.cff).

## Licencia

*Pendiente de definir por el autor del repositorio.* Los datos derivan de trabajos académicos
publicados; se recomienda citar siempre la fuente original.
