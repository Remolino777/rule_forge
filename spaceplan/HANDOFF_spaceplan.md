# HANDOFF — `spaceplan`, paso 6.6: análisis de áreas por lote (programa × esquema vertical × estrategia, IC e IO)

> **Qué vamos a agregar.** El programa de necesidades deja de ser un dato fijo del brief. El sistema recibirá **quién
> vive** (arquetipo de hogar con su trayectoria), **cómo vive** (perfil cultural: latino o anglosajón, con distinta
> importancia de la cocina) y **cuánto puede invertir** (presupuesto relativo, sin valores reales). Con eso generará tres
> programas (**mínimo, óptimo y máximo construible**, más los perfiles **por etapas** y **accesible**) que competirán en un
> **portafolio de opciones** (programa × número de pisos × estrategia de huella), en lugar de forzar soluciones de un
> solo piso dentro de un paso.

Módulo `spaceplan` de Municipal Permit Intelligence.

Fecha: 8 de octubre de 2026 · Estado: pasos 1–6, 6.5a–6.5d y **6.6** completos (6.6: 10 lotes del piloto, esquemas verticales V0–V5, índices IC/IO como familia de reglas de razón, evaluación E0/E1/E2, mapas de decisión) · Paquete `spaceplan` v0.1.0 · brief 0.5 · paquete 0.9 · reglas SDMC 0.4.0 · catálogo residencial 0.11.0 · catálogo de hogar 0.3.0 · 620 pruebas
Capstone MS-AAI, University of San Diego (18 meses desde sept. 2026; cierre feb. 2028). Preparado con asistencia de
Claude (Anthropic); declararlo en el informe según la política de IA de USD.

---

## 1. Reglas de trabajo del usuario (obligatorias en el nuevo chat)

1. Responder en **español**; el **código siempre en inglés**.
2. **Primero análisis lógico y plan de acción en pasos**; **preguntar siempre antes de empezar a programar**.
3. Incluir siempre una sección de **posibilidades de innovación**.
4. Estructura de código: `main/` (workflow), `lib/` (funciones de dominio), `lib_aux/` (sub-librería sin conocimiento
   de dominio). `lib_aux` no importa `lib`/`main`; `lib` no importa `main` (lo verifica `tests/test_architecture.py`).
5. Ningún número normativo en el código: los valores viven en `data/rules/*.json` (DSL) y los parámetros de diseño
   en `data/catalog/residential_catalog.json`, cada uno con su fuente y estado (`verified`/`provisional`).
6. F3 (RuleForge, 110 h) no se recorta bajo ninguna circunstancia.
7. **Costos sin valores reales.** El costo es un índice relativo sin unidades (1 = construir el 100 % del área máxima
   normativa del lote). Ningún precio en el código ni en el catálogo; la conexión a un módulo de costos real futuro se
   hace por una interfaz intercambiable que lee la ficha de cantidades de cada opción.
8. **El perfil cultural lo elige el cliente** y es editable; nunca se infiere de nombre, origen o idioma.
9. **No forzar soluciones dentro de un paso:** evaluar opciones que crucen pasos (p. ej. dos pisos con la zona privada
   arriba) antes de torcer la planta de un piso con correcciones.

Documentos del proyecto: Plan Light v3.0, Zona piloto Clairemont–Navajo RS-1-7 v1.0,
planogen v2, spaceplan v1.1 (diseño conceptual del módulo).

## 2. Cómo correr

```bash
unzip spaceplan_steps_1_6_5d.zip && cd spaceplan
pip install -e ".[dev]"            # shapely, numpy, jsonschema, networkx, matplotlib, pytest
pytest -q                           # 561 pruebas, ~9 min, ~5 min (correr en tandas si el entorno corta a 300 s)
spaceplan household --list                                    # 7 arquetipos
spaceplan household multigenerational                         # programas R/P/D ahora y en 5 años, delta
spaceplan household mi_hogar.json --tier preferred --no-next  # hogar propio (ver data/schemas/household.schema.json)
spaceplan capacity spaceplan/data/briefs/interior_50x100_multigen.json   # brief solo con hogar (programa derivado)
spaceplan capacity spaceplan/data/briefs/interior_50x100.json --budget medium --cost-model shape   # índice, presupuesto, tornado
spaceplan household multigenerational --culture latino --no-next                              # capa cultural
spaceplan capacity spaceplan/data/briefs/interior_50x100_multigen_anglo.json                  # cultura en el lote
spaceplan profiles spaceplan/data/briefs/interior_50x100_multigen_latino.json --budget medium --zone --sheets out/   # portafolio + láminas
spaceplan profiles empty_nest --culture anglo                                                  # portafolio sin lote
spaceplan capacity spaceplan/data/briefs/interior_50x100.json -o pkg.json --plot cap.png --site-plot site.png --zoning-plot zoning.png
spaceplan capacity spaceplan/data/briefs/apt_2br_interior.json --zoning-plot apt.png
spaceplan capacity spaceplan/data/briefs/fan_cul_de_sac_35_80x100.json --zoning-plot fan.png      # B + corrección
spaceplan capacity spaceplan/data/briefs/fan_reverse_80_40x100.json --strategy B_polygonal_footprint --no-corrections
spaceplan program t3_standard --garage 2 --profile balanced
spaceplan catalog --markdown docs/parameter_table.md
spaceplan areas --zone-top 2 --sheets out/figures --tables out          # 6.6: 10 lotes x 21 hogares (~2.5 min)
spaceplan areas fan_cul_de_sac_35_80x100 --households empty_nest.anglo,teens_family.latino --scheme V5
```

## 3. Arquitectura y flujo

```
House:     brief -> validate -> program review -> scope -> lot -> boundaries -> rule variants -> envelope
           -> capacity (layer 0) -> site partition (layer 1) -> zoning, zones + spaces (layer 1c / 2) -> backyard (1d)
           -> package (schema 0.6) -> validate
Apartment: brief -> validate -> program review -> unit -> zoning (apartment profile) -> package
```

| Archivo | Responsabilidad |
|---|---|
| `main/run_capacity.py` | Orquesta todo; `run_capacity()` despacha casa/apartamento (`run_apartment`). |
| `main/run_program.py`, `main/cli.py` | Expansión de tipologías, tabla de parámetros, CLI (`validate`, `capacity`, `program`, `catalog`). |
| `lib/rules.py`, `lib/rule_variants.py` | Acceso al DSL y tabla de decisión de variantes (retiros, FAR, altura, pavimento, proyecciones...). |
| `lib/lot.py`, `boundaries.py`, `lot_metrics.py`, `capacity.py` | Capa 0: lote, linderos, métricas, envolvente, FAR, factibilidad en 3 niveles. |
| `lib/site_partition.py`, `orientation.py` | Capa 1: huella por número de pisos, acceso (deck, sendero, acceso vehicular), pavimento, orientación y afinidad zona–fachada. Expone todas las posiciones de deck que cumplen (`access_options`). |
| `lib/catalog.py`, `program_builder.py`, `program_review.py`, `catalog_table.py` | Catálogo, tipologías, revisión de programa vs CRC, tabla de parámetros. |
| `lib/realization.py` | Interfaz intercambiable `RealizationStrategy`; `StrategyA`: rectángulo inscrito, 2 bandas de columnas apiladas, columna pasante opcional, spine opcional. |
| `lib/zoning.py` | Nivel de zonas: perfiles por tipo de vivienda, anclas, secuencia de entrada, particiones por espacios, fusiones, enumeración exhaustiva con poda, condiciones necesarias de la matriz; drivers `zone_site_options` (casa) y `zone_unit` (apartamento) que llaman al nivel de espacios. |
| `lib/space_layout.py` | Nivel de espacios: subdivisión de cada celda (guillotina con lados mínimos), pasillo tallado opcional, evaluación global, ranking. |
| `lib/circulation.py` | Grafo de puertas, reglas de puertas, accesibilidad, evaluación D/I, franjas de circulación. |
| `lib/relation_matrix.py` | Matriz D/I/N por tipo de vivienda + overrides del brief + grupos duros. |
| `lib/unit.py` | Unidad de apartamento (polígono, roles de borde, entrada). |
| `lib/backyard.py` | Programa del patio con filtro de prioridad, reserva verde y separaciones. |
| `lib/package.py`, `schema_validation.py`, `visualize.py` | Ensamblado del paquete, validación, diagramas (6.6: mapa de decisión, presupuesto de áreas, IC–IO, mejor esquema). |
| `lib/building_indices.py` | (6.6) IC e IO como familia de reglas de razón del DSL (`Z15`), variantes de garaje. |
| `lib/vertical_split.py` | (6.6) Esquemas verticales V0–V5: grupos, reparto por piso, reglas duras, métricas y pesos del hogar. |
| `lib/area_budget.py`, `lib/area_matrix.py` | (6.6) Límites del lote, E0/E1 por estrategia, celdas, ranking, Pareto. |
| `lib/flag_lot.py` | (6.6) Lote bandera, lectura provisional (cuerpo como lote, acceso como pavimento). |
| `main/run_area_matrix.py` | (6.6) Workflow del piloto, E2, tablas y figuras; `main/run_capacity.prepare_lot` y `main/run_profiles.profile_programs` extraídos para reutilizarlos. |

