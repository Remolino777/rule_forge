# S2.2g — Análisis a fondo: muros estructurales compartidos, crujías, techo y núcleo de escalera

*12 oct 2026 · análisis, sin código*

## 1. Por qué hoy cuesta alinear muros (con datos)

| Dato | Valor | Lectura |
|---|---|---|
| Casas resueltas cuyas dos plantas se dividen en **la misma dirección** (bandas paralelas) | **6 de 32** | En 26 de 32 la planta alta se corta en x y la baja en y. Sus muros principales son perpendiculares: alinear es casi imposible por construcción. |
| Bandas por planta (baja, alta) | (2,2) en 26; (1,2) en 6 | Las dos plantas tienen bandas, pero cada una elige su eje y su corte por área. |
| Muros interiores de arriba sobre muros de abajo (S2.2e → S2.2f) | 4 % → 9 % | Corregir cortes después (snap de ±2.5 ft) no alcanza. |
| Éxito independiente en S2.1 (lote interior) | planta baja ~10 %, planta alta ~17 % | Exigir que ambas coincidan multiplica las probabilidades: por eso cae la cobertura. |
| Lado corto de la planta alta (283 casas) | mediana 22.8 ft (10.5–38.6) | **197 de 283** pasan de 20 ft y necesitan **1 eje interior**. Ninguna pasa de 40 ft, así que **ninguna necesita más de 2**. |
| Lado corto de la planta baja | mediana 36.7 ft (máx. 43) | Bajo la planta alta, 1 eje casi siempre; 2 solo en 28 casas de más de 40 ft. |
| Planta alta sobre el garage | 234 de 283 | El garage (≈20 ft de luz libre) es una crujía natural: sus muros son ejes. |
| Ubicación de la planta alta | adelante 124, sobre garage 62, compacta 40, compacta en bandas 33, atrás 20, voladizo 4 | En "adelante" y "atrás" el borde de la planta alta (la junta) cruza la planta baja: **es un eje obligatorio** que hoy nadie anticipa abajo. |
| Escalera (centro) | 1/3 del ancho, 0.28 de la profundidad | Está dentro de la franja K12 y sus muros ya son los mismos en las dos plantas. |

### Las causas, en orden de peso

1. **Cada planta se zonifica sola.** El motor de bandas y columnas elige, en cada planta, el eje (x o y) y la
   posición de los cortes según las áreas objetivo. Nada le dice que hay una estructura.
2. **Los cortes salen del área, no de la estructura.** Una banda mide lo que su programa necesita (por ejemplo,
   13.5 ft) y no lo que la vigueta permite (≤ 20 ft) o lo que define un muro de abajo.
3. **La junta de la planta alta.** S1 coloca la planta alta (adelante, atrás, sobre el garage) y su borde cae sobre
   el interior de la planta baja; la zonificación de abajo no lo sabe.
4. **Los cuartos (S2.1) vuelven a cortar por área** dentro de cada zona, así que las paredes interiores terminan en
   cualquier lado.
5. **El área sobrante no tiene a dónde ir.** Si se fijan las crujías, el área que no cabe en los cuartos óptimos
   estira los cuartos (lo que limitamos en S2.2e). No hay una salida explícita, salvo el techo de S2.2d, que solo
   funciona arriba y en franjas de fachada.
6. **La búsqueda es estrecha.** Pocas topologías válidas por planta (2 a 11). Pedir coincidencia después de buscar
   deja muy pocas parejas.

**Conclusión:** el problema no es de tolerancias, es de orden. La estructura tiene que ser **el primer dato** de la
zonificación, no una verificación al final.

## 2. Los tres conceptos propuestos

### Concepto 1 — 1 o 2 ejes internos comunes, con la vigueta como medida máxima

Las crujías son franjas entre ejes. Cada crujía mide **≤ joist_span_max_ft (20 ft)** y **≥ la profundidad mínima
útil** (≈ 10–11 ft, la de un dormitorio).

| Lado corto de la planta alta (S) | Patrón | Ejes interiores |
|---|---|---|
| S ≤ 20 ft | 1 crujía (cuartos + pasillo lateral) | 0 (solo el contorno y el núcleo) |
| 20 < S ≤ ~30 ft | 2 crujías: cuartos (11–16) + pasillo y cuartos | 1 |
| ~30 < S ≤ 40 ft | Columna vertebral: cuartos (11–14) / pasillo (3.5–4) / cuartos (11–14) | 2 (los dos muros del pasillo) |

- Los ejes son paralelos al lado largo de la planta alta; las viguetas cruzan el lado corto.
- En la planta baja, debajo de cada eje va **un muro o una viga sobre el eje**. Una viga sobre el eje (por ejemplo,
  sobre la gran sala abierta) **sigue compartiendo el eje**. Así se respeta la planta abierta sin romper la regla.
- La junta de la planta alta (su borde sobre la planta baja) es un eje más. Junto con el eje interior suman los "1
  o 2 ejes".
- Los muros perpendiculares a los ejes (entre cuartos de una misma crujía) son **tabiques**: no cargan y quedan
  libres.

