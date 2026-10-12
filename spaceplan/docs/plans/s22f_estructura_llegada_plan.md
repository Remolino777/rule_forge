# S2.2f — Estructura de la planta alta, llegada de la escalera y puertas agrupadas (análisis y plan)

*12 oct 2026 · rama `stacking/6.7a-s2.2` · análisis previo, sin código*

## 1. Diagnóstico (32 casas del piloto S2.2e)

| Tema | Medida | Valor |
|---|---|---|
| Estructura | Muros interiores de la planta alta que caen sobre un muro de la planta baja | **mediana 4 %** (mín. 0 %, máx. 22 %) |
| Estructura | Lado corto del ambiente más grande de la planta baja (luz libre del entrepiso) | mediana 16 ft, máx. 20 ft; 13 de 32 casas > 16 ft |
| Llegada | Espacio que recibe la escalera | siempre un `hall` (32/32) |
| Llegada | Proporción del hall de llegada | 14 de 32 entre 1.0 y 1.5 (caja-vestíbulo); 2 casas en 15:1 (tira larga) |
| Llegada | Pasillos por planta alta | 18 de 32 tienen **dos** halls (el de la unidad de circulación + el pasillo de la zona privada) |
| Llegada | Área de hall + foyer arriba | mediana 143 ft² (máx. 223) |
| Puertas | Puertas de dormitorio que abren a otro hall, no al de llegada | 20 de 49 |
| Puertas | Separación máxima entre puertas de dormitorios | mediana 9 ft, máx. 20 ft |
| Puertas | Distancia de la llegada a la puerta de dormitorio más lejana | mediana 14.7 ft, máx. 21 ft |

### Causas en el código

1. **Plantas independientes.** S2 zonifica las dos plantas por separado. `zone_cell._combine` elige el par
   planta baja × planta alta por puntaje y por relaciones verticales en el grafo, sin geometría de muros. En S2.1,
   `space_cell` también resuelve cada planta por su cuenta.
2. **Retículas distintas.** Cada planta se rasteriza con su propio origen (`rasterize(polygon)`). Aunque dos cortes
   quisieran coincidir, pueden quedar corridos medio pie.
3. **Cortes sin ejes.** La guillotina de `unit_layout` corta en la posición que da las áreas objetivo. No conoce
   ningún eje preferido.
4. **Llegada sin reglas propias.** K01 solo elige el tipo de espacio (hall, vestíbulo o sala familiar), sin tamaño,
   forma ni continuidad. El pasillo de la zona privada (`corridor_allowance`) se dibuja como otro hall que no
   necesariamente continúa el de llegada.
5. **Esquina de la puerta.** `DoorPlacer.door` prueba primero la esquina `toward_plus`, una dirección del eje de la
   retícula que no depende de la escalera. Así se dispersan las puertas y se alarga el pasillo. Solo los baños
   compartidos tienen la regla de ≤ 6 ft (S2.2c).

## 2. Criterio estructural propuesto

Sistema supuesto: **entramado ligero de madera con plataforma** (lo habitual en San Diego, CRC). Tres clases de
muro:

| Clase | Definición | Regla |
|---|---|---|
| **Perimetral** | Muros exteriores de la planta alta | Sobre un muro exterior de la planta baja, o en voladizo dentro del límite (hard) |
| **Eje estructural** | Línea recta compartida por ambas plantas (x = c o y = c en la retícula común) que lleva el entrepiso y el arriostramiento | Los muros de la planta alta en un eje caen sobre un muro o una viga de la planta baja (hard para los ejes elegidos) |
| **Tabique** | Muro interior de la planta alta fuera de los ejes | Permitido sobre el entrepiso (no portante); su longitud se mide y se penaliza (soft) |

### Capas

| Capa | Regla | Origen | Kind |
|---|---|---|---|
| Normativa (CRC 2025, `verified: false`) | Líneas de muros arriostrados: un muro exterior se desvía ≤ 4 ft de su línea; un panel empieza ≤ 10 ft del extremo de la línea; ≤ 20 ft entre paneles | R602.10.1.2, R602.10.2.2 | code |
| Normativa | SDC D (San Diego): paneles arriostrados que no están en el mismo plano vertical entre pisos → edificio **irregular** → diseño de ingeniería (excepción: voladizo ≤ 4 × peralte de la vigueta) | R301.2.2.6 | code |
| Normativa | Abertura en el entrepiso (escalera) ≤ 50 % de la distancia entre líneas de arriostramiento y ≤ 25 % del área entre ellas | R301.2.2.6 | code |
| Diseño | Luz máxima de vigueta (sin viga) 16 ft; con viga, luz máxima de viga 20 ft | Tablas de luces (2×10/2×12, I-joist), práctica | soft, designer |
| Diseño | Alineación mínima: ≥ 50 % de la longitud de muros interiores de la planta alta sobre un eje | Criterio propuesto | soft → hard tras calibrar |
| Diseño | Apilar muros húmedos: baños de la planta alta sobre baño, cocina o lavandería de abajo | Práctica (plomería) | weight |

**Inconsistencia a decidir:** hoy `upper.cantilever_depth_ft` = 6 ft. Para un muro exterior portante, la excepción
de R301.2.2.6 da unos 3 ft con viguetas 2×10 (4 × 9¼ in). Un voladizo de 6 ft exige ingeniería o debe bajar.

### Modelo de ejes