Datos: `data/schemas/` (brief 0.2, package 0.6, catalog), `data/rules/sdmc_rs_1_7_capacity.json` (v0.3.0, Z00–Z14),
`data/rules/crc_2025_habitability.json` (v0.2.0, C01, C03, C06), `data/catalog/residential_catalog.json` (v0.5.0),
`data/briefs/` (4 casas, 2 apartamentos).

## 4. Decisiones de diseño acumuladas

**Pasos 1–4 (resumen).** Brief y paquete separados, hashes SHA-256, `Quantity` con estado, ningún número normativo en el
código, ancho/profundidad de lotes irregulares por métodos parametrizados con sensibilidad, capacidad normativa vs
realizable (falso infactible), patio y frente por diferencia de polígonos, orientación por vector norte con pesos por
latitud, corrección mínima de pavimento.

**Paso 5, revisión 1.** Tipo de vivienda (casa/apartamento); roles de fachada; perfiles de zonificación en el catálogo
(casa: sala a la calle principal dura, cocina atrás blanda; apartamento: vestíbulo en la entrada, cocina por el
vestíbulo y nunca sobre la puerta, sala y dormitorios con fachada exterior); overrides `hard|soft|off` desde el
brief; programa del patio con filtro de prioridad (reserva verde 30 %, áreas mín/obj/máx, un elemento de agua, asador
requiere deck, separaciones del DSL).

**Paso 5, revisión 2 (esta sesión).**
- *Matriz D/I/N del usuario* en el catálogo. "Acceso" = puerta de entrada (`@entry`); el vestíbulo es circulación.
  "Baño" se separó en baño social (`social_bath`, `half_bath`) y baño privado (`primary_bath`, `bathroom`).
  Apartamento = misma matriz sin patio + Acceso–Cocina = I. D duras solo en el núcleo funcional; "comedor/cocina–patio"
  es un **grupo duro** (al menos uno) y ambos pares son blandos con peso 1.5.
- *Semántica D*: puerta/apertura compartida; si interviene un espacio terminal o la entrada, también vale abrir al
  mismo vestíbulo/pasillo/spine; **dos espacios abiertos (sala, comedor, cocina) deben tocarse**. I: sin puerta
  directa y alcanzable por exactamente un espacio intermedio. La matriz se lee por filas (cada A necesita algún B).
- *Circulación como red*: los `hall` del programa se eliminan (`derived_space_types`); la circulación se produce:
  pasillo tallado en una celda con ≥2 terminales, spine opcional entre bandas (su área se descuenta de todas las
  zonas) y franjas de puerta a puerta en los espacios atravesados (se descuentan del área neta). Ancho de diseño
  3.5 ft; mínimo normativo C06 = 3 ft (provisional).
- *Reglas de puertas*: terminal–terminal solo si hay un par D entre sus tipos (en suite, dirigido dormitorio→baño);
  los terminales privados (dormitorios, baños privados, vestidor) solo abren a circulación o en suite; garaje solo a
  circulación o a las zonas de su grupo del brief; puertas al patio desde espacios no húmedos con fachada trasera.
- *Estrategia A ampliada*: columna pasante (≤3 zonas, izquierda o derecha), spine, partición "núcleo húmedo" (solo
  apartamentos), fusión de servicio pequeño en cocina o garaje (mudroom), todas las posiciones de deck que cumplen.
- *Rendimiento*: precheck barato de intervalos en el frente, salida en la primera violación, caché de roles; nivel de
  espacios con topes (`zone_schemes` 60, `max_combinations_per_scheme` 300). Casa: 2–6 s; apartamento: <1 s.


## 4b. Paso 6 (esta sesión): abanicos e irregulares

**Análisis.** En un abanico hay dos recursos distintos: área (concentrada atrás) y frente sobre la calle (escaso
adelante). La estrategia A pierde el fondo (65 % de la envolvente en el cul-de-sac) y el corte proporcional no da al
garaje el ancho del acceso vehicular aunque la suma de mínimos quepa.

**Implementación.**
- `lib_aux/section.py` (`SectionProfile`): integrales exactas sobre fronteras lineales a trozos, cortes por área
  (bisección con caché), intervalo útil por franja, mejores k escalones, ancho a profundidad dada.
- `lib/realization.py`: `FootprintDomain`; `StrategyB("rectangle")` (escalones, hombros `front_shoulder` /
  `rear_shoulder`, cuñas como reserva poligonal) y `StrategyB("polygonal")` (celdas de borde trapezoidales con núcleo
  rectangular). Ajuste de anchos de columna con intercambio de área en la banda (`zoning.max_area_shift` = 0.15;
  reportado como `realization.area_shift`), también en el modo poligonal (`polygonal_cuts`).
- Junta entre escalones (`carve_joint`): corredor del ancho de diseño desde la columna de circulación hacia un extremo,
  tallado en las columnas posteriores completas; alternativa al spine completo, que separa comedor y cocina.
- `lib/polygonal.py`: extensión poligonal consciente del CRC (catálogo `polygonal_extension`): astillas < 2 ft a
  residuo; tipos tolerantes absorben; dormitorios/baños solo si crecen ≤ 25 % y sin esquinas < 60°; registro completo.
- Anclaje "sala a la calle" con alternativa `street_view` (hombro) a costo 0.5 en el puntaje blando.
- Garaje en tándem (`garage_2car_tandem`, 1 carril, 40 ft de fondo) y carriles en el sitio.
- Estrategia `auto` (catálogo `realization`): A si su rectángulo usa ≥ 80 % de la envolvente; si no, B escalonado.
  Capacidad realizable reportada para B2, B3 y poligonal.
- Corrección mínima multivariable: `lib/corrections.py` (combinaciones por costo, retrocesos mínimos por frente
  estricto/relajado y por profundidad del deck, poda por frente) + `main/run_corrections.py` (búsqueda con tope,
  frontera de Pareto costo vs puntaje). Bloque `corrections` del paquete.
- Nivel de espacios: enumeración best-first por suma de rangos (`lib_aux/allocation.ranked_product`).

**Resultados.**
| Brief | Resultado |
|---|---|
| fan_cul_de_sac | Base B no factible (deck en el antejardín, pavimento 69 %); corrección mínima: B escalonado + retroceso 5 ft (costo 0.65), garaje doble conservado; sala en el hombro (9.1 ft) |
| fan_reverse_80_40x100 (nuevo) | Zonifica directo con B en ~5 s; hombros posteriores hacia el jardín |
| trapezoid_asym_45_65x100 (nuevo) | A seleccionado (85 %); sin esquema; corrección: garaje de 1 auto (B da zonas válidas pero falla el nivel de espacios) |
| fan_curve | 3,000 sq ft exceden en 1 sq ft lo que caben 2 escalones; sin corrección (pide 3 bandas) |
| interior / corner / apartamentos | Sin cambios (A) |

