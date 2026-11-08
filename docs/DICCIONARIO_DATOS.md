# Diccionario de datos

Todas las redes usan la misma estructura. Cada red vive en `data/<red>/`.

## Convenciones

- CSV con separador `,`, punto decimal `.`, UTF-8 y encabezado.
- **Los IDs de barras, circuitos y conductores son los de la tesis original** (no se renumeraron).
- Unidades: kW, kvar, kVA, MVA, kV, km, Ω/km, A. Los costos están en **unidades completas** de la moneda
  indicada en `system.json` (los valores que la tesis da en 10³ se multiplicaron por 1000).
- `null` en `system.json` significa que la tesis no informa ese dato para esa red.

## Archivos presentes en todas las redes

### `system.json` — parámetros generales

| clave | descripción |
|---|---|
| `name` | identificador de la red |
| `source` | tablas, figuras y secciones de la tesis de donde salen los datos |
| `V_kV` | tensión nominal |
| `stages` | número de etapas del horizonte de planeamiento |
| `years_per_stage` | duración de cada etapa en años |
| `V_min_pu`, `V_max_pu` | límites de tensión |
| `interest_rate` | tasa de interés anual (para valor presente) |
| `loss_factor` | factor de pérdidas usado en la tesis |
| `energy_cost_per_kWh` | costo de la energía de pérdidas (`null` si no se informa) |
| `power_factor` | fp usado para obtener P y Q a partir de S (`null` si la tesis da P y Q) |
| `currency` | moneda de todos los costos (`US$` o `R$`) |

Claves adicionales en algunas redes: `V_source_pu` (tensión fija en la subestación),
`se_operation_cost_per_kVA2h` (costo de operación de la subestación) y `line_model`
(`per_circuit`: ver red27).

### `buses.csv` — barras

| columna | tipo | descripción |
|---|---|---|
| `bus` | int | ID de la barra |
| `type` | str | `load` (carga), `SE` (subestación existente), `SE_cand` (subestación candidata), `paso` (sin carga en ninguna etapa) |
| `x`, `y` | float | coordenadas del nodo en la figura de la tesis, en **puntos PDF** (1 pt = 1/72 pulgada), `y` positiva hacia arriba. Sirven para dibujar la red, **no** para medir distancias (usar `lines.length_km`). |
| `load_class` | str | `res`, `com`, `ind` o `none`; elige la curva de carga |
| `n_consumers` | int | número de consumidores (última etapa) |

### `loads.csv` — demanda pico por etapa

| columna | tipo | descripción |
|---|---|---|
| `bus` | int | barra (solo barras `load`) |
| `stage` | int | etapa, de 1 a `stages` |
| `P_kW` | float | potencia activa pico |
| `Q_kvar` | float | potencia reactiva pico |

Una fila por barra de carga y etapa, también cuando la demanda de esa etapa es 0.

### `lines.csv` — corredores (existentes y candidatos)

| columna | tipo | descripción |
|---|---|---|
| `line` | int | ID del circuito |
| `from`, `to` | int | barras extremas |
| `length_km` | float | longitud |
| `status` | str | `existing` (ya construido) o `candidate` (puede construirse) |
| `conductor` | int | tipo de conductor instalado; `0` en candidatos |

### `conductors.csv` — catálogo de conductores

| columna | tipo | descripción |
|---|---|---|
| `type` | int | tipo de conductor |
| `R_ohm_km`, `X_ohm_km` | float | resistencia y reactancia |
| `Imax_A` | float | capacidad de corriente |
| `cost_per_km` | float | costo de construcción por km (`0.0` si los costos son por circuito, ver `line_costs.csv`) |

### `substations.csv` — subestaciones y alternativas

| columna | tipo | descripción |
|---|---|---|
| `bus` | int | barra de la subestación |
| `status` | str | `existing` o `candidate` |
| `cap_MVA` | float | capacidad actual (0 si es candidata) |
| `option` | int | `0` = estado actual; `1, 2, …` = alternativas de ampliación o construcción |
| `cap_new_MVA` | float | capacidad si se elige esa opción |
| `cost` | float | costo de la opción |