### Concepto 2 — El área sobrante la absorbe el techo

- **Arriba:** cada crujía se llena con los cuartos en su área óptima (con los topes de S2.2e). Lo que sobra a lo
  largo de la crujía pasa a **techo** (o terraza ≤ 3 ft), en el extremo de fachada, como en S2.2d pero por crujía.
- **Abajo:** la huella la fija S1. Lo que sobra va primero a los cuartos (dentro de sus topes) y después a un
  **porche o patio techado** en la fachada del jardín, o deja una huella más chica (S1 ya admite "no construido").
- **Resultado:** los muros quedan donde manda la estructura y la diferencia de área se ve como volumen (techos en
  varios niveles), no como cuartos estirados.

### Concepto 3 — El núcleo de la escalera es estructura propia y ancla un eje

- Las cuatro paredes de la caja de escalera son continuas en las dos plantas: es un **núcleo rígido** que también
  sirve como línea de arriostramiento (R602.10).
- **Su muro largo prolongado es el eje vertebral.** Arriba es el muro del pasillo (llegada compacta, un solo
  pasillo, puertas agrupadas a lo largo de él); abajo es el muro del foyer o del hall.
- Esto resuelve a la vez la llegada (el pasillo nace en el descanso), las puertas (todas sobre el eje) y la
  estructura (el eje está apoyado en el núcleo).
- **Restricción:** el eje vertebral debe caer dentro de la franja K12 (25–75 % de la profundidad). La escalera ya
  cumple (0.28 de mediana).

## 3. Modelo propuesto: "marco estructural primero"

```
S1 (huellas, escalera)
   └─► S1.3 MARCO: dirección de viguetas (lado corto de la planta alta)
                   ejes candidatos = contorno + muro largo del núcleo + junta + muros del garage
                   + ejes libres solo si una crujía pasa de 20 ft
                   elegir 0–2 ejes interiores: crujías entre 10–11 y 20 ft
   └─► S2 por crujías: las bandas SON las crujías (posición fija), las columnas se cortan por área dentro de
                   cada banda, el mismo eje en las dos plantas; la planta baja fuera de la huella alta queda libre
   └─► S2.1: cuartos en su área óptima dentro de cada crujía; el sobrante se vuelve techo o porche;
                   los tabiques perpendiculares son libres
   └─► verificación: cada eje con muro o viga abajo (obligatoria), luces ≤ 20 ft, vigas ≤ 20 ft entre apoyos
```

**Ventaja clave:** el motor de bandas y columnas ya existe (`core_zoning`). Cambia **quién fija los cortes de
banda**: hoy el área; mañana el marco. Las columnas siguen siendo por área. Por eso el cambio es acotado y la
alineación queda **garantizada por construcción**, no buscada.

### Riesgos

- **Cobertura:** las bandas fijas pueden no admitir algunos programas (por ejemplo, una suite de 16 ft en una
  crujía de 12 ft). Mitigación: el marco propone 2–3 variantes de ejes (posiciones de la junta y del eje vertebral)
  y S2 prueba cada una.
- **Planta baja libre fuera de la huella alta:** si la zonificación baja no se guía en esa parte, puede dar formas
  pobres. Mitigación: allí puntuar por forma, como hoy.
- **Programas chicos (S ≤ 20 ft):** sin eje interior. Solo cuentan el núcleo y la junta.

## 4. Plan de acción propuesto (S2.2g, un paso)

| # | Trabajo | Módulos |
|---|---|---|
| 1 | Datos: `structure.*` amplía con profundidad mínima de crujía, patrones (1 crujía / 2 crujías / columna vertebral), prioridad del eje del núcleo, porche/techo como destino del sobrante | design_structure |
| 2 | Marco: `lib/structural_frame.py` + `lib_aux` (ejes candidatos, elección de 0–2 ejes, variantes) | stacking |
| 3 | S2 por crujías: `core_zoning` acepta bandas fijas (las crujías) en ambas plantas y la misma dirección | core_zoning, zone_cell |
| 4 | S2.1: llenado óptimo por crujía y sobrante a techo o porche; el pasillo sobre el eje vertebral | unit_layout, unit_frame |
| 5 | Verificación con los ejes declarados (muro o viga sobre el eje = compartido); `support_min_fraction` en 1.0 sobre los ejes | floor_structure |
| 6 | KPIs: ejes compartidos (100 % esperado), crujías, área a techo o porche, cobertura | space_quality |
| 7 | Piloto contra S2.2f, pruebas y documentos | tests, docs |

## 5. Innovación (pasos futuros)

- **Tipologías estructurales como "gramática":** catálogo de marcos (crujía simple, doble, columna vertebral,
  núcleo central). Un LLM elige o explica cuál usa cada casa y por qué.
- **Prefabricado:** crujías en módulos de 2 ft, paneles de muro y viguetas estándar, con cómputo de desperdicio.
- **Techos en varios planos** generados desde las crujías que quedan en techo (conecta con S2.2d).
- **Paquete para el ingeniero:** ejes, crujías, vigas y postes exportados para una verificación rápida.