**Limitaciones nuevas.**
1. El modo poligonal rara vez pasa el nivel de espacios: los núcleos rectangulares son conservadores (`cell_dimensions`)
   y la accesibilidad falla en topologías de una sola banda.
2. Las condiciones de zona siguen siendo necesarias pero laxas: aparecen zonificaciones válidas sin distribución de
   espacios accesible (trapecio, abanico inverso poligonal).
3. B usa 2 bandas (2 escalones); el tercer escalón queda como expansión.
4. El intercambio de área anticipa el paso 9 de forma acotada; no es todavía la asignación QP.
5. La corrección se detiene en el presupuesto (`max_evaluations` 8 + `pareto_extra_runs` 2).

## 4c. Reenfoque (después del paso 6): portafolio de opciones y paso 6.5

### Por qué
La corrección mínima del paso 6 "resolvió" `fan_cul_de_sac` en un piso (B escalonado + retroceso 5 ft), pero con una
planta que un arquitecto no propondría: dormitorios hacia la calle, sala en un hombro de 9 ft y área quitada a la zona
privada para ensanchar el garaje. Causas: sesgo de un piso (n2 diferido nunca compitió), criterio de "primera solución
que cumple", parches que esconden el conflicto (intercambio de área, anclaje alternativo, retroceso) y un perfil que no
depende del tipo de lote ("sala a la calle" contradice la geometría del abanico, cuyo lado ancho y privado es el fondo).

### Lectura de áreas del cul-de-sac (aproximada)
Lote 5,750 sq ft; FAR 0.59 → 3,392 sq ft; programa ≈ 2,212 sq ft → holgura de FAR ≈ 1,180 sq ft. Envolvente: 31 ft al
frente, ≈ 45 ft a 40 ft de profundidad, 66 ft al fondo. Opción preferida: **dos pisos con gradiente vertical**. Planta
baja ≈ 1,400–1,500 sq ft (garaje + vestíbulo/escalera al frente angosto; zona social ampliada, cocina y servicio en el
escalón ancho hacia el jardín). Planta alta ≈ 950–1,050 sq ft (zona privada). La planta alta cabe dentro de la baja; el
jardín sube ≈ 30 %. La **junta entre escalones** del paso 6 pasa a ser el **núcleo de escalera**. El pavimento (69 %)
se resuelve mejor con **retroceso por columna** (garaje adelante, entrada retrasada ≈ 5 ft), no con retroceso global.

### Principios
1. **Portafolio de opciones:** programa (mínimo/óptimo/máximo/etapas/accesible) × pisos × estrategia × variantes de
   fachada, evaluadas con un mismo criterio; la corrección mínima pasa a ser un caso particular.
2. **Evaluación escalonada:** presupuesto de áreas por piso (barato) → factibilidad gruesa de apilamiento → zonificación y
   espacios completos solo para las opciones prometedoras.
3. **Perfiles por tipo de lote** (rectangular, esquinero, abanico directo, abanico inverso, bandera); en abanicos, "sala al
   jardín, entrada visible desde la calle".
4. **Holgura de FAR como variable de diseño** visible al cliente.
5. **Puntaje de calidad común:** zona social (tamaño, orientación), relación con el jardín, privacidad (profundidad y
   separación vertical), jardín, circulación con escalera y penalización por solución forzada.

### Perfiles de programa
- **Mínimo construible:** lo indispensable para ese hogar (mínimos del CRC + necesidades del arquetipo). El más barato.
- **Máximo construible:** el menor entre el techo normativo (capa 0) y el techo presupuestario; se reporta cuál manda.
- **Óptimo construible:** el codo de la curva costo–calidad para ese hogar, evaluado también contra su etapa siguiente.
- **Por etapas (crece contigo):** el mínimo de hoy preparado para llegar al óptimo (estructura, escalera en la junta,
  zonas de expansión); dos estados compatibles, ambos verificados contra la norma.
- **Accesible / envejecer en casa:** dormitorio y baño completos en planta baja, entrada sin escalones, pasos amplios.
- **Lentes de prioridad** (no perfiles): máximo jardín, eficiencia (forma compacta, orientación), reventa.
- **Fuera del piloto:** ADU/JADU (solo bandera de potencial).

### Índice de costo relativo (sin valores reales)
- **Base:** índice = área bruta de la opción / área máxima normativa del lote (el máximo vale 1).
- **Ponderado (opcional):** coeficientes relativos sin unidades por tipo de área (húmeda > 1, garaje y exteriores < 1),
  en el catálogo con fuente y estado provisional.
- **Forma (opcional):** multiplicadores relativos por segundo piso, huella escalonada o poligonal y ladera.
- **Presupuesto relativo:** nivel (ajustado / medio / holgado) o fracción del máximo. Si queda por debajo del índice del
  mínimo → sugerir construcción por etapas.
- **Dos lecturas:** relativo al lote (decidir en un lote) y relativo a una vivienda de referencia (comparar lotes).
- **Conexión futura:** el portafolio pide el costo a un **modelo de costo intercambiable** (mismo patrón que las
  estrategias de realización). Cada opción entrega una **ficha de cantidades** completa: área por tipo y por piso, huella,
  cubierta, perímetro de fachada, escaleras, núcleos húmedos, complejidad de huella y pendiente. Un módulo real futuro
  solo lee esa ficha.

### Arquetipos de hogar
Un arquetipo es una **combinación de dimensiones**, no una etiqueta fija:

| Dimensión | Valores | Efecto en la casa |
|---|---|---|
| Composición | adultos, menores por tramo (0–5, 6–12, 13–18), adultos mayores | dormitorios, baños, supervisión, separación |
| Etapa de vida | pareja joven, crianza temprana, adolescentes, nido vacío, retiro | prioridades, pisos tolerados, crecimiento |
| Trabajo en casa | nadie / una / dos personas | estudios aislados cerca de la entrada |
| Movilidad | plena / reducida / prevista | suite en planta baja, accesibilidad |
| Vida social | íntima / frecuente / grandes reuniones | comedor, sala o sala familiar, terraza cubierta |
| Huéspedes | raros / frecuentes / residentes temporales | cuarto de huéspedes o estudio convertible |
| Cocina | ligera / diaria / intensiva | tipología de cocina (ver capa cultural) |
| Vehículos y mascotas | autos, mascotas | garaje, cuarto de lodo, patio |
| Trayectoria | estable / hijos previstos / llega un familiar mayor | perfil por etapas, reservas |

**Arquetipos de referencia:** pareja joven; crianza temprana; familia con adolescentes; multigeneracional; nido vacío /
retiro; trabajo remoto; adultos que comparten. **Trayectoria:** el óptimo se evalúa contra la etapa actual y la siguiente
(la casa debe servir 15–20 años); la casa por etapas es la que cubre la trayectoria al menor índice de costo inicial.
Cada dimensión activa reglas del catálogo: programa, ajustes a la matriz D/I/N, anclajes y pesos de calidad.

### Capa cultural: latina y anglosajona
Preferencias elegidas por el cliente y editables; las etiquetas son puntos de partida documentados, con perfil mixto o
personalizado siempre disponible; hay gran diversidad dentro de cada grupo.

| Aspecto | Perfil latino (tendencia) | Perfil anglosajón suburbano (tendencia) |
|---|---|---|
| Uso de la cocina | diario e intensivo, varias personas cocinando | más ligero; cocina como estar y exhibición |
| Relación con la sala | semiabierta o separable (olores, humo) | abierta, gran espacio común |
| Centro social | comedor y mesa familiar | isla de la cocina |
| Ventilación | prioritaria | normal |
| Área y despensa | mayor área de trabajo, despensa amplia | despensa tipo walk-in, área estándar |
| Cocina secundaria | asador / cocina exterior para reuniones | amenidad de patio |
| Conexiones | cocina–lavado–patio de servicio; cocina–patio | garaje–cuarto de lodo–cocina; lavandería junto a dormitorios |
| Comedor | capacidad para familia extendida | pierde peso frente al rincón de desayuno |
| Sala | sala de recibir + zona familiar; terraza cubierta | gran espacio integrado; sala de medios en casas grandes |
| Dormitorios y baños | tolera baños compartidos; cuarto para abuelos | suite con baño y vestidor; tendencia a baño por dormitorio |
| Patio | reunión: asador, sombra, mesa grande | césped, juego, piscina |

