# S2.2g — Plan detallado: marco estructural primero (C) + posiciones por optimización (E)

*12 oct 2026 · plan para aprobación, sin código*

## 0. Decisiones del cliente (18:45)

| Tema | Decisión |
|---|---|
| Enfoque | **C + E**: soporte o marco estructural primero, posiciones por optimización; la verificación de S2.2f (A) queda al final |
| Planta alta de 30 a 40 ft (lado corto) | **Pasillo central con 2 ejes** (crujía de cuartos / pasillo / crujía de cuartos) |
| Sobrante de la planta baja | **Cualquiera de los dos**: porche techado o huella más chica, según la fachada |
| Eje del núcleo de la escalera | **Un candidato más** (sin prioridad) |

## 1. Análisis lógico

### 1.1 Qué cambia y qué se conserva

| Hoy | S2.2g |
|---|---|
| Cada planta elige su dirección de bandas (la baja solo `y`; la alta `x` o `y`) | **Una dirección por casa**, la del marco, para las dos plantas |
| Cortes de banda por área | **Cortes de banda = ejes del marco** (fijos o con una pequeña ventana) |
| 1–2 bandas por planta | 1–4 bandas: crujías bajo la planta alta y las franjas de la planta baja fuera de ella |
| Columnas por área dentro de la banda | Igual, pero por área **óptima**; el sobrante va a techo (arriba) o porche o huella menor (abajo) |
| Alineación buscada después (snap, puntaje) | Alineación **por construcción** y verificada al 100 % sobre los ejes declarados |

Se conserva:
- el motor de bandas y columnas (`core_zoning`) y todas sus verificaciones (ancho, llegada, puertas, K01, K04,
  hall de escalera, anclas, matriz);
- S2.1 por zonas, techos y terrazas (S2.2d), topes de área (S2.2e), llegada compacta y puertas agrupadas (S2.2f).

### 1.2 El marco

```
dirección de viguetas   = a través del lado corto de la planta alta (S)
ejes (paralelos al lado largo):
  contorno de la planta alta (fijo)
  junta: el borde de la planta alta sobre la planta baja (fijo, si existe)
  candidatos interiores: muros largos del núcleo de escalera, muros del garage, posiciones libres (retícula 0.5 ft)
patrón por S:
  S ≤ 20 ft        → 0 ejes interiores                         (1 crujía)
  20 < S ≤ 30 ft   → 1 eje                                    (2 crujías, cada una entre bay_min y 20 ft)
  30 < S ≤ 40 ft   → 2 ejes = pasillo central                 (crujía | pasillo | crujía; pasillo = ancho de hall)
variantes: las 2–3 mejores combinaciones (crujías equilibradas, ejes sobre elementos fijos cuando caen cerca)
```

Datos medidos (283 casas de dos pisos):
- 86 no necesitan eje interior (S ≤ 20 ft);
- 197 necesitan 1 o 2;
- ninguna necesita más de 2;
- la planta alta está sobre el garage en 234 casas, y los muros del garage son candidatos naturales.

### 1.3 Zonificación por crujías (S2)

- **Planta alta:** las bandas son las crujías.
  - En el patrón de pasillo central, la crujía del medio es la zona de **circulación**: es el pasillo y nace en el
    descanso. Se cumplen a la vez la llegada compacta, el pasillo único y las puertas en fila.
  - Las crujías laterales llevan las zonas privadas y sociales en columnas por área.
- **Planta baja:** los mismos ejes prolongados son cortes de banda en toda la planta. Fuera de la huella alta la
  planta baja tiene libertad (sin carga arriba).
  - En la gran sala abierta, un eje sin muro es una **viga sobre el eje**: sigue siendo eje compartido.
- **Sobrante:**
  - arriba, al final de cada crujía sobre fachada → **techo** o terraza ≤ 3 ft (mecanismo de S2.2d llevado a S2);
  - abajo → **porche techado** si da al jardín o a la calle, o **huella más chica** en las otras fachadas.

### 1.4 Optimización de posiciones (E)

Por cada variante de marco y cada par de topologías prometedoras (baja × alta), un **MILP pequeño** con
`scipy.optimize.milp` (HiGHS):

- **Variables (en celdas de 0.5 ft):** posición de los ejes libres dentro de su ventana, cortes de columna de cada
  banda en cada planta y holgura de techo o porche por banda.
- **Restricciones:**
  - eje alto = eje bajo (es la misma variable);
  - cada crujía bajo la planta alta ≤ 20 ft y ≥ `bay_min`;
  - anchos mínimos de zona;
  - la columna de llegada cubre el descanso;
  - el núcleo de la escalera dentro de su crujía;
  - franja K12.
- **Objetivo:** mínimo desvío ponderado de área de las zonas respecto de su óptimo, más un costo pequeño por pie² de
  techo o porche (para no regalar área).