1. **Retícula común:** las dos plantas sobre el mismo origen del lote (paso de 0.5 ft).
2. **Ejes candidatos:** se derivan de la planta baja (S1 y S2):
   - el perímetro;
   - los muros del núcleo de escalera (los mismos en ambos pisos);
   - las fronteras de las zonas S2 de la planta baja;
   - una línea intermedia cuando la profundidad supera la luz máxima.
3. **Selección:** se elige el conjunto mínimo de ejes paralelos a cada fachada tal que ninguna luz supere la máxima.
   Un tramo sin muro abajo, como la gran sala, recibe una **viga**, que se cuenta y se penaliza.
4. **Planta alta:**
   - S2 premia que las fronteras de zona caigan sobre ejes;
   - en S2.1, cada corte de guillotina prueba primero la posición del eje más cercano, si el área queda dentro de la
     tolerancia (*snapping*), y el puntaje suma el término `structure`.
5. **Orden:** la planta baja se resuelve primero (top-2 opciones) y la planta alta se busca con sus ejes.

## 3. Llegada de la escalera

| Criterio | Propuesta | Kind |
|---|---|---|
| Descanso superior | ≥ ancho de la escalera × 36 in, libre de giros (R311.7.6, ya existe) | code |
| Nodo de distribución | El hall de llegada es compacto: área ≤ descanso + ancho de hall × (número de puertas que sirve) × factor; sin "caja-vestíbulo" vacía | soft |
| Un solo pasillo | El pasillo de la zona privada continúa el hall de llegada: mismo eje y mismo ancho; recto, en L o en T; nunca dos halls desconectados | hard (S2.1) |
| Sala familiar arriba | Puede abrirse a la llegada como *loft*, pero no puede ser el paso a los dormitorios | hard |
| Recorridos | Llegada → puerta de cada dormitorio ≤ 15 ft (mediana actual 14.7, máximo 21) | soft |
| Fondo de saco | El pasillo termina en la última puerta; lo que sobra va a clóset o blancos | soft |
| Luz | El descanso sigue con K06 (ventana) | existente |

## 4. Puertas de dormitorios agrupadas

1. **Esquina más cercana:** de las dos esquinas que soportan la hoja abierta, se elige la que queda más cerca de la
   llegada (distancia por el pasillo, no en línea recta).
2. **Agrupamiento:**
   - se aplica a las puertas de dormitorios que dan al mismo pasillo; métrica = longitud del tramo de pasillo que
     contiene todas las puertas;
   - objetivo: ≤ 12 ft, o pares de puertas en muros enfrentados ("en espejo");
   - se extiende la regla de S2.2c de baños compartidos.
3. **En la distribución (S2.1):** el término `circulation` del puntaje suma la distancia llegada → puertas. Así la
   guillotina prefiere ordenar los dormitorios alrededor del nodo y no en fila a lo largo de un pasillo largo.
4. **Interferencias:** se reutiliza el detector exacto de S2.2e (R1–R3): dos puertas juntas no pueden cruzar sus
   giros.

## 5. Plan de implementación (un solo paso, S2.2f)

| # | Trabajo | Módulos |
|---|---|---|
| 1 | **Datos:** nuevo `design_structure.json` (luces, alineación, voladizo, muros húmedos, pesos, capa CRC con R602.10 y R301.2.2.6); K13-STAIR-ARRIVAL en `client_stair_rules`; `door.grouping.*`; registro y herramientas LLM (`get_criteria` grupos `structure` y `arrival`) | data/rules, design |
| 2 | **Geometría:** `lib_aux/structure_grid.py` (retícula común, líneas de muro, ejes, luces, vigas, voladizos, alineación) | stacking/lib_aux |
| 3 | **S2:** término de alineación de fronteras de zona en `_combine` y retícula común en `rasterize` | zone_cell, floor_frame, zone_grid |
| 4 | **S2.1, estructura:** planta baja primero → ejes → planta alta con *snapping* de cortes y término `structure` | space_cell, unit_layout |
| 5 | **S2.1, llegada:** pasillo único y continuo, nodo compacto, sala familiar no como paso, fondo de saco recortado | unit_layout, unit_frame, space_relations |
| 6 | **S2.1, puertas:** esquina hacia la llegada, agrupamiento, recorridos | door_placement |
| 7 | **Calidad:** alineación %, luz máx., vigas, voladizo, irregularidades CRC, área y forma de la llegada, número de halls, separación de puertas, recorridos | space_quality, run_quality |
| 8 | **Piloto, pruebas, HANDOFF y documentos** contra `s22e_pilot/after` | tests, docs |

Riesgos:
- **Cobertura:** más restricciones arriba. Se mitiga con lo estructural interior en soft al inicio y medido; se
  endurece tras calibrar.
- **Tiempo de cálculo:** la planta alta se busca por cada una de las 2 mejores plantas bajas, unas 2 veces más arriba.
- **Golden:** la retícula común cambia las salidas S2 y S2.1, y hay que refrescar los fixtures de stacking.

## 6. Innovación (pasos futuros)

- **Agente estructural:**
  - propone vigas y ejes y explica cada irregularidad CRC en lenguaje llano;
  - entrega un paquete para el ingeniero: ejes, luces y cargas tributarias.
- **Modularidad:** ejes en módulos de 2 ft para paneles prefabricados (*panelized framing*), con medición de
  desperdicio.
- **Carbono incorporado y costo:** estimación por vigas y por metro de muro portante (conecta con el índice de costo
  6.5b).
- **Cargas verticales:** verificación simple de cargas por tributaria y elección de sección de vigueta o viga (tabla).