**Traducción al sistema** (sin código nuevo de dominio): catálogo de **tipologías de cocina** (abierta con isla,
semiabierta separable, cerrada con ventilación cruzada, doble limpia/de trabajo, exterior) con preferencias por perfil;
ajustes a la **matriz D/I/N** (latino: cocina–comedor D, cocina–sala separable, cocina–lavandería y cocina–patio de
servicio D; anglosajón: cocina–sala familiar abierta, secuencia garaje–cuarto de lodo–cocina); **reglas de programa**
(factores de cocina/despensa, capacidad de comedor, terraza; sala familiar, cuarto de lodo, suite); **programa del patio**
(prioridad del asador y la terraza frente al césped o la piscina); **pesos de calidad**. **Transferencia a Colombia:**
zona de ropas como recinto y cuarto de servicio (solo prueba de transferencia).

**Validación:** todas las tendencias son hipótesis provisionales con fuente; contrastarlas con planos preaprobados y
cedidos del piloto (área y tipología de cocina, relaciones), entrevistas breves con arquitectos o constructores locales y
literatura de mercado fechada. El informe declara que son una prueba de concepto, no una caracterización de grupos.

### Ética
Vivienda justa (las reglas por persona son guía de diseño, nunca filtro de ocupación; la cultura nunca se infiere);
privacidad de los datos del hogar (guardar solo lo necesario; el paquete no expone composición ni presupuesto
innecesariamente); el índice de costo es comparativo, nunca una cotización.

### Ejemplo esperado (mismo lote cul-de-sac, mismo presupuesto relativo)
- **Multigeneracional, perfil latino:** planta baja con garaje al frente, suite accesible de la abuela, comedor amplio
  con cocina semiabierta ventilada, lavado y patio de servicio a un lateral, terraza cubierta con asador hacia el fondo
  ancho; planta alta para el resto.
- **Familia de 4, perfil anglosajón:** planta baja con gran espacio y cocina de isla abierta al jardín, secuencia garaje →
  cuarto de lodo → cocina, estudio junto a la entrada; planta alta con suite (baño y vestidor), dormitorios y lavandería.

## 4d. Paso 6.5a (esta sesión): modelo de hogar y arquetipos

**Análisis.** El arquetipo es un preajuste del vector de dimensiones, no una rama de código. La salida no es un programa
sino **necesidades por nivel** (requerida / preferida / deseable), para que 6.5d arme mínimo, óptimo y máximo sin
reinterpretar al hogar. La agrupación de dormitorios es guía de diseño, nunca límite de ocupación.

**Implementación.**
- `data/catalog/household_catalog.json` (+ `household_catalog.schema.json`): franjas de edad (con `room_role` y `grown`),
  dimensiones con valor por defecto, política de dormitorios (pareja comparte; adolescentes, adultos y mayores con cuarto
  propio; niños comparten de a 2: 0–12 en el mínimo, solo 0–5 y si `shared_rooms_ok` en el preferido; tipo del cuarto
  principal por nivel; planta baja por movilidad), niveles con perfil de área (compact / balanced / balanced), factor
  bruto 1.15, trayectoria (horizonte 5 años, vida útil 20, valores de llegada), **36 reglas** H01–H36 y **7 arquetipos**.
- `data/schemas/household.schema.json`: bloque `household` (miembros, dimensiones, `cultural_profile` elegido por el
  cliente, trayectoria con eventos `child_expected`, `elder_joins`, `adult_joins`, `member_leaves`, `mobility_change`,
  `program_tier`, `include_household`).
- `lib_aux/predicates.py`: predicados (`always/all/any/not/fact-op-value`) y expresiones numéricas (`fact`, `multiply`,
  `divide_by`, `add`, `round`, `min`, `max`) sin dominio; un hecho desconocido lanza error.
- `lib/household_catalog.py`: carga y validación semántica (hechos conocidos, tipos de espacio existentes, perfiles,
  franjas contiguas, **reglas de la capa hogar no leen el perfil cultural**).
- `lib/household.py`: modelo, superposición arquetipo + valores del cliente, validación (pareja mutua y adulta, eventos),
  `advance` (envejecimiento + eventos), agrupación de dormitorios invariante al orden, hechos.
- `lib/household_rules.py`: composición determinista (conteos por máximo, planta baja por máximo ≤ conteo, factores de
  zona por producto, garaje por máximo con tope del catálogo), pistas de relación y pesos de calidad registrados, traza.
- `lib/program_builder.py`: `program_from_needs` (instancias con `household_role`, anfitriones, piso 0 por movilidad);
  `expand_typology` no cambia. Tipos nuevos `flex_room` y `mudroom`; `storage`/`mechanical` aceptan `hall` como anfitrión.
- `main/run_household.py`: `derive_household` (ahora + siguiente etapa + `growth_delta`), `resolve_brief_program`
  (brief con `household` sin `program` → programa derivado; con ambos → gana el del brief y se registra la comparación).
  `run_capacity` llama primero a `resolve_brief_program` y añade el bloque `household` al paquete.
- CLI `household`; tabla `docs/household_rules.md`; ejemplos `examples/household_*`.

**Resultados (área bruta estimada, sq ft).**

| Arquetipo | Requerido | Preferido | Deseable | Preferido en 5 años |
|---|---|---|---|---|
| young_couple | 1282 (1 dorm.) | 2317 (1) | 2334 | 2524 |
| early_childhood | 1305 (2 dorm.) | 2185 (2) | 2829 | 2358 |
| teens_family | 1455 (3 dorm.) | 2875 (3) | 3145 | 2702 |
| multigenerational | 1524 (3 dorm.) | 3076 (4) | 3410 | 3076 |
| empty_nest | 1156 (1 dorm.) | 2116 (1) | 2133 | 2116 |
| remote_work | 1282 (1 dorm.) | 2024 (1) | 2208 | 2024 |
| shared_adults | 1506 (3 dorm.) | 2174 (3) | 2421 | 2174 |

Los 42 programas (7 × 2 etapas × 3 niveles) pasan la revisión del catálogo y del CRC sin errores ni advertencias.

**Hallazgos al pasar los programas por el lote interior 50 × 100 (un piso, sin corrección).**
- Preferido: zonifican young_couple (44), early_childhood (10) y empty_nest (43); teens_family y remote_work dan
  zonas válidas pero no distribución de espacios; shared_adults no zonifica; **multigenerational excede el FAR**
  (3,076 > 3,000): conflicto hogar–lote que 6.5d/6.8 deben resolver (dos pisos o nivel requerido).
- Requerido: **ninguno zonifica en un piso**, igual que `t2_compact` con perfil compacto. Causas: (1) sin `laundry`
  no existe zona de servicio y la enumeración da 0 topologías; (2) con `laundry` la enumeración arranca pero falla por
  fachada y perfil: la zonificación de un piso está calibrada con programas de tamaño medio. No se torcieron las reglas
  de hogar para forzarlo (principio 9); entra en 6.6–6.8.

**Pruebas nuevas (104).** Predicados; catálogo inválido (6 mutaciones); 7 arquetipos × 2 etapas × 3 niveles limpios;
orden de niveles; traza completa; política de dormitorios; trabajo y garaje; trayectoria; MR-H1 monotonía (4 tipos de
miembro × 7), MR-H2 orden, MR-H3 preajuste = entrada manual, MR-H4 perfil cultural inerte, MR-H5 etapa siguiente =
envejecimiento manual; vivienda justa (hogar de 10); validación (7 casos); privacidad; apartamento sin garaje;
integración con el brief; CLI.

**Limitaciones nuevas.**
1. Pistas de relación (suite accesible `en_suite`, estudio `near` la entrada) y pesos de calidad se registran pero aún
   no se aplican en la zonificación (6.7 / 6.8).