## Archivos presentes solo en algunas redes

### `recond_cost.csv` — recondutoramiento (red54, red417)
| columna | descripción |
|---|---|
| `from_type`, `to_type` | conductor actual → conductor nuevo (`from_type < to_type`) |
| `cost_per_km` | costo de cambiar el conductor, por km |

### `line_costs.csv` — costo por circuito (red27)
| columna | descripción |
|---|---|
| `line` | circuito |
| `conductor` | conductor que se puede instalar en ese circuito |
| `cost` | costo total del circuito con ese conductor |

En circuitos existentes solo aparecen las opciones de recondutoramiento.

### `consumers.csv` — consumidores por etapa (red27)
`bus, stage, n_consumers`.

### `reliability.json` — confiabilidad (red27)
Tasa de fallas por circuito (`failure_rate_per_year`), tiempo de reparación (`repair_time_h`),
tiempo de reconfiguración (`switching_time_h`) y límites regulatorios de los índices de continuidad:
`DIC_max_h`, `FIC_max` (por consumidor) y `DEC_max_h`, `FEC_max` (por alimentador).

## Solución de referencia: `data/<red>/solution_camargo/`

Solución publicada por Camargo (2014) para cada red, tal como se simula en `opendss/<red>/camargo/`.

### `lines.csv` — conductor de cada corredor por etapa
| Columna | Tipo | Descripción |
|---|---|---|
| `line` | int | corredor (`lines.csv` de la red) |
| `stage` | int | etapa |
| `conductor` | int | tipo de conductor en servicio en esa etapa; **0 = no construido o abierto** |

Estado derivado (`Network.topology`): `existente` (existing con su conductor original), `recondutorada`
(existing con otro conductor), `nueva` (candidate construida). Un corredor con `conductor = 0` que estuvo en
servicio antes (o era existing) está **abierto**.

### `substations.csv` — subestaciones activas por etapa
| Columna | Tipo | Descripción |
|---|---|---|
| `bus` | int | barra de la SE |
| `stage` | int | etapa |
| `option` | int | alternativa activa (`substations.csv` de la red); 0 = configuración existente |

### `reference.json` — resultados publicados y validación
| Clave | Descripción |
|---|---|
| `source` | sección y tablas de la tesis |
| `stages`, `losses_kW`, `vmin_pu` | pérdidas (kW) y tensión mínima (pu) publicadas por etapa |
| `substation_MVA` | potencia de cada SE por etapa (null si la tesis no la informa) |
| `v_source_pu_thesis` | tensión de la fuente informada en la tesis (null si no la informa) |
| `v_source_pu_opendss` | tensión de la fuente con la que OpenDSS reproduce los resultados |
| `opendss_validation` | pérdidas, Vmin y MVA de cada SE obtenidos en OpenDSS por etapa |

## Modelos OpenDSS: `opendss/<red>/<caso>/`

`caso` = `base` (caso 0, red inicial) o `camargo`. Por etapa `s`: `master_e{s}.dss` (compila y resuelve),
`fuentes_e{s}.dss`, `lineas_e{s}.dss`, `cargas_e{s}.dss`, `no_energizadas_e{s}.csv` (cargas sin camino a una SE,
no simuladas); comunes: `linecodes.dss`, `buscoords.csv`. Barras `b<número>`; líneas `L<line>`; cargas `LD<bus>`;
la primera SE es la fuente del circuito y las demás `Vsource.SE<bus>`. Se regeneran con
`python redes_dnep_opendss.py`.

## Archivo compartido: `data/load_curves.csv`

Curvas de 24 h en p.u. del pico (máximo = 1.0) para las clases `res`, `com` e `ind`.
Carga horaria de una barra: `P(h) = P_kW · curva[load_class][h]` (igual para Q).
Factores de pérdidas resultantes: res 0.40, com 0.48, ind 0.68.

> Estas curvas **no provienen de la tesis** (que solo da la demanda pico): son curvas típicas
> elegidas para este conjunto de datos. Se pueden reemplazar por curvas propias.