- **Área exacta:** la planta no es un rectángulo perfecto (garage, escalera, polígonos). El MILP usa la
  aproximación rectangular y luego un ajuste entero local (±2 celdas) con las sumas de prefijos exactas que ya usa
  `core_zoning`.
- **Tamaño:** unas 10–30 variables; milisegundos por par.

### 1.5 Verificación y salida

- Los **ejes declarados** van en el bloque `s2.frame` y en `s21.structure.frame`.
- `floor_structure` verifica: cada eje con muro o viga en la planta baja (100 %), crujías ≤ 20 ft, vigas ≤ 20 ft
  entre apoyos.
- Los tabiques interiores no se exigen; el snap blando de S2.2f queda solo para ellos.

### 1.6 Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Programas que no caben en crujías fijas (por ejemplo, suite de 16 ft en crujía de 12 ft) | 2–3 variantes de marco; ventanas en los ejes libres; el MILP mueve ejes libres |
| Más bandas = más topologías | Topologías por asignación de zonas a crujías (pocas zonas por planta), con el tope `max_topologies` actual |
| Cobertura menor al principio | Medir tras cada fase (G2, G3) contra S2.2f (25 casas) y S2.2e (32) |
| Planta baja fuera de la huella alta con formas pobres | Puntuar forma como hoy; bandas libres fuera de la huella |
| Tiempo de cálculo | MILP en milisegundos; se limita a las top-k topologías por planta |
| Fixtures y golden de stacking | Solo la etapa S2.1 usa el marco (como S2.2f); se refrescan los fixtures |

## 2. Plan de acción (un paso, cinco fases con medición)

| Fase | Trabajo | Módulos (main / lib / lib_aux) | Medición al cerrar la fase |
|---|---|---|---|
| **G1 · Datos y marco** | `design_structure` T03-FRAME: `bay_min_ft`, umbrales de patrón (20 / 30 / 40 ft), `spine_hall_ft` (del catálogo), `frame_variants` 3, `axis_window_ft`, `ground_surplus` = `either`, `roof_cost`. `lib/structural_frame.py`: candidatos y variantes. `lib_aux/frame_geometry.py`: líneas, crujías, ventanas. Herramientas LLM, grupo `structure`. | data, design, stacking/lib, stacking/lib_aux | En las 283 casas: patrón, crujías y ejes sobre elementos fijos (sin tocar el pipeline) |
| **G2 · S2 por crujías** | `core_zoning`: modo `framed` (dirección fija, cortes de banda = ejes, N bandas, asignación de zonas a crujías, la circulación en la crujía de pasillo); sobrante como pseudo-zona de techo o porche. `zone_cell`: marco → búsqueda en ambas plantas con los mismos ejes. | stacking/lib | Plantas zonificadas, ejes compartidos (100 %), cobertura en S2 |
| **G3 · MILP de posiciones** | `lib/frame_positions.py` (MILP con scipy/HiGHS) + `lib_aux/milp_tools.py`: ejes libres y cortes conjuntos, con ajuste entero local | stacking/lib, lib_aux | Desvío de área, cobertura, tiempo por casa |
| **G4 · S2.1 y verificación** | Techo o porche de S2 llevado a S2.1 (techo arriba: `open_air`; porche abajo: nuevo `open_air` "porch"); verificación con ejes declarados; bloques `frame` en la salida; KPIs (ejes compartidos, crujías, área a techo o porche, alineación de tabiques). Esquema del contrato. | stacking/lib, main, contracts, viz (porche y ejes en las láminas) | Piloto completo (10 lotes, 291 celdas) |
| **G5 · Cierre** | Pruebas (marco, MILP, crujías, verificación), fixtures, HANDOFF 4z, resultados, documento del proyecto | tests, docs | Suite completa en verde; comparación contra S2.2e y S2.2f |

**Calendario:** dentro del cierre de S2.2 (diciembre de 2026). 6.7b (enero de 2027) y 6.8 (febrero de 2027) no se
mueven.

## 3. Criterios de éxito

| Indicador | Objetivo |
|---|---|
| Ejes compartidos con muro o viga abajo | **100 %** (por construcción) |
| Muros de arriba sobre muros de abajo (incluye tabiques) | > 40 % (hoy 9 %) |
| Plantas en la misma dirección | 100 % (hoy 6 de 32) |
| Crujías ≤ 20 ft bajo la planta alta | 100 % |
| Cobertura | ≥ 25 casas (S2.2f); objetivo 32 (S2.2e) |
| Llegada compacta, pasillo único | se mantiene |

## 4. Innovación (pasos futuros)

- **Catálogo de marcos** (crujía simple, doble, pasillo central, núcleo central) que un LLM elige y explica al
  cliente.
- **Aprendizaje:** priorizar marcos y topologías con los resultados de los pilotos.
- **Prefabricación:** crujías en módulos de 2 ft, con cómputo de desperdicio.
- **Techos en varios planos** desde las crujías en techo y el porche.
- **Paquete estructural para el ingeniero:** ejes, vigas y postes.