2. `household_role` existe en las instancias, pero la matriz D/I/N sigue funcionando por tipo.
3. Requerido no zonifica en un piso (ver hallazgos); lavandería en armario elimina la zona de servicio.
4. `brief_sha256` del paquete se calcula sobre el brief resuelto (con el programa derivado).
5. Todas las reglas son hipótesis `provisional`; el baño mínimo (CRC R306) y el estacionamiento (SDMC Cap. 14) por verificar.
6. Un solo paso de trayectoria (ahora + horizonte); el estudio y el cuarto de huéspedes no se fusionan en el mínimo.

## 4e. Paso 6.5b (esta sesión): índice de costo relativo

**Análisis.** La pieza central es la **ficha de cantidades**, no la fórmula: cualquier modelo (relativo hoy, real,
carbono o energía después) lee solo la ficha. El índice se normaliza contra una **ficha de referencia sintética**
(mezcla de referencia, un piso, rectángulo, plano, sin obras exteriores) evaluada con el mismo modelo, de modo que la
referencia vale 1 en todos los modelos y el modelo base coincide con bruta ÷ FAR.

**Implementación.**
- Catálogo 0.8.0 `cost_index`: clases de área (zona → clase, húmedos aparte, clase ancla `habitable_dry` fija en 1),
  coeficientes y factores de forma como **rangos (mín., más probable, máx.)**, umbral de ladera, mezcla de referencia,
  vivienda de referencia 2,000 sq ft, niveles de presupuesto 0.45/0.65/0.85, leyenda "comparativo, no cotización".
  Validación semántica en `lib/catalog.py` (`cost_index_errors`). Tabla en `docs/parameter_table.md`.
- `lib/quantities.py`: `QuantitySheet` con base por ítem (measured/derived/estimated/reference/not_available) y
  confianza = peor base. Respeta `required_gross_area_sqft` declarado; con 2+ pisos agrega la escalera repetida.
  Huella, perímetro, pavimento y deck medidos cuando hay opción de sitio; estimados (rectángulo 1.5:1) si no.
- `lib/cost_models.py`: protocolo `CostModel` + `base`, `weighted`, `shape` (registro por nombre), `relative_index`.
- `lib/budget.py`: nivel o fracción → máximo construible, restricción que manda (normativa/presupuesto), veredictos,
  sugerencia de construcción por etapas.
- `lib/cost_sensitivity.py` + `lib_aux/weighted.py`: tornado uno-a-la-vez; con dos opciones mide B − A y marca los
  parámetros que **cruzan cero** (`decisive_parameters`).
- `main/run_cost.py`: `package_cost` (lectura `lot`: programa × cada opción de sitio + niveles del hogar × pisos) y
  `household_cost` (lectura `reference_dwelling`). Integrado en `run_capacity` (bloque `cost`, paquete 0.9) y en
  `derive_household` (ahora y etapa siguiente). `resolve_brief_household` devuelve también los programas por nivel.

**Resultados.**
- interior_50x100: n1 0.737 / n2 0.777 (base); con `shape` casi empatan (0.776 / 0.772). Tornado: **solo el factor de
  dos pisos invierte la decisión**; los coeficientes por clase casi se cancelan con la referencia.
- fan_cul_de_sac (B escalonado): n1 0.652 / n2 0.687 (base); con `shape` gana n2 (0.710 / 0.706), otra vez decidido
  por `form:two_floors`. Primer parámetro a validar con constructores locales.
- interior_50x100_multigen, presupuesto ajustado: requerido 0.51–0.55, preferido 1.03–1.07 (excede la norma),
  sugerencia de construcción por etapas.

| Arquetipo (vivienda de referencia = 1) | Requerido | Preferido | Deseable | Preferido `shape` | Preferido en 5 años |
|---|---|---|---|---|---|
| young_couple | 0.64 | 1.16 | 1.17 | 1.19 | 1.26 |
| early_childhood | 0.65 | 1.09 | 1.41 | 1.13 | 1.18 |
| teens_family | 0.73 | 1.44 | 1.57 | 1.48 | 1.35 |
| multigenerational | 0.76 | 1.54 | 1.70 | 1.61 | 1.54 |
| empty_nest | 0.58 | 1.06 | 1.07 | 1.09 | 1.06 |
| remote_work | 0.64 | 1.01 | 1.10 | 1.07 | 1.01 |
| shared_adults | 0.75 | 1.09 | 1.21 | 1.14 | 1.09 |

**Pruebas nuevas (29).** Catálogo inválido (5), sin moneda en código ni datos, ficha estimada/medida, escalera
repetida, MR-C1 monotonía, MR-C2 proporcionalidad con la referencia, MR-C3 referencia = 1, MR-C4 coeficientes neutros
= base, MR-C5 orden de niveles, factores de forma, presupuesto, staging, apartamento sin bloque, tornado ordenado y
recalculado a mano, CLI.

**Limitaciones nuevas.**
1. Todos los coeficientes son hipótesis `provisional`; el índice es comparativo, nunca una cotización.
2. Perímetro medido = caja envolvente de la huella (subestima huellas escalonadas); piso por piso es reparto parejo.
3. Núcleos húmedos estimados (uno por piso); cubierta = huella (cubierta plana).
4. El tornado no capta interacciones; el intervalo Monte Carlo queda para 6.8 (los rangos ya están en el catálogo).
5. El presupuesto solo aplica en la lectura `lot`; los niveles por arquetipo en la lectura `lot` son estimados.

## 4f. Paso 6.5c (esta sesión): capa cultural latina y anglosajona

**Análisis.** Mismo patrón que el arquetipo: **el perfil es un preajuste de 9 aspectos explícitos** que el cliente ve y
edita; las reglas culturales leen aspectos, nunca la etiqueta. Sin perfil ni aspectos no se activa ninguna regla
cultural (neutralidad). La cultura solo agrega o sube de nivel: nunca quita un espacio requerido por el hogar. Lo que
el brief fija explícitamente gana sobre la cultura.

**Implementación.**
- Catálogo de hogar 0.2.0: `culture_aspects` (9), `culture_presets` (latino, anglo, mixed, custom; los dos últimos
  vacíos), `kitchen_typologies` (open_island, semi_open_separable, closed_ventilated, double_kitchen) con sus efectos,
  `kitchen_typology_selection` (primera coincidencia; la elección explícita del cliente gana) y **13 reglas C01–C13**.
  Validación: aspectos = `enums.CULTURE_ASPECTS`, valores de preajustes, roles de matriz, anclajes, elementos de patio,
  tipos de espacio; las reglas de la capa hogar no pueden leer hechos culturales ni usar efectos culturales.
- Catálogo residencial 0.9.0: tipo `work_kitchen`; roles de matriz `work_kitchen` y `mudroom`; elementos de patio
  `covered_terrace` y `outdoor_kitchen` (toca el elemento que requiere: `touch_deck` generalizado); clase de costo
  exterior `backyard` (0.25/0.4/0.6).
- `lib/household_rules.py`: `_apply_effect` único para todas las capas; efectos nuevos `type_area_factor`,
  `relation_override` (mayor peso por par de roles, N = 0), `anchor_override` (modo más fuerte), `backyard_element`
  (menor número; `add` para terraza y cocina exterior), `backyard_green` (mayor). Tipología como regla `KT-*`.
- `lib/culture.py`: `merge_culture_into_brief` → `relation_overrides`, `zoning_overrides.anchors`, `backyard_program`
  con registro `applied` / `overridden_by_brief`. `resolve_brief_household` lo aplica; bloque `household.culture`
  en el paquete (el perfil solo con `include_household`).
- Ficha de cantidades: área de los elementos de patio colocados (no verdes) como clase `backyard`, medida.
- CLI `--culture`; tabla `docs/household_rules.md` con aspectos, preajustes y tipologías;
  `docs/culture_validation_protocol.md`; briefs `interior_50x100_multigen_latino/anglo.json`;
  `examples/household_culture.txt`.

**Resultados (programa preferido; tipología · bruta sq ft · índice ponderado vs vivienda de referencia).**

| Arquetipo | Sin perfil | Latino | Anglosajón | Índice sin perfil |
|---|---|---|---|---|
| young_couple | 2317 | semi_open_separable · 2369 · 1.21 | open_island · 2421 · 1.24 | 1.19 |
| early_childhood | 2185 | semi_open_separable · 2237 · 1.16 | open_island · 2340 · 1.21 | 1.13 |
| teens_family | 2875 | semi_open_separable · 2932 · 1.51 | open_island · 2978 · 1.54 | 1.48 |
| multigenerational | 3076 | semi_open_separable · 3157 · 1.65 | double_kitchen · 3295 · 1.74 | 1.61 |
| empty_nest | 2116 | semi_open_separable · 2168 · 1.11 | open_island · 2271 · 1.17 | 1.09 |
| remote_work | 2024 | semi_open_separable · 2248 · 1.18 | open_island · 2145 · 1.13 | 1.07 |
| shared_adults | 2174 | semi_open_separable · 2225 · 1.16 | open_island · 2329 · 1.22 | 1.14 |

- Multigeneracional: latino → cocina semiabierta separable, comedor ×1.3 ligado al patio (D 2.0), sala familiar,
  cocina–lavandería D dura + lavandería–patio, patio con terraza cubierta y cocina exterior. Anglosajón → la cocina
  intensiva del hogar con relación abierta da **doble cocina** (`work_kitchen`), cuarto de lodo, rincón de desayuno,
  lavandería cerca de dormitorios (cocina–lavandería pasa a I), baño por dormitorio deseable, patio con piscina y
  50 % verde.
- En el lote 50 × 100 el patio cambia de verdad: latino coloca terraza cubierta 200 + cocina exterior 48; anglosajón
  terraza 150 + piscina 300 + asador. El índice ponderado del costo recoge la diferencia (clase `backyard` medida).
- Con el nivel requerido la zonificación de un piso sigue sin esquema (limitación de 6.5a, sin cambios).

**Pruebas nuevas.** Catálogo cultural inválido (7), ética (sin hechos de nombre, origen, idioma, etnia), MR-K1
neutralidad (7 arquetipos), MR-K2 preajuste = aspectos manuales, MR-K3 la cultura no quita espacios y los programas
siguen limpios (7 × 2), MR-K4 toda diferencia trazada a una regla cultural (7 × 2), MR-K5 el brief gana, dos perfiles
difieren, selección de tipología (5), elección explícita y perfil mixto, extremo a extremo en el lote (2), CLI.
MR-H4 se reescribió: la capa hogar es idéntica bajo cualquier perfil.

**Limitaciones nuevas.**
1. Todas las tendencias son hipótesis `provisional`; validación según `docs/culture_validation_protocol.md`.
2. La secuencia garaje → cuarto de lodo → cocina y "lavandería cerca de dormitorios" son pistas: se aplican en 6.8.
3. Los overrides se aplican a la zonificación del nivel elegido; la matriz sigue por tipo (no por `household_role`).
4. Más relaciones duras (cocina–cocina de trabajo) pueden bajar la tasa de zonificación; no se midió todavía en lote.
5. El preajuste colombiano (zona de ropas, cuarto de servicio) queda para la prueba de transferencia.

## 4g. Paso 6.5d (esta sesión): portafolio de programas y láminas de revisión

**Análisis.** Mínimo, óptimo y máximo salen de **una sola curva de expansión**: desde el nivel requerido, en cada paso
la mejora factible con mayor ganancia de calidad por unidad de índice de costo. Techos: normativo (bruta ≤ FAR) y
presupuestario (índice ≤ fracción). Mínimo = inicio; máximo = último punto (se reporta qué techo lo detuvo); óptimo =
**codo** de calidad vs costo (regla de Kneedle). La calidad es un **indicador de programa provisional** (necesidades
preferidas y deseables, cultura ×1.25, tamaño por zona, autos, **cobertura de la etapa siguiente**) hasta el puntaje
geométrico de 6.8. Factibilidad en tres estados: cabe en 1 piso / requiere 2 pisos (6.7) / excede la norma.

**Diagnóstico previo (perfil anglosajón sin planta).** Dos causas: (1) `breakfast_nook` estaba en la zona *kitchen*
pero las particiones de zona lo ponen en la parte comedor de la social → movido a *social* (catálogo 0.10.0);
(2) el cuarto de lodo necesitaba más búsqueda → **reintento acotado** (`circulation.search_retry`: 200 esquemas,
1,500 combinaciones) solo cuando hay esquemas de zonas sin distribución de espacios; desactivado en la corrección.
Ahora zonifican: nido vacío anglo, familia con adolescentes latino y anglo. Siguen sin planta en 1 piso: crianza
temprana y pareja joven anglo (el baño de los niños queda sin acceso a circulación; topología → 6.7 / 10).

**Implementación.**
- `lib_aux/knee.py`: `knee_index` (Kneedle) y `greedy_ratio_path` (mejor razón ganancia/costo con factibilidad), sin dominio.
- Catálogo de hogar 0.3.0: `program_quality` (pesos, multiplicador cultural, ganancia mínima del codo) y
  `program_substitutions` (split_social, primary_suite, laundry_room, work_study), todo provisional.
- Catálogo residencial 0.10.0: `cost_index.later_works_factor` (1.1/1.2/1.35), `accessibility` (baño ×1.3, dormitorio
  ×1.1, paso 4 ft, puerta 34 in, giro 5 ft, entrada sin escalón; guía de diseño universal provisional),
  `circulation.search_retry`, `display` (etiquetas, plantillas de observaciones y textos de lámina en es/en).
- `lib/program_profiles.py`: `ProfileContext` (estados, movimientos, programa por estado, índice, techos),
  `expansion_profiles`, `staged_profile` (hoy + después × factor, prima por etapas, convertibles),
  `accessible_program`, `floor_feasibility`.
- `lib/review_notes.py`: observaciones automáticas (vínculo débil con el patio, área privada a través de lo social,
  puerta al patio desde dormitorio o vestidor, cocina o suite sin jardín, áreas bajo objetivo o mínimo, circulación,
  jardín, patio excluido, satélites) → semilla del detector de soluciones forzadas de 6.8.
- `lib/visualize.py`: `plot_review_sheet` (planta a escala con cotas, puertas, cuadro de áreas, leyenda,
  observaciones) y `plot_portfolio_sheet` (curva con perfiles, techos, tabla, etapas).
- `main/run_profiles.py` + CLI `profiles`; `main/run_household.household_stages`; `zone_site_options(retry=...)`.

**Resultados (lote interior 50 × 100, FAR 3,000 sq ft; índice base).**

| Hogar · perfil · presupuesto | Mínimo | Óptimo | Máximo (techo) | Planta 1 piso |
|---|---|---|---|---|
| Crianza temprana · latino · medio | 1,305 · 0.435 | 1,530 · 0.510 | 1,932 · 0.644 (presupuesto) | óptimo y accesible |
| Nido vacío · anglo · sin presupuesto | 1,156 · 0.385 | 1,558 · 0.519 | 2,277 · 0.759 (programa completo) | óptimo, máximo y accesible |
| Multigeneracional · latino · holgado | 1,524 · 0.508 | 1,811 · 0.604 | 2,542 · 0.847 (presupuesto) | ninguno (→ 6.7) |

- Etapas (crianza temprana): hoy 0.435 + después 0.090 = 0.525 vs construir el final ya 0.510 (prima +0.015).
- El óptimo deja fuera los aumentos de tamaño y el segundo auto: rinden poco por unidad de costo.
- Las láminas confirman en planta lo que el detector lista (p. ej. pasillo privado que abre a la sala y al comedor).

**Limitaciones nuevas.**
1. La calidad es un indicador de programa; no ve la geometría (6.8 la reemplaza por el puntaje común).
2. El perfil accesible exige dormitorio y baño en planta baja, no su contigüidad (en suite); en la lámina de
   crianza temprana el baño accesible es el de los niños.
3. El mínimo casi nunca zonifica en 1 piso (lavandería en armario, pocas zonas): limitación de la zonificación.
4. El reintento de búsqueda puede tardar 20–30 s cuando no hay solución; la suite pasó de ~4 a ~9 min.
5. Los motivos del patio (`requires rear_deck`, `group 'water'`) siguen en inglés en las láminas.

## 4h. Paso 6.6 (esta sesión): análisis de áreas por lote

**Decisiones del usuario.** Agregar los lotes del piloto que faltaban; 7 arquetipos × 3 perfiles; reparto de dos
pisos a nivel de áreas **con el índice de construcción** (y el de ocupación); no limitar los dos pisos a "privada
arriba": opciones por arquetipo (caso del nido vacío); E2 solo para un piso; lote bandera provisional; garaje en el
IC como sensibilidad.

**Implementación.**
- DSL 0.4.0: `Z15-BUILDING-INDICES` (IC = FAR, IO = cobertura en ladera; variantes `garage_included` por defecto y
  `garage_excluded`, `verified: false`, SDMC 113.0234 pendiente).
- Catálogo 0.11.0: `area_analysis` (perfiles, estrategias, umbral indicativo de jardín 20 %, frente duro/blando,
  planta alta útil 300 sq ft, uso diario, E2) y `vertical_schemes` (15 grupos, V0–V5 con predicados de
  aplicabilidad, grupos cohesivos = suite, regla de lavandería por aspecto cultural, pesos y 5 multiplicadores
  VS01–VS05). Validación semántica en `lib/catalog.py`. Brief 0.5: `lot.flag` y `terrain.view_side`.
- 4 lotes nuevos: `shallow_50x95`, `narrow_40x125`, `hillside_50x100` (vista posterior), `flag_70x80_pole20`.
- `lib_aux/pareto.py`; `quantities.build_sheet(floor_shares=...)`; `site_partition.site_context` y
  `measure_footprint` (E1); `_option_b(steps=...)`.
- El máximo de dos pisos se recalcula con techo FAR − escalera; el cliente puede fijar un esquema (`--scheme`).

**Resultados** (detalle en `docs/area_analysis.md`, figuras y CSV en `examples/area_matrix/`).
- 3,148 celdas en 10 lotes, ≈ 40 s sin E2. El FAR casi nunca obliga a dos pisos.
- En abanicos manda el **pavimento del antejardín** con B (no el frente); en la curva ningún máximo es factible.
- En ladera el **IO 50 % bloquea 19 celdas** (máximos de un piso y V4): dos pisos pasan a ser condición.
- Cruce un piso / dos pisos en **IC ≈ 0.35** (19 % → 59 % → 80 % → 100 % por tramo de 0.1).
- V1 vs V0 con el mismo óptimo: +≈ 520 sq ft de área libre (+14–19 %), IO −0.10.
- Garaje en el IC: 0 veredictos cambian; holgura de 0.05–0.10 en los máximos.
- Nido vacío: V0 gana, pero en el máximo compiten V1 ≡ V2 (suite abajo por H16) y V4; adolescentes → V2;
  multigeneracional máximo → V1/V3 (abuelos abajo).
- E2: 7 de 20 zonifican; el nido vacío zonifica en un piso en el cul-de-sac y en la curva.

**Pruebas nuevas (59).** MR-A1 más programa ⇒ no más área libre; MR-A2 dos pisos liberan suelo; MR-A3 coherencia
con 6.5d; MR-A4 estrategias colapsan en rectángulos; MR-A5 la escalera es la única diferencia de IC; MR-A6 privada
arriba ⇒ menor IO; MR-A7 IO en ladera; MR-V1 movilidad reducida abajo; cohesión de la suite; MR-V2 un piso sin
dependencia de escalera; MR-V3 esquema fijado por el cliente; MR-V5 el hogar cambia el orden, no el conjunto;
supervisión, separación, lavandería por cultura, V5 con vista; variantes de garaje; catálogo inválido (7); sin
números normativos en el código nuevo; bandera (3); lotes nuevos; Pareto; CLI.

**Limitaciones nuevas.**
1. Puntaje de esquemas provisional; pesos cercanos deciden cruces (calibrar en 6.8 con planos del piloto).
2. Dos pisos solo a nivel de áreas: sin planta alta dibujada, escalera ni plano envolvente (6.7).
3. El jardín medido no es monótono en abanicos (no cuenta cuñas laterales): el puntaje usa área libre.
4. Lote bandera provisional; la conformidad reporta la profundidad del cuerpo.
5. Láminas E2 del abanico rotulan como "frente" el ancho mayor del lote (heredado).

## 5. Resultados de referencia (paso 5) (paquete 0.6)

| Brief | Estado zonificación | Válidos (zonas / espacios) | Tiempo | Nota |
|---|---|---|---|---|
| interior_50x100 (n1) | zoned | 28 / 30 | ~3 s | Sala a la calle, comedor detrás, cocina al patio, lavandería alojada; circulación ≈ 20 % |
| corner_55x100 (n1) | zoned | 72 / 6 | ~5.5 s | Gran salón sala+comedor al frente; circulación ≈ 20 % |
| fan_cul_de_sac (n1) | no_valid_scheme | 0 | ~0.7 s | Frente 33 ft insuficiente para sala 12 + vestíbulo + garaje doble 20 |
| fan_curve | site infeasible | — | — | Pavimento 63 % > 60 % (corrección propuesta: acceso de 1 auto) |
| apt_2br_interior (40×36) | zoned | 16 / 64 | ~0.1 s | Núcleo húmedo + cocina + vestíbulo al pasillo; spine; circulación 14 % |
| apt_2br_corner (42×34) | zoned | 168 / 238 | ~0.6 s | Mejor: sala-comedor pasante; circulación 13–19 % |

Las opciones de 2 pisos (n2) quedan `deferred_to_stacking` (paso 7).

## 6. Limitaciones y deuda técnica conocidas

1. La circulación ronda 19–21 % en casas (umbral de alerta 20 %): el spine de ancho completo y los pasillos a lo largo
   de toda la celda son generosos. Mejorar con spine parcial y pasillos de longitud mínima.
2. El nivel de espacios **no es exhaustivo** (topes); el ranking puede perder buenas soluciones.
3. Las condiciones de la matriz a nivel de zonas son necesarias pero laxas (`_near` admite un vecino común).
4. Las franjas usan distancia en L entre puertas; las puertas se ubican en el punto medio del muro compartido.
5. Puertas al patio: cualquier espacio no húmedo con fachada trasera (falta control fino de dormitorios).
6. El patio se planifica solo sobre el esquema #1 de cada opción y con la huella de su variante.
7. Apartamentos sin normativa multifamiliar (zonas RM, CBC R-2); solo mínimos de habitabilidad.
8. Lotes en abanico fallan por geometría rectangular: requieren la estrategia B (paso 6).
9. Las pruebas tardan ~65 s (fixture de sesión corre los 6 briefs).

## 7. Verificaciones normativas pendientes (todas marcadas `verified: false`)

- Altura 24/30 ft (131.0444(b)), medición 113.0270, Diagrama 131-04L (plano envolvente), definición de *steep hillsides*.
- Ancho y profundidad de lote irregular y posterior en lotes triangulares (Cap. 11).
- Si el deck cuenta como pavimento (131.0447); si garaje/deck/bodega cuentan en el FAR.
- Piscina/jacuzzi: separaciones a linderos y vivienda (valores *placeholder* 5/3/5 ft) y barrera de seguridad (CA H&SC).
- Estructuras accesorias en zonas RS (placeholder 3 ft).
- CRC 2025: numeración y valores de habitabilidad (70 sq ft, 7 ft, 8 %/4 %), pasillo 36 in, separación garaje–vivienda.
- Mapa C-1041 (Clairemont), fuente de datos de calle, licencia de IfcOpenShell.

## 8. Próximos pasos (plan spaceplan v1.1 + revisiones)

| # | Paso | Notas para el nuevo chat |
|---|---|---|
| 6 | ~~Estrategia B~~ **hecho** | Pendientes derivados: tercera banda; núcleos menos conservadores en el modo poligonal; junta en "T". |
| 7 | **Apilamiento en varios pisos** | Zonificar n≥2: escalera alineada en todos los pisos (área repetida), privada arriba por defecto, 131.0460 (tercer piso), 131.0444 (plano envolvente). Habilita `interior_50x100` n2 (opción seleccionada por el jardín). |
| 8 | Expansión con satélites y prohibiciones | Parte ya cubierta por el nivel de espacios; formalizar el grafo cociente y la verificación zona↔espacio. |
| 9 | Asignación de áreas (QP) | Sustituir el escalado proporcional por optimización con mínimos duros y perfiles. |
| 10 | Configuración fina y métricas | Spine parcial, pasillos mínimos, puertas con posición y abatimiento, métricas de sintaxis espacial. |
| 11 | MAP-Elites | Descriptores: posición del deck, tipo de sendero, columna pasante, spine, partición privada, fusión de servicio. |
| 12 | Conexión con planogen | El esquema de espacios reemplaza el paso 6 de planogen. |
| 13 | Exportador IFC | IfcSpace/IfcZone/IfcDoor desde el paquete. |


### Plan ajustado (paso 6.5 y portafolio; todo antes de F3, marzo 2027)

| # | Paso | Fecha | Horas | Salida verificable |
|---|---|---|---|---|
| 6.5a | ~~Modelo de hogar por dimensiones, arquetipos, trayectoria, reglas con fuente (brief 0.3)~~ **hecho** | oct 2026 | 8 | 7 arquetipos × 2 etapas × 3 niveles cumplen el CRC |
| 6.5b | ~~Índice de costo relativo, presupuesto, ficha de cantidades, interfaz intercambiable, tornado~~ **hecho** | oct 2026 | 5 | Máximo normativo = 1 en los tres modelos; restricción activa reportada |
| 6.5c | ~~Capa cultural latina/anglosajona: tipologías de cocina, matriz D/I/N, programa, patio, pesos~~ **hecho** | oct 2026 | 7 | Mismo lote y hogar con dos perfiles → programas, relaciones y patio distintos y trazables |
| 6.5d | ~~Generador mínimo/óptimo/máximo + por etapas + accesible, contra la etapa siguiente, láminas~~ **hecho** | oct 2026 | 8.5 | 5 perfiles por brief con curva, techo activo y láminas |
| 6.6 | ~~Análisis de áreas por lote: programa × esquema vertical × estrategia, IC/IO, 4 lotes nuevos~~ **hecho** | oct 2026 | 8 | Tabla y figuras por lote del piloto |
| 6.7 | Apilamiento grueso integrado al portafolio: geometría de los esquemas V1–V5 (planta alta contenida, escalera en la junta, plano envolvente 131.0444) | ene 2027 | 8 | Los mejores esquemas de 2 pisos de 6.6 con planta dibujada |
| 6.8 | Puntaje de calidad común, Pareto del portafolio, codo costo–calidad, detector de soluciones forzadas, retroceso por columna, perfiles por tipo de lote | feb 2027 | 8 | Opción recomendada con alternativas y explicación |

Total ≈ 50 h (6.6 tomó 8 h por los esquemas verticales, los índices y el lote bandera). Mínimo viable ≈ 14 h: 6.5a con 4 arquetipos, 6.5b nivel base, 6.5c solo cocina y matriz D/I/N.
El paso 7 detallado (zonificación por piso con la junta como núcleo) queda para un curso o después de F3.

## 9. Posibilidades de innovación registradas

- (paso 6.6) Curva IO–IC del piloto como figura central; umbral de cruce un piso / dos pisos (IC ≈ 0.35) como regla
  explicable y contrastable con planos aprobados de Clairemont; transferencia a un POT colombiano declarando IO e IC
  en `Z15`; valor del segundo piso en área libre por unidad de índice; sensibilidad de la definición de área
  construida como riesgo normativo para RuleForge; barrido paramétrico de lotes con planogen; esquemas verticales
  aprendidos de planos preaprobados; costo de adaptación a 20 años por esquema (V1 → vida en una planta vs V2).

- (paso 6.5d) Curva calidad–costo por hogar y lote como figura central; óptimo de trayectoria (costo total a 20 años);
  explicación mejora por mejora; láminas comparativas (mínimo/óptimo/máximo o dos perfiles lado a lado); detector de
  lecturas débiles → detector de soluciones forzadas (6.8); accesible con contigüidad en suite exigida; búsqueda
  adaptativa del nivel de espacios guiada por la primera falla (reachability) en lugar de topes fijos.

- (paso 6.5c) Cuestionario de hábitos que llena los aspectos sin mencionar cultura; brief en lenguaje natural con GBNF
  (solo aspectos, con confirmación); tornado cultural (qué aspecto mueve más programa y costo por lote); co-ocurrencia
  de aspectos medida en planos del piloto (¿se sostienen los preajustes?); figura "mismo lote, distintos hogares y
  perfiles"; preajuste colombiano como prueba de transferencia; tipologías de cocina aprendidas como propuestas que el
  estudiante acepta (patrón RuleForge).

- (paso 6.5b) Intervalo Monte Carlo con semilla fija y "empate técnico" (6.8); ciclo tornado → validar → angostar rangos
  → Monte Carlo como figura del informe; razones entre tipos de ocupación de tablas públicas de valoración, guardando
  solo la proporción (fuente y licencia por verificar); carbono incorporado o energía sobre la misma ficha; costo de
  trayectoria (preferido hoy vs mínimo + ampliación); holgura de FAR visible; perímetro real del polígono de huella.

- (paso 6.5a) Línea de tiempo completa del hogar (0–20 años) y costo de adaptación por opción; sensibilidad de área por
  dimensión; calibración de la mezcla de arquetipos con datos censales del piloto (por verificar fuente y año); matriz
  "mismo lote, distintos hogares"; brief de hogar en lenguaje natural con GBNF (sin inferir cultura); minería de reglas
  desde planos preaprobados; puntaje de diseño universal; detector de conflicto hogar–lote en una frase; fusión estudio +
  huéspedes en el mínimo; reglas aprendidas como propuestas que el estudiante acepta (mismo patrón que RuleForge).

- (paso 6.5) Mismo lote, distintos hogares y culturas (matriz visual de casas óptimas); óptimo de trayectoria; tipologías
  de cocina como variable de diseño; restricción activa extendida (código, presupuesto, lote u hogar); ficha de
  cantidades abierta a costos reales, energía o carbono; validación cultural con planos del piloto; brief en lenguaje
  natural con gramática GBNF; detector de soluciones forzadas; mapa de decisión por lote; uso explícito de la holgura
  de FAR.
- (paso 6) Tercera banda; junta en "T" o con quiebre que salte el par abierto; Pareto con más ejes (jardín, residuo,
  profundidad desde la entrada); calibración de la política poligonal con recintos trapezoidales construidos; curva de
  frente requerido vs `max_area_shift`.

- Mapa de qué regla de la matriz bloquea cada lote (estadísticas de falla) como explicación al cliente.
- Profundidad desde la entrada y privacidad cuantificada (sintaxis espacial) con el grafo de puertas.
- Matriz D/I/N validada con planos preaprobados reales; matriz cultural colombiana (servicio, patio de ropas).
- Eficiencia de circulación vs forma de lote y estrategia (figura del informe).
- Ubicación óptima de la puerta en apartamentos; planta tipo multifamiliar con pasillo común.
- Corrección mínima generalizada (pavimento, frente, matriz) y reubicación del acceso según la zonificación.
- Calibración bayesiana del catálogo; brief en lenguaje natural con gramática GBNF (técnica de RuleForge).

## 10. Mensaje sugerido para abrir el nuevo chat

> Adjunto `spaceplan_steps_1_6_6.zip` y este HANDOFF. Continuamos el módulo spaceplan del capstone con el **paso 6.7:
> apilamiento grueso** (geometría de los esquemas verticales de 6.6: planta alta contenida, escalera en la junta,
> plano envolvente 131.0444) sobre los mejores esquemas de dos pisos del piloto. Respeta las reglas de la sección 1.
> Primero haz el análisis lógico y el plan, y pregúntame antes de programar.
