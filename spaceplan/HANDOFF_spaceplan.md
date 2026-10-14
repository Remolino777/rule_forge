# HANDOFF — `spaceplan`, paso 6.6: análisis de áreas por lote (programa × esquema vertical × estrategia, IC e IO)

> **Qué vamos a agregar.** El programa de necesidades deja de ser un dato fijo del brief. El sistema recibirá **quién
> vive** (arquetipo de hogar con su trayectoria), **cómo vive** (perfil cultural: latino o anglosajón, con distinta
> importancia de la cocina) y **cuánto puede invertir** (presupuesto relativo, sin valores reales). Con eso generará tres
> programas (**mínimo, óptimo y máximo construible**, más los perfiles **por etapas** y **accesible**) que competirán en un
> **portafolio de opciones** (programa × número de pisos × estrategia de huella), en lugar de forzar soluciones de un
> solo piso dentro de un paso.

Módulo `spaceplan` de Municipal Permit Intelligence.

Fecha: 12 de octubre de 2026 · Estado: **paso 6.7a S2.2d parte 1 hecha (sección 4w: escalera en la franja central K12, planta alta óptima con techo y terraza de 3 ft; 26 de 291 casas)**; S2.2c (4v, 39 casas); S2.2b (4u); S2.2a (4t) · catálogo de apilamiento 0.12.0 · estándares de diseño 0.5.0 · registro de diseño 0.3.0 · reglas de cliente 0.6.0 · reglas de aberturas CRC 0.3.0 · catálogo residencial 0.13.0
Capstone MS-AAI, University of San Diego (18 meses desde sept. 2026; cierre feb. 2028). Preparado con asistencia de
Claude (Anthropic); declararlo en el informe según la política de IA de USD.

---

## 1. Reglas de trabajo del usuario (obligatorias en el nuevo chat)

1. Responder en **español**; el **código siempre en inglés**.
2. **Primero análisis lógico y plan de acción en pasos**; **preguntar siempre antes de empezar a programar**.
3. Incluir siempre una sección de **posibilidades de innovación**.
4. Estructura de código: `main/` (workflow), `lib/` (funciones de dominio), `lib_aux/` (sub-librería sin conocimiento
   de dominio), dentro de cada módulo (`core/`, `modules/<m>/`, `pipeline/`). `lib_aux` no importa `lib`/`main`;
   `lib` no importa `main`; los módulos siguen el grafo acíclico del plan y hablan por contratos (lo verifica
   `tests/pipeline/test_architecture.py`).
5. Ningún número normativo en el código: los valores viven en `data/rules/*.json` (DSL) y los parámetros de diseño
   en el catálogo (`data/catalog/fragments/*.json`, un fragmento por módulo), cada uno con su fuente y estado
   (`verified`/`provisional`).
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
git clone --branch spaceplan-modular https://github.com/Remolino777/rule_forge && cd rule_forge/spaceplan
pip install -e ".[dev]"            # shapely, numpy, jsonschema, networkx, matplotlib, pytest
python -m pytest -q tests/cost             # un módulo (segundos); suite completa por carpetas (tests/<módulo>/), ~10 min
python tools/golden_check.py check          # GOLDEN CHECK PASSED (nada cambió)
spaceplan capacity spaceplan/data/briefs/interior_50x100.json --contracts out/contracts   # contratos de cada módulo
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

**Arquitectura modular (reestructuración 8–9 oct 2026, sección 4i).** El flujo de arriba no cambió; ahora cada
etapa es un módulo con `main/` (workflow), `lib/` (dominio) y `lib_aux/` (sin dominio) y entrega un **contrato JSON**.
Grafo de dependencias, archivos por capa y contratos **generados desde el código**: `docs/architecture/modules.md`.

| Módulo | Responsabilidad | Contrato que produce |
|---|---|---|
| `core/` | DSL (`rules`), catálogo en fragmentos (`catalog`), contratos (`contracts`), validación, grafo de relaciones; `lib_aux`: geometría, `Quantity`, hash, JSON, sección, predicados, codo, Pareto | — |
| `modules/lotcap/` | Capa 0: lote, linderos, métricas, variantes de reglas, alcance, capacidad A/B, lote bandera, selección de estrategia (`run_lotcap`) | `lot_capacity` |
| `modules/site/` | Capa 1: partición del sitio por pisos, orientación, patio (`run_site`) | `site_plan` |
| `modules/household/` | Hogar, catálogo de hogar, reglas, cultura, tipologías, revisión del programa (`run_household`, `run_program`) | `program` |
| `modules/cost/` | Ficha de cantidades, modelos de costo, presupuesto, tornado (`run_cost`); lee `lot_capacity`, `site_plan` y `program` como JSON | `cost_report` |
| `modules/profiles/` | Curva de expansión, mínimo/óptimo/máximo, por etapas, accesible (`run_profiles`) | `program_portfolio` |
| `modules/zoning/` | Zonas y espacios, circulación, matriz D/I/N, estrategias A/B, poligonal, correcciones, unidad (`run_zoning`, `run_corrections`) | `zoning_scheme` |
| `modules/areas/` | Esquemas verticales, IC/IO, presupuesto de áreas, matriz por lote (`run_area_matrix`) | `area_matrix` |
| `modules/viz/` | Figuras y láminas; `main/run_viz` dibuja desde contratos | — |
| `pipeline/` | Composición: `run_capacity` (encadena contratos), `run_portfolio`, `run_area_analysis`, `run_household_report`, `run_catalog`, `run_modules`, CLI; `lib/package` arma el paquete solo desde contratos | `package` (0.9) |

Datos: `data/schemas/` (brief 0.5, package 0.9, catalog), `data/rules/sdmc_rs_1_7_capacity.json` (v0.4.0, Z00–Z15),
`data/rules/crc_2025_habitability.json` (v0.2.0, C01, C03, C06), `data/catalog/fragments/*.json` (catálogo residencial
0.11.0 en 8 fragmentos por módulo + `index.json`; el archivo único `residential_catalog.json` se eliminó en la tanda 4),
`data/catalog/household_catalog.json` (0.3.0), `data/briefs/` (15 briefs: 13 casas, 2 apartamentos),
`contracts/schemas/` (7 contratos 0.2.0).

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

## 4i. Reestructuración modular (8–9 oct 2026, 4 tandas programadas): módulos por etapa y contratos

**Qué cambió (sin cambiar resultados).** Refactorización pura en la rama `spaceplan-modular` (ramas instantáneas
`refactor/tanda-0` a `refactor/tanda-4`; plan en `docs/refactor/REFACTOR_PLAN.md`, informes en
`docs/refactor/log/`). Los 15 paquetes de referencia y la tabla del piloto son idénticos a la instantánea dorada
(`python tools/golden_check.py check`); además, los 21 paquetes en bruto (orden de claves, bloques sin redondear,
tres combinaciones de opciones) son idénticos byte a byte a los de la tanda 3.

- **Tanda 1**: 7 esquemas de contrato, núcleo `core/`, catálogo en fragmentos por módulo.
- **Tanda 2**: `modules/<m>/{main,lib,lib_aux}` y `pipeline/`, prueba del grafo de dependencias.
- **Tanda 3**: ciclo `zoning` ↔ `space_layout` roto, interfaz pública del sitio, `run_capacity` delgado,
  `visualize.py` repartido, cero excepciones al grafo.
- **Tanda 4 (cierre)**: contratos ejecutables y encadenados, CLI por módulo, pruebas por módulo con contratos fijos,
  puentes y catálogo original eliminados, documentación generada.

**Contratos ejecutables (0.2.0).** `core/lib/contracts.py` (`make_contract`, `read_contract`, `package_json`,
`plain_json`); cada productor tiene `modules/<m>/main/contract.py` con `to_contract` / `from_contract`, ambos
validan contra el esquema. `run_capacity_contracts(brief)` devuelve `(paquete, contratos)`: el paquete se arma
**solo** desde `program`, `lot_capacity`, `site_plan` y `zoning_scheme` (`pipeline/lib/package.py`), el costo
lee esos contratos como JSON (`cost_from_contracts`, sin importar código de lotcap, site ni household) y las
figuras de `capacity` se dibujan desde los contratos (`viz/main/run_viz.py`).

**CLI por módulo.** `spaceplan lotcap|site|zoning BRIEF -o C.json`, `spaceplan household BRIEF.json --contract
P.json`, `spaceplan cost --lot-capacity .. --site-plan .. --program .. [--brief] [--budget]`, `spaceplan viz
--lot-capacity .. --site-plan .. --zoning-scheme .. --capacity-plot|--site-plot|--zoning-plot PNG [--area-matrix AM
--sheets DIR]`, `--contract` en `profiles` y `areas`, `spaceplan capacity BRIEF --contracts DIR`. Los comandos
anteriores no cambian.

**Pruebas por módulo.** `tests/<módulo>/` (core, lotcap, site, household, cost, profiles, zoning, areas, viz,
pipeline) con contratos fijos en `tests/<módulo>/fixtures/` (14, generados por `tools/make_fixtures.py`, que solo
escribe si el paquete armado con ellos es idéntico a la instantánea). Cada módulo se prueba contra su contrato fijo
sin correr el pipeline completo y cada contrato se prueba con su consumidor. `docs/architecture/modules.md` se
genera desde el código (`tools/module_graph.py`) y una prueba falla si queda desactualizado.

**Pruebas y tiempos.** 1,026 pruebas (1,107 al cierre de la tanda 3; la baja son pruebas de los puentes eliminados,
detalle en `docs/refactor/log/tanda-4.md`). Suite completa ≈ 11 min 17 s corriendo las carpetas en serie (antes
≈ 9 min de reloj, ≈ 11 min sumando tandas de archivos); por módulo: core 1 min 32 s · lotcap 1 min 55 s · site
1 min 6 s · household 3 min 46 s · cost 14 s · profiles 43 s · zoning 1 min 9 s · areas 15 s · viz 3 s · pipeline
32 s. Golden check ≈ 2 min 36 s.

**Decisiones de diseño (para revisar).**
1. `to_contract` / `from_contract` viven en `main/` de cada módulo (`lotcap` necesita `LotSetup`, que es de `main`).
2. `site` y `zoning` siguen recibiendo objetos geométricos en memoria de `lotcap`; sus comandos corren los módulos
   previos. Rehidratar la geometría desde `lot_capacity` es el paso siguiente natural.
3. Serialización como el paquete (4 decimales en lote, sitio, zonificación y revisión; hogar y costo tal cual). Un
   módulo que lee un contrato redondeado puede moverse en el último decimal (el patio leyendo la zonificación:
   < 0.01 sq ft); el pipeline evita ese camino para no cambiar resultados.
4. Conflicto de nombres en la CLI: `household`, `profiles` y `areas` ya existían; escriben su contrato con
   `--contract` en vez de un subcomando nuevo.
5. El catálogo original se eliminó; su SHA-256 queda fijado en `tests/core/test_catalog_fragments.py`.

**Cómo agregar un módulo** (p. ej. `stacking` para el paso 6.7): ver la última sección de
`docs/architecture/modules.md` (estructura, grafo permitido, esquema y `contract.py`, composición en `pipeline`,
CLI, pruebas con contratos fijos, regenerar el documento).

## 4j. Paso 6.7a, etapa S0 (9 oct 2026): módulo `stacking` — niveles y presupuesto de altura

**Qué hace.** Toma las celdas ganadoras de 6.6 (`area_matrix`, por defecto rango ≤ 2 por lote, hogar y perfil) y la
`lot_capacity` de cada lote, y para cada celda arma los **niveles respecto del terreno** (0 planta baja, +1 planta
alta; −1 sótano en 6.7b) con sus propiedades por regla (cuenta en FAR, es piso, cuenta en IO) y revisa la **altura**
por tipo de techo contra el plano envolvente de 131.0444. No dibuja nada: es aritmética (S0). Marca `next_stage = S1`
en las celdas de dos pisos que siguen (escalera, polígono por nivel, contención: etapa S1).

**Paso 0 (verificación normativa en el texto oficial del SDMC).** Reglas nuevas en un conjunto aparte,
`data/rules/sdmc_rs_1_7_vertical.json` (0.1.0), para no tocar el conjunto de capacidad ni los paquetes dorados:
V01 geometría del plano (131.0444(a)(b)(c): conecta la altura máxima junto al retiro con la altura máxima total;
45° desde la vertical en lotes < 75 ft; frontal solo sobre 27 ft) — **lectura provisional**: 24 ft en la línea del
retiro lateral subiendo a 30 ft (el 24 solo aparece en el Diagrama 131-04L); V02 medición de altura (113.0270:
terreno más bajo entre existente y propuesto; altura total + diferencia de cota hasta 10 ft), V03 sótano en el FAR
(113.0234(a)(2): cuenta si el piso superior está > 3 ft 6 in sobre el terreno, o > 5 ft con pendiente ≥ 5 %),
V04 pisos (113.0261: primer piso ≤ 2 ft 6 in; sótano es piso con ≥ 6 ft), V05 garaje en el FAR (113.0234(a)(6) y
(d)(3)(A)(i): **el garaje de vivienda unifamiliar sí cuenta**, confirma la lectura por defecto de 6.6). V02–V05
`verified: true`. Parámetros de diseño en `data/catalog/stacking_catalog.json` (0.1.0, todos `provisional`):
entrepiso 10 ft, planta baja 1 ft sobre terreno, placa 9 ft, techos plano (pretil 2 ft) e inclinado 4:12 (por
defecto), modos de selección, sondeo de sótano.

**Arquitectura.** `modules/stacking/{main: run_stacking, contract; lib: stacking_catalog, vertical_rules, levels,
height_check, cell_selection, lot_vertical; lib_aux: vertical_geometry}`. En S0 solo importa `core` (lee contratos);
`ALLOWED` le reserva `lotcap, site, cost, zoning, areas` para S1/S2. Composición en `pipeline/main/run_modules.py`
(`stack_plan_contract_for`, y `lot_capacity_contract_for`: capa 0 sola, mismo contrato que el flujo completo).
CLI: `spaceplan stacking [LOTES] [--households ..] [--cells best|top2|all] [--area-matrix AM --lot-capacity LC ..]
[-o stack_plan.json] [--tables DIR]` (piloto completo ≈ 1 min). Contrato fijo
`tests/stacking/fixtures/stack_plan_interior_50x100_empty_nest_anglo.json`; 47 pruebas nuevas.

**Resultados del piloto (10 lotes × 21 hogares, top2: 1,977 celdas, 1,108 de dos pisos).**
1. **La altura nunca impide dos pisos**: 0 celdas exceden; con techo inclinado la cumbrera de dos pisos queda entre
   21.4 y 25.8 ft (holgura mínima 4.2 ft bajo 30 ft). Tres pisos no caben por altura en ningún lote (131.0460 no
   aplica en el piloto).
2. **El plano 131.0444 solo manda en 67 celdas (6 %)** y siempre por el **hastial hacia el lindero lateral** (planta
   alta más ancha que profunda): retranqueo de 0.3–1.8 ft (media 0.7). Con techo plano o la cumbrera girada todas
   quedan dentro del plano: es una decisión de orientación del techo, no un límite de capacidad. Casi todas son
   máximos (47) y esquema V1 (58).
3. El plano frontal (sobre 27 ft) nunca se activa.
4. Sótano (sondeo): en los lotes planos un semisótano con el piso superior a 4.5 ft cuenta en el FAR sin ser piso;
   en la ladera (pendiente media 28 %) hasta 5 ft queda fuera del FAR: la regla ya favorece el walkout (H2 de 6.7b).

**Limitaciones de S0.** Plantas como rectángulos (ancho de la estrategia; la alta, escalada); la pendiente es la media
del lote (113.0234 la pide por borde); el inicio del plano en 24 ft es lectura del diagrama; techo y entrepiso son
hipótesis.

## 4k. Paso 6.7a, etapa S1 (9 oct 2026): plantas dibujadas, escalera como objeto y techo contra 131.0444

**Qué hace.** Para cada celda de dos pisos que S0 marcó `next_stage = S1`: planta baja = franja frontal del polígono
realizable de la estrategia con el área bruta de la planta baja; garaje provisional en la línea frontal (área =
IC − IC sin garaje, × base del FAR; si la planta es poco profunda se ensancha); planta alta = franja trasera o
delantera de la planta baja, o rectángulo anclado al garaje (V4 lo prueba primero), contenida por construcción;
**escalera** del CRC (R311.7) en la **junta** (borde de la planta alta que no está en el perímetro de la baja), mismo
rectángulo en ambos niveles y fuera del garaje; polígono permitido por nivel (envolvente menos el plano a la altura del
muro); **techo de la planta alta real** contra 131.0444 (por defecto, cumbrera girada, plano); cuarto sobre garaje con
la nota R302.6 (cielo raso Type X). Celda dibujada → `next_stage = S2`.

**Datos.** Reglas nuevas `data/rules/crc_2025_stairs.json` (S01–S06, todas `verified: false`: contrahuella ≤ 7¾ in,
huella ≥ 10 in, ancho ≥ 36 in, altura libre ≥ 6 ft 8 in, descanso ≥ 36 in, separación garaje–vivienda). Catálogo de
apilamiento 0.2.0: diseño de escalera en los mínimos, tipos recta/U/L, posiciones de la planta alta, garaje
provisional, política de techo, modo por etapa (S1 usa `best` por defecto). Contrato `stack_plan`: bloque opcional
`s1` por celda y `plan` por lote (aditivo dentro de 0.2.0); S0 no cambia (solo versión y hash del catálogo en el
fixture).

**Arquitectura.** `lib`: `stair_rules`, `lot_plan`, `plan_levels`, `stair`, `roof_plane`, `cell_geometry`;
`lib_aux`: `plan_geometry`; `viz/lib/stack_plan_plots` (hojas de plantas apiladas desde el contrato). Solo lee
contratos. CLI: `spaceplan stacking --stage S1 [--cells best|top2|all] [--tables DIR] [--plans DIR]` (piloto ≈ 25 s
con contratos en disco). 29 pruebas nuevas.

**Resultados del piloto (top2, 1,108 celdas de dos pisos).**
1. **Todas se dibujan**: escalera recta en la junta en el 100 %; 46.5 sq ft por piso contra 60 del catálogo
   (6.6 sobrestimó la escalera en 13.5 sq ft por piso). *Corregido en S1.1 (sección 4l): S1 elegía por orden, no
   por comparación; "U y L nunca hicieron falta" era efecto del orden.*
2. **Plano 131.0444 con la planta alta real**: 44 celdas lo activan con el techo por defecto (S0: 67). 51 de las
   de S0 quedan libres y aparecen 28 nuevas: la planta alta real es una franja ancha y poco profunda, el techo gira y
   el hastial queda hacia el lindero lateral. **Las 44 se resuelven girando la cumbrera** (ninguna necesita techo plano
   ni retranqueo). Todas son perfiles máximos (V1 42, V5 2); retranqueo evitado 0.03–1.57 ft.
3. **Cuarto sobre garaje en 653 celdas (59 %)**: las plantas bajas son anchas y poco profundas (mediana 42 × 36 ft),
   la franja trasera alcanza el garaje → R302.6 (Type X) es la regla CRC más frecuente del piso alto. V4 se ubica sobre
   el garaje en 29 de 55 celdas.
4. El garaje se ensancha por falta de fondo en 125 celdas; la planta alta mide en mediana 0.37 de la baja.

**Limitaciones de S1.** Garaje provisional a la derecha (el lado de la entrada vehicular no está en los contratos);
planta baja = franja de ancho completo (sin la variante con cuarto de equipos del sitio); techo sobre el rectángulo
envolvente de la planta alta; reglas CRC sin verificar; la junta reemplaza a la circulación zonificada (S2).

## 4l. Paso 6.7a, corrección S1.1 (9 oct 2026): configuraciones de escalera, espacio bajo ella, llegada y arranque

**Por qué.** S1 elegía la escalera por orden (recta primero), no tenía recta con descanso intermedio, cobraba la huella
entera en planta baja sin recuperar el espacio de abajo y no definía la dirección ni qué espacio recibe cada extremo
(nada impedía llegar a un dormitorio). Plan y decisiones del cliente: `spaceplan_6_7a_S1_1_plan.md` (proyecto).

**Reglas.** CRC 0.2.0 (sin verificar): S07 tramo ≤ 151 in, S08 puerta en el tope, S09 protección bajo escalera ½ in,
S10 holguras de inodoro, S11 altura 6'8" sobre aparatos. **Reglas de cliente** en archivo aparte
`data/rules/client_stair_rules.json` (`kind: client`): K01 llegada a pasillo, vestíbulo en casa pequeña o family room
como máximo, nunca a cuartos; K02 arranque A vestibulado, B sala, C cocina (siempre disponible); K03 bajo escalera hacia
la cocina = solo almacenamiento; K04 medio baño siempre vestibulado; K05 extensión de la matriz D/I/N para S2.

**Qué hace.** Cuatro configuraciones (recta, recta con descanso, L, U; L compensada registrada como futura) en todas sus
direcciones y lados sobre la junta; válidas si la huella cabe en ambas plantas fuera del garaje y caben las zonas de
llegada (abajo descanso × ancho en planta baja; arriba pasillo 3 × 3.5 ft o vestíbulo 4 × 4 ft en la planta alta).
Altura libre bajo la escalera = línea de nariz − estructura (10 in): franjas < 4 ft, almacenamiento, ≥ 6'8" (medio
baño, extensible hasta 3 ft más allá del extremo, con vestíbulo de 3 × 3 ft). Elección lexicográfica: costo neto en
planta baja, medio baño, arranque cerca de la entrada, centro de la junta. Salida: bloque **`stair_core`** fijo para S2
(huella, extremos con zona y espacios receptores, bajo escalera con uso por opción de arranque, alternativas por
configuración, extensión D/I/N) y **`rule_traces`** (normativa vs cliente). Planta alta **compacta** (rectángulo atrás,
≥ 12 ft de fondo) para plantas altas pequeñas. Catálogo de apilamiento 0.3.0. 13 pruebas nuevas (S1.1).

**Resultados del piloto (top2, 1,108 celdas).**
1. **Las 1,108 se dibujan con escalera, llegada y arranque válidos** (6 en el lote bandera solo con la planta alta
   compacta: la franja de ancho completo medía 62 × 3 ft).
2. **El costo neto en planta baja es igual en las cuatro configuraciones: 16.8 sq ft** (la cuña baja del primer tramo,
   < 4 ft). Lo demás se recupera como almacenamiento o medio baño. Contra los 60 sq ft de 6.6, la planta baja tiene
   ≈ 43 sq ft más de lo calculado.
3. Elegidas: L 787, recta con descanso 225, recta 71, U 25. La L gana porque el arranque queda más cerca de la entrada
   (mediana 19.5 ft desde el frente).
4. **Medio baño vestibulado bajo la escalera en el 100 %** de las elegidas (extensión 2.7 ft). En las 25 en U el espacio
   de abajo abre junto al arranque: si se arranca desde la cocina (opción C) pasa a almacenamiento (K03).
5. **Llegada a vestíbulo en 768 celdas (69 %)**: la planta alta sirve a ≤ 2 cuartos (umbral provisional del catálogo).
6. Trazas: normativas todas pasan; de cliente K01, K02 y K04 quedan diferidas a S2 (el espacio receptor se asigna al
   zonificar); K03 se aplica en 25.

**Limitaciones.** El tiempo del piloto subió a ≈ 8 min (top2); espacios receptores no asignados hasta S2; el lado del
garaje sigue provisional; el umbral de "casa pequeña" no lo fijó el cliente.

## 4m. Lógica de áreas con las variables de diseño del cliente (9 oct 2026): FOS, FOT, un piso primero, sensibilidad

**Decisiones del cliente.** (1) FOS de diseño 0.60 sobre la **envolvente** (área dentro de los retiros); cuenta interior
y garaje, no deck ni jardín (SDMC 113.0240). En RS-1-7 el SDMC no fija ocupación salvo ladera empinada (131.0445(a)):
el FOS es una variable de diseño. (2) FOT: por defecto **SDMC 131.0446 (Tabla 131-04J)**; un FOT fijo (0.85, valor de
zonas RT) es un **escenario** editable y queda marcado como no normativo. (3) **Un piso primero**: el segundo piso solo
si el programa no cabe en un piso dentro de la huella y el FOT lo permite. (4) Mínimo del **lote** (casa básica de un
dormitorio, tipología `h1_basic`) y mínimo del **hogar**; óptimo = el mayor programa de la curva que cabe en un piso
dentro de la huella (el codo queda como lente); máximo = 100 % del FOT efectivo (o pisos por altura × huella).
(5) Escalera: 44 sq ft por piso en el FAR (catálogo 0.12.0). (6) Casa pequeña = 1 cuarto arriba. Investigación:
`spaceplan_FOS_investigacion.md` y `spaceplan_FOT_investigacion.md` (proyecto).

**Datos y código.** `data/rules/client_design_variables.json` (D01 FOS, D02 FOT, D03 pisos, D04 perfiles; editables, y
por corrida con `--fos`, `--fos-base`, `--fot-source`, `--fot`, `--floors-policy`, `--optimum-policy`; `--legacy-areas`
reproduce 6.6). `core/lib/design_variables.py` (carga, validación, `design_limits` con el límite que manda).
`areas`: presupuesto con huella de diseño y FOT efectivo, estado `exceeds_design_footprint`, política de pisos en el
ranking (`policy_excluded`), `lib/lot_minimum.py`, `lib/sensitivity.py`. `profiles`: óptimo "footprint".
`pipeline/main/run_sensitivity.py` + CLI `spaceplan sensitivity` + `viz/lib/sensitivity_plots.py`. Golden y fixtures
congelados de nuevo con informe: `docs/refactor/log/golden_refresh_2026-10-09_area_logic.md`. 17 pruebas nuevas.

**Resultados del piloto.**
1. Huella de diseño 1,777–2,246 sq ft (0.36–0.39 del lote); FOT del SDMC 2,850–3,540 sq ft; mínimo del lote 808 sq ft.
2. Mejores de dos pisos: **245** (antes 519): máximos 140, accesibles 81, por etapas 24; **todos los óptimos son de un
   piso**. S1.1 dibuja las 371 de dos pisos de top2; la llegada es a pasillo en el 78 %.
3. **El máximo no tiene celda factible en 64 de 210 hogares**: el reparto por esquema deja la planta baja sobre la huella.
   Hace falta un reparto equilibrado (paso 9, QP).
4. Escenario FOT 0.85: **no agrega casas de dos pisos (229) y empeora el máximo (85 sin celda)**; manda el FOS con el
   reparto, no el FOT.
5. Sensibilidad (`spaceplan sensitivity`, 5 s): con FOS 0.60 casi ningún programa completo cabe en un piso en lotes
   rectangulares; con el FOT del SDMC entre 5 % y 43 % no cabe ni en dos pisos (el lote poco profundo, el peor); en FOT
   altos manda la altura (2 pisos × huella).

**Limitaciones.** El reparto por esquema no equilibra los pisos; la demanda de la sensibilidad es el programa completo
sin techo; el caso de los áticos ≥ 5 ft (113.0234) y la condición de desnivel de la ladera empinada quedan por verificar.

## 4n. Paso 9a (10 oct 2026): reparto balanceado entre pisos y máximo recortado

**Problema.** Con un piso primero, 64 de 210 máximos quedaban sin esquema viable. El área total sí cabía bajo el FOT; lo que no cabía era la planta baja dentro de la huella de diseño (FOS 0.6 × envolvente), porque V1–V5 asignan grupos fijos sin mirar áreas. Subir el FOT no ayuda: no es el límite que falla.

**Solución (catálogo 0.13.0, regla del cliente `vertical_schemes.ground_balance`, VB01).**
- `areas/lib/floor_balance.py`: `balance_split` sube espacios uno a uno en el orden del catálogo (family room → study → flex room → storage) hasta que la planta baja entra en la huella. Nunca sube garaje, cocina, sala, comedor, foyer, mudroom ni medio baño. Respeta `floor_preference` y los grupos cohesivos, los espacios alojados siguen a su anfitrión y la planta alta nunca supera a la baja. Cada movimiento queda en `exceptions` (`kind: ground_balance`) y en la celda como `balanced_up`.
- Máximo recortado: `profile_programs(..., maximum_fits=...)` retrocede por la curva de expansión hasta el último paso cuyo programa tiene un reparto en dos pisos que cabe (`two_floor_fits`); si ninguno cabe, el máximo es el mayor programa de un piso dentro de la huella (`one_floor_fits`). Gobierna `design_footprint_ground` y la celda lleva `maximum_trim`.
- `vertical_split.build_split` (cola de `split_program`) y `space_matches` quedan públicos.
- Sensibilidad: clase nueva `split_fails` (el área cabe en dos pisos pero la planta baja mínima balanceada, `min_ground`, no cabe en la huella). Umbral nuevo `fos_for_every_split`. La figura derecha suma `exceeds + split_fails`.

**Resultado del piloto.** Máximos sin esquema: 64 → 18. Los 18 son todos del lote fan-curve-35-80x100 por `site_fails`. Ningún máximo queda inviable por la huella de diseño. 42 se resuelven subiendo el family room y 12 se recortan (empty nest con la suite abajo por movilidad). Mejores de dos pisos: 245 → 291. Óptimos: siguen todos en un piso.

**Diagnóstico de los `site_fails` (fan-curve).** Lo decide SDMC 131.0447, pavimento del antejardín ≤ 60 %. Con garaje de 2 autos, el acceso (300 sq ft) más el deck de entrada (60) sobre un antejardín curvo de 575.6 sq ft da 62.5 %. Sin el deck daría 52 % y pasaría. El resultado depende de la variante pendiente `deck_counts_as_paving` (conservadora). El garaje de 1 auto pasa (36 %).

**Pruebas.** `tests/areas/test_floor_balance.py` (9 pruebas). Golden congelado de nuevo con `docs/refactor/log/golden_refresh_2026-10-10_floor_balance.md`. 1,226 pruebas pasan.

## 4o. Paso 6.7a, etapa S2 (10 oct 2026): zonificación por planta alrededor del `stair_core`

**Decisiones del cliente (plan `spaceplan_6_7a_S2_plan.md`).** D1: `area_matrix` exporta por celda de dos pisos el
bloque `space_split` (cada espacio con piso, zona y área, tal como lo evaluó el reparto de 9a). D2: nivel de zonas,
receptores, circulación y medio baño; los espacios quedan para S2.1. D3: enumerador ligero dentro de `stacking`.
D4: K05 gana sobre la matriz base (`living–social_bath` D blanda → N dura; también `kitchen–` y `dining–social_bath`).
D5: las tres opciones de arranque A/B/C se guardan como portafolio.

**Qué hace.** Por celda con `s1.status == "drawn"`: unidades de zona por planta (halls prorrateados como en el
área; circulación ≥ `circulation.target_fraction` del piso; servicio pequeño fusionado; arriba, una zona con dos
cuartos habitables también se busca partida en dos, una a cada lado del hall); rejilla de 0.5 ft con sumas de prefijos;
topologías de 1–2 bandas × columnas en los ejes del catálogo; la unidad receptora se **ancla** sobre la zona de llegada de
la escalera (la columna se estira para cubrirla y las vecinas reparten el resto). Duras: ancho mínimo (lado mayor de
sus espacios), área ±25 %, llegada en una unidad, puertas por zona (lo privado solo abre a circulación) y alcance desde
la entrada o la llegada, garaje con puerta, entrada en la fachada frontal, K04 (vestíbulo del medio baño a circulación),
K01 (llegada: family room si está arriba, vestíbulo si ≤ 1 cuarto, si no hall), anclas del perfil casa, pares duros de la
matriz en el mismo piso. Puntaje: relaciones, forma, anclas, acceso a la escalera (con penalización si el tramo bordea
zona privada) y pares entre pisos medidos a través de la escalera. Planta baja: una búsqueda por uso del bajo escalera
(medio baño con vestíbulo, o almacenamiento con el medio baño reubicado en circulación). **Retroceso:** si la celda no se
zonifica, S2 pide a S1 redibujarla con otra colocación de la planta alta o con otra configuración de escalera
(`draw_cell(..., placements, stair_ids)`) y se queda con la primera que zonifica (`redrawn_by_s2`).

**Datos y código.** Catálogo de apilamiento 0.5.0 (bloque `s2`), reglas de cliente 0.2.0 (`precedence` en K05),
`area_matrix` con `space_split`, `stack_plan` con bloque `s2` (aditivo en 0.2.0; `next_stage` S2.1; trazas
`deferred_to_S2.1` y `not_evaluated`). `lib`: `floor_frame`, `core_zoning`, `zone_relations`, `zone_cell`;
`lib_aux`: `zone_grid`; `main/run_stacking`: `--stage S2`, `stage_s2`, `backtrack_order`, `stack_plan_s2.csv`;
`viz`: `plot_zoning_sheet`, `stack_zoning_sheets`. CLI: `spaceplan stacking --stage S2 [--cells top2] --tables out
--plans out` (best ≈ 3 min, top2 ≈ 4 min con contratos en disco). 17 pruebas nuevas (1,263 en total). Golden sin cambios; fixtures de
`area_matrix` y `stack_plan` renovados (`docs/refactor/log/golden_refresh_2026-10-10_stage_s2.md`).

**Resultados del piloto (top2, 460 celdas de dos pisos dibujadas).**
1. **393 zonificadas (85 %)**; máximos 257/276, por etapas 43/43, accesibles 93/141. En best: 261/291 (90 %).
2. Llegada: hall 284, family room 75, vestíbulo 34. **Las 69 celdas con el family room subido por 9a llegan al family
   room.** Arranque elegido A 358, B 35 (A inviable); factibles A 358, B 365, C 338: casi siempre hay portafolio.
3. Medio baño bajo la escalera 218, reubicado en circulación 175 (el vestíbulo no daba a la circulación).
4. **El retroceso a S1 rescató 180 celdas** (145 con otra escalera). Escaleras finales: recta 162, L 142, recta con
   descanso 63, U 26; colocación: atrás 269, sobre garaje 94, adelante 15, compacta 15.
5. **Las 67 que no zonifican son plantas altas pequeñas** (mediana 242 sq ft contra 768 de las zonificadas; 61 con
   llegada a vestíbulo, 48 accesibles): la escalera y su llegada no dejan un cuarto de 8 ft. Además, en 19 zonificadas la
   planta alta es menor que su programa (escala < 1): S1 dimensiona la planta alta con 44 sq ft de escalera y la L o la
   U ocupan más.
6. Entrada por la sala en 91 (la circulación no llega a la fachada frontal); par entre pisos más incumplido
   `D:kitchen–laundry` (30, lavandería arriba por cultura).

**Limitaciones.** Zonas rectangulares por columna (sin zonas en L); puertas, abatimientos y la posición del medio baño
reubicado quedan para S2.1; los pares N sin escalera (medio baño sin puerta directa a sala/cocina) y un clóset de
lavandería en el hall de llegada quedan `deferred_to_S2.1`; garaje provisional a la derecha; área ±25 % y demás valores
de diseño provisionales.

## 4p. Paso 6.7a, S1.2 (10 oct 2026): escalera desde la puerta principal, luz, U de 2.5 m, selector en tres niveles

**Rama:** `stacking/6.7a-s1.2-spike` (prueba corta y cierre; aún fuera del flujo `--stage S2`). Script de comparación:
`tools/spike_s1_2.py CONTRACTS OUT --cells best` (necesita `site_plan_<brief>.json` además de los contratos de áreas).

**Decisiones del cliente.** Entrada en 7 pasos: la fachada a la calle, la puerta sobre el deck del `site_plan` (abre
hacia dentro, bisagra al muro cercano), un vestíbulo de 5×5 ft, recorridos y escaleras U y L contra los muros
permitidos. Los muros permitidos son los laterales y el posterior que siguen arriba; la junta solo como último recurso.
Se descartan las interferencias; sin estructura por ahora. Estrategias: A muro lateral, D fachada posterior, C U con
vacío central, B centro. **Sin claraboya.** Luz en dos capas: S12 (R303.7, luz artificial, siempre) y K06 (ventana
según S13 / Tabla R302.1, sin verificar; obligatoria en A, C y D). K08: **U ≥ 2.5 m** de ancho total (afecta también a
S1). Llegada arriba (K01) y medio baño (K09) como **preferencias**. Regla de hall: la escalera toca la circulación al
menos un ancho de escalera; sala y cocina no pasan de la mitad de su borde; una sola zona privada no pasa de 3/4.
Selector en tres niveles: obligatorio → recorrido dentro de una tolerancia sobre el mejor → preferencias (estrategia,
llegada, medio baño).

**Código.** `lib/access_core.py`: puerta, giro, vestíbulo, muros, distancia de separación perpendicular y luz.
`lib/access_stair.py`: candidatas por estrategia con búsqueda en dos niveles, descartes, preselección y medio baño
posterior. `lib/access_rank.py`: selector. `lib/routes.py`: recorridos hasta el centro de cada zona. S2: vestíbulo y
vacío fijos, llegada por preferencia, regla de hall. `draw_cell(..., picker, garage_side)`. Catálogo 0.7.0 (bloque
`access_core`, escalera `u_well`), reglas de cliente 0.4.0 (K06–K09), CRC escaleras 0.3.0 (S12, S13). 13 pruebas
nuevas (T1–T8 y el hall); 1,291 pasan; golden sin cambios.

**Resultados (3 lotes, 100 celdas best; versión actual también con la regla de hall).** Zonificadas 76 → 96; con luz
0 → 58; mayor rectángulo libre PB 787 → 871 sq ft y PA 552 → 618; recorrido a sala, comedor, cocina y escalera
98.5 → 79.2 ft; puerta → arranque 6.5 → 3.0 ft; U 4 → 14. Con tolerancia 6 ft: A 27, D 26, C 5, B 38. **Simulación de
tolerancias:** 12 ft → A 49, B 22, luz 74; 20 ft → A 55, B 11, luz 85, recorrido +7 ft. ≈ 7 s por celda.

**Pendiente.** Fijar la tolerancia de recorrido (decisión del cliente); integrar S1.2 en `--stage S2` y correr los 10
lotes; bajar el tiempo (reutilizar la huella para todas las posiciones); verificar S13 (R302.1) y si el vacío cuenta
en el FAR; la estructura.

## 4q. Paso 6.7a, S1.2 integrada en el flujo (10 oct 2026): opción B, tolerancia 15 ft

**Rama:** `stacking/6.7a-s1.2`. `spaceplan stacking LOTES --stage S2 --site-plan SP.json ...` (sin `--site-plan` se
calcula desde los briefs). Comparación: `tools/compare_s12_baseline.py OUT stack_plan*.json` contra la línea base
congelada `docs/baselines/stack_plan_04bbba2` (S1.1 + retroceso de S2). Resultados: `docs/results/s12_pilot/`.

**Decisiones del cliente.** Opción B: se borran el selector por junta y el retroceso de S2; la línea base queda como
datos. Tolerancia de recorrido 15 ft. Piloto solo con celdas `best`.

**Código.** `lib/access_cell.py`: `stage_s1` junta las candidatas de todas las posiciones de la planta alta, preselecciona
por estrategia, busca el medio baño y dibuja la mejor por un proxy (marcada `provisional`); `stage_s2` dibuja y
zonifica cada preseleccionada y elige con `access_rank` (obligatorio → tolerancia 15 ft → preferencias); guarda
`stair_choice` (elegida, razón, Pareto, portafolio por estrategia, no zonificadas). `site_entry` toma la opción
seleccionada del `site_plan`, y sin opción trazada usa la puerta centrada. Catálogo 0.8.0; esquema con `access_core`,
`stair_choice` y `u_well`; láminas con puerta, vestíbulo, vacío y estrategia. 1,296 pruebas pasan.

**Resultados (10 lotes, 291 celdas best, mismas celdas que la línea base).** Zonificadas 261 → 279 (+22, −4: tres
`empty_nest` máximo en el trapecio y uno en el cul-de-sac, sin candidata zonificable). Escalera contra muro exterior
0 → 236; con luz natural (K06) 224. Medio baño bajo escalera 141 → 241. Mediana del mayor rectángulo libre (ambas
zonificadas): PB 770 → 851 sq ft, PA 468 → 648. Ocupación de la escalera 54.3 → 60.8 sq ft (U y L ocupan más).
Recorrido mediano 83 ft. Estrategias: A 123, D 100, B 55, C 1, sin elegir 12. B se concentra en lotes angostos o en
abanico (angosto 12, cul-de-sac 8, curva 7 —este sin `site_plan` trazado—, reverso 7). Tiempo ≈ 3.9 s por celda de
punta a punta (incluye matriz de áreas y S0), dos lotes en paralelo.

**Ajustes (S1.2b, 10 oct 2026).** La escalera elegida conserva las candidatas y descartes de S1. Recorrido en dos
plantas: un destino que está arriba (sala en la ladera, perfil accesible) se camina puerta → arranque + escalera
(huellas y descansos, sin factor de esfuerzo; decisión del cliente) + llegada → zona. `stair_choice.ranked` guarda
todas las candidatas zonificadas, para simular la tolerancia sin volver a zonificar
(`tools/simulate_tolerance.py`). Diagnóstico de no zonificadas: `tools/diagnose_unzoned.py`. 1,298 pruebas pasan.

**Hallazgos.** (1) B gana por recorrido, no por falta de alternativas: en 48 de 55 celdas había A, D o C zonificada,
entre 15.5 y 42 ft más larga (mediana 22). Simulación (279 celdas): 10 ft → B 78, luz 201; 15 → B 55, luz 224;
20 → B 39, luz 240; 25 → B 25, luz 254, recorrido mediano +3 ft; 30 → B 19, luz 260; 40 → B 12, luz 267.
(2) Las 12 no zonificadas son plantas altas pequeñas (175–255 sq ft: un cuarto y un baño) que S1 dibuja como franjas
de 5–8 ft de fondo a todo el ancho; A no tiene muro lateral que siga arriba y la regla de ancho falla en todas. Es un
problema de la forma de la planta alta en S1, no de la escalera.

**Cierre S1.2 (11 oct 2026).** Decisiones del cliente: tolerancia **25 ft**; planta alta en dos bandas para casas
pequeñas. Catálogo 0.9.0: `route_tolerance_ft` 25 y `upper_floor.small_house_placements: [compact_bands]` (rectángulo
atrás, centrado, de fondo = mayor lado mínimo de las habitaciones de arriba + mayor ancho de escalera; a lo ancho si
la planta baja es poco profunda). Resultado final (291 celdas): zonificadas 261 → **286**; escalera contra muro
exterior 0 → 259; con luz 254; A 149, D 103, C 2, B 32, sin elegir 5; medio baño bajo escalera 141 → 239; recorrido
mediano 86.5 ft (+3.2 ft de recorrido extra mediano por la tolerancia). `compact_bands` se eligió en 7 celdas.
Quedan 5 sin zonificar: perfiles accesibles de 175–255 sq ft arriba en lotes en abanico y angosto (ancho y área de
habitación). ≈ 4.5 s por celda de punta a punta. 1,299 pruebas pasan.

**Pendiente.** Las 5 celdas accesibles (¿planta alta más ancha o programa arriba distinto?); `site_plan` del lote en
curva; verificar S13 (R302.1) y si el vacío cuenta en el FAR; estructura; **S2.1**.

## 4r. Paso 6.7a, etapa S2.1 (11 oct 2026): espacios y puertas dentro de cada zona

**Rama:** `stacking/6.7a-s2.1` (desde `2a31c9a`). `spaceplan stacking LOTES --stage S2.1 [-o OUT.json] --tables T
--plans P` (por defecto celdas `best`; tablas `stack_plan_s21.csv`; láminas `<lote>_stack_spaces.png`). Resultados:
`docs/results/s21_pilot/`. Plan y decisiones: `spaceplan_6_7a_S2_1_plan.md` (proyecto).

**Decisiones del cliente (E1–E6).** E1 solo la candidata elegida, con retroceso por `stair_choice.ranked`; E2
rectángulos, los sobrantes como clóset o circulación; E3 puertas con posición, ancho, giro y bisagra; E4 R310 y C03 con
fachada como reglas duras; E5 clósets con los sobrantes; E6 los pendientes no bloqueantes quedan fuera.

**Qué hace.** Por planta: rejilla de S2 (0.5 ft) con los objetos fijos como nodos (vestíbulo de la puerta, escalera,
medio baño bajo la escalera y su vestíbulo, garaje). Cada unidad de zona de S2 se corta en rectángulos (guillotina de
tres niveles, cortes por área sobre la máscara de la unidad): sin pasillo, con el pasillo de circulación ya en un lado
(`edge:`), con una franja de pasillo en un lado o por el medio (`mid_x`/`mid_y`, carga doble, colocada donde toca la
circulación). Los cuartos se agrupan en suites (cuarto + clósets + baño en suite; el baño compartido solo o pegado a un
cuarto) y forman bandas perpendiculares al pasillo. Un clóset del programa puede integrarse a su cuarto
(`closets_in_rooms`). Poda local: lado y área mínimos (catálogo − tolerancia, nunca bajo C01/C06), fachada de habitables
(O03 vía C03) y de dormitorios (O01), el pasillo toca las unidades enlazadas, cada cuarto puede tener puerta, los pares
duros D de cuartos de paso tocan su unidad. Puertas: árbol de vanos entre espacios de paso desde la raíz (vestíbulo de
entrada abajo, escalera arriba), una puerta por cuarto (circulación > anfitrión/en suite > cuarto de paso), giro dentro del
espacio servido, nunca sobre escalera ni descanso (S08), sin cruzar otros giros; garaje nunca a dormitorio (O02, puerta de
cierre automático). Chequeos de planta: alcance, llegada K01/K02 en un espacio permitido, matriz D/I/N con K05 sobre el
grafo de puertas (cierra los `deferred_to_S2.1`). Si falla: siguientes zonificaciones de S2 en memoria
(`s2_alternatives` = 3) y luego la siguiente escalera de `ranked` (hasta 4).

**Datos y código.** Catálogo de apilamiento 0.10.0 (bloque `s21`; `selection.stage_default_modes.S2.1 = best`); ruleset
nuevo `crc_2025_openings.json` 0.1.0 (O01 R310, O02 R302.5.1, O03 R303.1; `verified: false`); esquema `stack_plan` con
bloque `s21` y etapa `S2.1`. `lib`: `space_rules`, `unit_frame`, `unit_layout`, `door_placement`, `space_relations`,
`space_cell`; `lib_aux`: `space_grid`; `access_cell.stage_s2(..., refine, max_tries)`; `zone_cell` guarda alternativas en
memoria; `viz`: `plot_space_sheet`, `stack_space_sheets`. 15 pruebas nuevas más los casos de arquitectura de los módulos nuevos (1,342 en total). Golden sin cambios; fixture
de `stack_plan` renovado (`docs/refactor/log/golden_refresh_2026-10-11_stage_s21.md`).

**Resultados del piloto (10 lotes, 291 celdas best; S2 zonifica 286).**
1. **135 celdas con planta completa (47 %)**: máximo 110/186, accesible 17/81, por etapas 8/24. Por lote: angosto
   23/33, reverso 16/25, esquina 16/33, trapecio 16/30, ladera 15/36, interior 13/36, poco profundo 13/30, bandera 11/28,
   cul-de-sac 7/27, curva 5/8.
2. Retroceso: 93 con la escalera elegida, 42 con otra de `ranked` (16, 18 y 8 en los rangos 1–3); 44 usan otra
   zonificación de S2. Estrategias finales A 73, D 35, B 23, C 4.
3. Mediana de 23 puertas por casa; 211 clósets integrados a su cuarto; 3 clósets de sobrantes; profundidad mediana de la
   suite desde la entrada: 6 puertas; circulación mediana de la planta alta 21 % (umbral de alerta del catálogo 20 %).
4. **151 sin planta**: falla la planta baja en 91 y la alta en 60. Primeras violaciones: unidades que no admiten un
   corte válido (social 33, privada 22, cocina 13), mudroom sin paso (10), pasillo que no alcanza las unidades enlazadas
   (10), baño privado en la llegada (K05, 9), pares D cocina–lavandería (6) y comedor–cocina (5), cocina sin fachada
   (O03, 4).

**Hallazgos.** (1) La zonificación de S2 no reserva el pasillo interior de la zona privada: S2.1 lo toma del área de los
cuartos y los deja bajo su mínimo. (2) Las unidades sociales delgadas (estudio y flex en 7.5 ft) solo tocan la
circulación en un extremo y no admiten un segundo cuarto. (3) El perfil accesible es el más afectado (pasillos de 4 ft,
puertas de 34 in). (4) La cocina sin fachada es una consecuencia directa de E4; la excepción de R303.1 está prevista en
los datos (`artificial_light_exception`) y es decisión del cliente. (5) La violación reportada es la más frecuente entre
las opciones descartadas; para diagnóstico conviene la "más profunda".

**Pendiente (S2.1b).** Zonificación de S2 consciente del pasillo (reservar la franja de la zona privada en el objetivo de
área, o ajustar el límite circulación–privada en S2.1); mudroom como paso entre garaje y cocina; diagnóstico por regla;
tiempo (≈ 12 s por celda con retrocesos). Siguen fuera: las 5 celdas accesibles de S1.2, `site_plan` del lote en curva,
S13/FAR, estructura.

## 4s. Paso 6.7a, S2.1b (11 oct 2026): puertas, baños por dormitorio, salida al patio, voladizo y antejardín

**Decisiones del cliente.** (1) Corredizas en clósets; corrediza de vidrio, más ancha, del comedor o la cocina (o la
sala) al deck, cuyo vidrio cuenta para la luz. (2) Baño compartido entre las dos recámaras, entrado desde la
circulación; arriba no hay medio baño. (3) K10: primero baño privado y walk-in del master, luego un baño por dormitorio
mientras el FAR alcance; el ajuste del programa va en `stacking` (sin tocar el golden). (4) Salida al patio comedor >
cocina > lavandería/mudroom, posterior o lateral. (5) Voladizo de 6 ft. (6) Puerta principal (típica de las casas tract
de San Diego: una hoja de 36" × 80" con panel lateral fijo, metida bajo el alero, deck cubierto para esperar; R311.2 y
R311.3) distinta de la secundaria (patio). (7) Antejardín con la norma (Z10, Z11) que muestra circulación y jardín.
Conectividad al 100 % como invariante.

**Código.** `lib/program_adjust.py` (asignación por FAR antes de S0: reserva de pasillo de la zona privada como parte
de su objetivo, master primero, baño por dormitorio, en suite o compartido con `shared_by`); `floor_frame` (la reserva
entra al objetivo de la zona; el baño compartido y sus recámaras quedan juntos al partir la zona); `plan_levels`
(`cantilever_rear`) y `cell_geometry` (`S1Context.cantilever_ft`, solo en la etapa S2.1); `door_placement`
(corredizas, bisagra en esquina real `_supported`, K10 en las reglas de puerta, `place_patio_exit` con rellano, S13 y
deck trasero); `unit_layout` (grupo recámara | baño compartido | recámara sobre el pasillo); `lib/front_yard.py`
(entrada vehicular, deck de entrada, sendero, jardín, puerta principal con panel lateral, Z10 / Z11 / O04 / O05);
`space_cell` (bloques `site`, `k10`, `patio_exit`, trazas); `viz` (antejardín, corredizas, vanos punteados).
Catálogo 0.11.0 (tipos de puerta, `exits`, `program`, `upper_floor.cantilever`), reglas de aberturas 0.2.0 (O04 R311.2,
O05 R311.3), reglas de cliente 0.5.0 (K10). 12 pruebas nuevas.

**Piloto (10 lotes, 291 celdas best).** S2 zonifica 281 (antes 286: el programa ajustado cambia S1/S2 en 5 celdas).
**126 casas con planta completa (45 %; S2.1 v1: 135)** — máximo 101/186, accesible 16/81, por etapas 9/24. En todas:
0 espacios sin acceso; 0 de 1,150 hojas abatibles al aire (antes 332 de 1,653); 430 clósets con corrediza; salida al
patio en el 100 % (comedor 102, cocina 11, sala-comedor 11, mudroom 2; posterior 77, lateral 49; sobre el deck del
`site_plan` 6); Z10, Z11, O04 y O05 aprobados en todas; K10: 265 baños en suite y 19 compartidos entre dos recámaras;
mediana de 56 sq ft agregados por celda dentro del FAR. El voladizo no ganó en ninguna celda (las otras colocaciones
siempre caben). Fallan más las plantas bajas (102 contra 53 altas): unidades sociales y de cocina sin corte válido
(37 y 16), pasillo que no alcanza las unidades (16).

**Pendiente.** Zonificación de S2 con la salida al patio y las puertas en esquina (hoy las descubre S2.1); el deck
trasero del `site_plan` frente a la salida (solo 6 coinciden); baños en franja larga (la forma se puntúa, no se
prohíbe); voladizo como forma preferida cuando ahorra área en planta baja; tiempo ≈ 12 s por celda.

## 4t. Paso 6.7a, S2.2a (11 oct 2026): registro de parámetros de diseño, perfil del cliente, herramientas para LLM y KPIs de calidad

**Origen.** El cliente vio espacios alargados y distribuciones incorrectas. El análisis
(`claude/spaceplan_6_7a_S2_1c_formas_analisis.md`) mostró que la forma no se castiga por debajo de 3:1 (el 3:1 sale
de `zoning.max_aspect_ratio`), que área objetivo + lado mínimo empujan a la franja y que no había criterio de
mobiliario. El cliente aprobó S2.2 completo en 6 pasos (`claude/spaceplan_6_7a_S2_2_calidad_espacios_plan.md`):
a registro y KPIs; b forma y mobiliario; c planta abierta y bandas de servicio; d circulación y puertas; e luz y
ventilación; f integración. Decisiones: planta abierta (great room) como base del perfil anglo/San Diego, separada
como alternativa, y la cocina latina cerrada si su tipología lo pide; walk-in y baños de la planta alta con luz y
ventilación mecánica permitidas; **no** se mueve el calendario (6.7b sigue en ene 2027, 6.8 en feb 2027), así que S2.2
cierra en dic 2026.

**Datos (todo `verified: false`, valores de diseño, no código).**
- `data/rules/design_space_standards.json`: 25 tipos con medidas típicas, proporción preferida/máxima, lado máximo,
  rectángulo de mobiliario, plantillas (cocina L/U/galley/isla con holguras NKBA; baño en línea / doble lavabo),
  cama de referencia, mesa del comedor; `great_room` (aún no es tipo del catálogo; S2.2c).
- `design_circulation_doors.json` (P01–P06: forma del pasillo, holguras NKBA 2, conflictos de giro, privacidad,
  recorridos, sintaxis espacial con peso 0).
- `design_light_ventilation.json` (L01 categorías N/P/M por tipo con `__upper`, L02 prioridad de fachada con
  recámaras primero, L03 luz diurna 2.5 × dintel, L04 ventilación de una cara / cruzada).
- `crc_2025_openings.json` 0.3.0: O06 baño R303.3 (3 sq ft o 50/20 cfm), O07 ventilación de toda la casa
  (150.0(o), ASHRAE 62.2).
- `data/design/registry_refs.json`: 123 parámetros existentes por referencia (áreas y lados del catálogo, ancho del
  pasillo, fracción de circulación, pesos y tolerancias de S2.1, voladizo, salida al patio, puertas, FOS, política de
  pisos, K10) y 51 restricciones (mín ≤ objetivo ≤ máx, preferida ≤ máxima…).

**Módulo nuevo `design`** (`core` solo; `stacking` lo puede leer):
- `lib/design_registry.py`: 368 parámetros (id estable, valor, tipo, unidad, kind, quién, rango/opciones, piso
  normativo convertido a la unidad, fuente); `check_value`, `check_constraints`, `self_check`, `materialize`.
- `lib/design_profile.py`: perfil del cliente (cambios con autor, fecha y motivo; la línea base nunca se edita);
  `propose`, `apply` (todo o nada), `diff`, `snapshot`, `check_profile`.
- `lib/llm_tools.py`: 7 herramientas en JSON Schema (`list_parameters`, `explain_parameter`, `propose_change`,
  `apply_changes`, `diff_profile`, `run_variant` y `compare_variants` para S2.2f) y `dispatch` local; publicado en
  `data/schemas/design_tools.json`.
- `lib_aux/param_paths.py`, `lib_aux/units.py`; `main/run_design.py` (`spaceplan design list|explain|propose|apply|
  diff|check|tools|materialize`), `main/contract.py` (contrato nuevo `design_profile`, perfil base en
  `data/design/profiles/baseline.json`).
- `stacking/lib/space_quality.py` + `main/run_quality.py` (`spaceplan quality <stack_plan...> --profile --out`).

**Medición «antes» (piloto S2.1b, 126 casas; `docs/results/s22a_baseline/`).** 59.7 % de espacios sobre la proporción
preferida y 41 % sobre la máxima; 14.6 % bajo el lado mínimo del catálogo (por la tolerancia del 15 %); 36.7 % sin
lugar para el mobiliario; 83 espacios partidos en piezas (32 pasillos, 24 foyers, 5 baños, 1 recámara); 267 pasillos
y foyers no rectangulares; circulación 17.7 % por planta (meta 15 %); tramo de pasillo 24.5 ft; 27.7 % de espacios N
más hondos que la profundidad de luz; 630 espacios M ocupan 4,815 ft de fachada. Por tipo: baño 5 × 11.5 (75.9 %
sobre la preferida, 58.2 % > 2:1 como en el análisis), comedor 8.5 × 20 (57.5 % sin mesa de 6), foyer 100 % no
rectangular, despensa y desayunador sin su mobiliario (85.7 % y 87.1 %).

**Pruebas.** `tests/design/test_design_registry.py` (19) y `tests/stacking/test_space_quality.py` (7); arquitectura con
el módulo `design`; `module_graph` regenerado; golden sin cambios.

**Pendiente (siguientes pasos).** S2.2b usa el registro en S2.1 (puntaje de forma por tipo y del peor espacio,
mobiliario, lado mínimo sin tolerancia en habitables) y concilia catálogo y estándares (despensa, desayunador). S2.2c
crea `great_room` y las bandas de servicio; S2.2d puertas y circulación; S2.2e luz y ventilación con la prioridad de
fachada; S2.2f conecta `run_variant` al pipeline y endurece reglas calibradas.

## 4u. Paso 6.7a, S2.2b (11–12 oct 2026): el registro de diseño dentro de S2.1 — perfil intermedio

**Decisiones del cliente.**
- Cama queen con 36 in a ambos lados y al pie (rectángulo de 11 × 10 ft).
- Los espacios chicos cubren todo el muro donde se apoyan; se agregan el clóset de blancos y el clóset de baño.
- Circulación e iluminación entran a los pesos.
- Un espacio = una pieza.
- Primero se pidió proporción y mobiliario duros en baños, comedor y cocina. Al medir el perfil estricto (8 de 291 casas) el cliente eligió el **perfil intermedio** (12 oct, 23:54):
  - **duros:** baños (proporción máxima, mobiliario, clóset de baño) y una pieza por espacio;
  - **preferencias fuertes** (puntaje): recámara de 11 × 10, clósets a muro completo, comedor y cocina, hasta que S2.2d dimensione las zonas para ellos.

**Datos.**
- `design_space_standards` 0.3.0:
  - `space.policy.*`: tolerancia habitable 0, peso del peor espacio, espacios chicos a su tamaño típico (tope 1.25), tipos de muro completo, una pieza (pasillos aparte, `one_piece_circulation` apagado hasta S2.2d);
  - `space.closets.*`: blancos, baño y recámara;
  - plantillas de cocina L/U/galley/isla con `templates_allowed`;
  - kinds según el perfil intermedio.
- Registro 0.2.0 (396 parámetros).
- Catálogo de apilamiento 0.12.0, pesos:
  - planta: relaciones .25, forma .15, mobiliario .10, circulación .15, luz .15, clósets .05, vertical .15;
  - unidad: forma .25, mobiliario .25, ajuste .10, circulación .15, luz .25.

**Código.**
- `space_rules`: `design_view(profile)`, `SpaceRules.design/design_kinds`, `std`, `hard`, `policy`, `closets`, `category`, `furniture_ft` (cocina: cualquier plantilla) y `furniture_hard`.
- `unit_frame`: sin tolerancia en el lado mínimo de habitables; el mobiliario duro fija el lado mínimo de los cortes.
- `unit_layout`:
  - pedazos sueltos al vecino con más muro (o al propio pasillo a través de la escalera);
  - `_cap_small` lleva los espacios chicos a su tamaño típico;
  - `_carve` talla el clóset de baño (toma el largo sobre la proporción preferida) y el de recámara, lejos de la fachada y de la puerta;
  - `_linen` pone el clóset de blancos al fondo del pasillo alto;
  - `_hard_shape` aplica la proporción y el mobiliario duros;
  - `_full_wall` / `_wall_misses` revisan el muro completo (duro o puntuado);
  - el puntaje nuevo: forma por tipo con el peor espacio, mobiliario (incluye muro completo), ajuste, circulación (pasillo rectangular y largo máximo), luz (profundidad de luz N, holgura de fachada, fachada ocupada por M, ventilación cruzada).
- `space_cell`: partes de planta con mobiliario y luz.
- `space_grid`: `fits_in_mask`, `exterior_cells`, `exposed_sides`, `shared_edge`.
- `run_stacking(..., design_profile)` y `spaceplan stacking --design-profile`; el meta registra la versión del registro y el perfil.
- `space_quality`: plantillas de cocina y clósets por rol.

**Piloto (10 lotes, 291 celdas; `docs/results/s22b_pilot/`).**

| Perfil | Casas | Sobre la proporción máxima | Sin mobiliario | Notas |
|---|---|---|---|---|
| Antes (S2.1b) | 126 | 41 % | 37 % | baño 5 × 11.5, comedor 8.5 × 20 |
| Estricto | 8 | 39 % | 23 % | baños, comedores y cocinas 100 % en rango |
| **Intermedio (línea base)** | **43** | **26 %** | **19 %** | baño 5 × 8 y master 8 × 11 (100 % en rango), 49 clósets de baño, 19 de blancos, 34 de recámara; comedor 9 × 17 |
| Todo como preferencia (2 lotes) | 30 de 33 | 32 % | 30 % | |

- Bloqueos del intermedio:
  - zona privada sin corte válido (89): el baño master de 8 × 9 duro exige 8 ft en los cortes;
  - social sin corte (21);
  - baño sin alcance (18) o sin mobiliario (16).
- Por partes (lote esquina): ninguna regla sola explica la caída; las reglas se bloquean entre sí, porque las zonas de S2 no se dimensionaron para ellas.
- El cómputo pasó de ≈ 1 h a ≈ 1 h 15 min por piloto (dos procesos: 38 min).

**Pendiente.**
- S2.2c: planta abierta (great room) para la planta baja.
- S2.2d: S2 dimensiona las zonas con los mínimos de estos tipos; pasillo en una pieza; luego se endurecen las preferencias fuertes.
- Opción para el cliente: plantilla de baño master de un lavabo (5 × 8) como alternativa permitida, igual que en la cocina.
- Despensas angostas (3 × 6.5) sin mobiliario.

## 4v. Paso 6.7a, S2.2c (12 oct 2026): plantillas de baño, master por el walk-in, planta abierta, perfil máximo

**Decisiones del cliente (12 oct, 01:59–02:06).**
- **Plantillas permitidas** (duras, cumple si cabe alguna):
  - baño master: doble lavabo 8 × 9 o un lavabo 5 × 8;
  - baño: tina 5 × 8 o ducha 5 × 7;
  - medio baño: 3 × 5 o esquina 4 × 4.
- **Master:** al baño se llega por el walk-in (recámara → walk-in → baño; K11 duro).
- **Baño compartido:** las puertas de las recámaras que lo comparten quedan cerca de la del baño.
- **Planta abierta por cultura** (anglo y sin cultura abiertas, latino separada): la sala se une al great room y el medio baño sigue privado (K04).
- **Perfil máximo:** pesa más la proporción (factor 1.6 sobre el peso de forma); nunca se estiran espacios.
- **Fachada del jardín:** es la del great room. La escalera va entre los cuartiles de los muros laterales (S2.2d).
- **Planta alta:** áreas óptimas, con el sobrante como techo o terraza de máximo 3 ft (S2.2d).

**Código y datos.**
- `design_space_standards` 0.4.0:
  - `templates_allowed` en baños;
  - `space.great_room.open_cultures`, `zones` (con la sala), `merge_units` (apagado: unir las unidades cocina y social bajó de 3 a 1 de 12 casas en el lote esquina; se retoma en S2.2d);
  - `space.policy.maximum_shape_factor`, `walk_through_closet`, `walk_through_min_side_ft` (6), `shared_bath_door_max_ft` (6).
- `unit_frame`: el walk-in del master con lado mínimo de paso; `SpaceFloor.profile` / `open_plan`; `great_room()` (unión opcional).
- `unit_layout`: orden de la suite [suite, walk-in, baño]; alcance del baño por el walk-in; `shape_weighted` para el perfil máximo.
- `door_placement`:
  - el baño del master abre primero al walk-in (las puertas de los walk-ins se colocan antes);
  - `great_room_pair`: los límites entre zonas del great room son vanos de largo completo (sin muro).
- `space_relations`: el par D recámara–baño se cumple a través del walk-in.
- `space_cell`: K11 duro después de las puertas (`k11:bath_not_through_walk_in`), `shared_bath_doors` en el término de circulación, cultura por celda.

**Piloto (`docs/results/s22c_pilot/`).**
- **39 casas** (intermedio: 43; la diferencia está dentro de la variación de la búsqueda, ±3 por lote).
- Sin lugar para el mobiliario: 16.5 % (antes 19 %); en recámaras 27 % (antes 38 %).
- Baños 100 % en rango; 49 clósets de baño, 18 de blancos y 31 de recámara.
- K11 descarta 9 casas.
- Bloqueos: zona privada sin corte válido (80), social sin corte (25), cocina sin corte (21). Siguen pidiendo que S2 dimensione las zonas (S2.2d).
- Pruebas: el fixture de S2.1 pasa a `teens_family.anglo` (la versión sin cultura ya no se completa).

## 4w. Paso 6.7a, S2.2d parte 1 (12 oct 2026): escalera en la franja central (K12), planta alta óptima con techo y terraza

**Decisiones del cliente (12 oct, 02:06).**
- **Escalera (K12):** entre los cuartiles del largo de los muros laterales y nunca sobre la fachada del jardín, que es la del great room y su luz.
- **Planta alta:** espacios en su área óptima, también en el perfil máximo; el sobrante va a techo o a terraza de máximo 3 ft.

**Código y datos.**
- `client_stair_rules` 0.6.0 con K12-STAIR-BAND:
  - `band` [0.25, 0.75] de la profundidad desde la calle; `measure: centre`;
  - con la huella completa dentro de la franja, 5 de 12 casas del subconjunto esquina se quedaban sin escalera y ninguna se completaba;
  - `garden_facade_free`.
  - `access_stair.in_band` filtra las candidatas («K12» en los descartes); `access_cell` pasa la regla.
  - Registro: `stair.band`, `stair.garden_facade_free`. Los cambios de perfil a stores que no son del diseño (reglas de escalera, catálogos) aún no llegan al pipeline: se materializan en S2.2f.
- `design_space_standards` 0.5.0, `space.upper.*`: `optimal_enabled`, `min_roof_sqft` 15, `terrace_enabled`, `terrace_max_depth_ft` 3, `terrace_from`.
- `unit_layout`:
  - en la planta alta, cada unidad (no circulación) se prueba además con sus espacios en área óptima y el sobrante como franja sobre una fachada (`_roof_variants`, como la franja de pasillo; las opciones de techo dentro del corte en columnas se rechazaban casi siempre por quedar adentro);
  - la franja se divide en terraza (≤ 3 ft, a lo largo de todo el muro de la recámara o estancia que sirve) y techo (`_terraces`);
  - las celdas al aire son exteriores para la fachada.
- `door_placement.compose` deja el techo y la terraza fuera de la planta (`FloorLayout.open_air`).
- `space_cell` emite `open_air` por planta (esquema `s21_floor.open_air`); las láminas dibujan el techo rayado y la terraza como deck.
- `plan_geometry.polygon_json` conserva los huecos de los polígonos (un foyer que rodea el medio baño se exportaba sin hueco).

**Piloto (`docs/results/s22d_pilot/`).**
- **Solo con K12: 26 casas** (S2.2c: 39).
- La escalera central deja 10 celdas sin escalera que quepa (S1) y 40 más sin zonificar en S2. Las candidatas que quedan suelen ser de la estrategia B (junta), que S2 no zonifica.
- Pasillos más cortos (17.5 ft contra 22) y casi sin espacios partidos (4 contra 19).
- **Con techo y terraza: 26 casas;**
  - 6 eligen techo (314 sq ft) y 2 terrazas de 3 ft junto al master (111 sq ft);
  - sobre la proporción máxima 23.9 %; sin mobiliario 17.2 %; espacios N sin luz suficiente 21.9 %.
- Pruebas: los fixtures de S2.1 pasan a `teens_family.latino`.

**Puerta a la terraza.** `place_terrace_doors`: corrediza de vidrio (72 in) centrada en el muro común entre la
recámara o estancia y su terraza (ejemplo: el master de young_couple en el lote angosto).

**Diagnóstico de K12.**
- Sin K12, 92 celdas elegían la estrategia D (escalera en la fachada del jardín, hoy prohibida); con K12 caen a B (junta, 107 celdas), que S2 zonifica mal.
- Las candidatas A en la franja se zonifican menos (276 contra 471).
- Mandar más candidatas por estrategia a S2 (`top_k` 3 → 6) no cambia la cobertura del subconjunto esquina.
- La palanca es S2: zonificar alrededor de un núcleo de escalera en la franja media.

**Pendiente (S2.2d parte 2).**
- S1/S2 con la escalera central: zonificación de ambas plantas alrededor de un núcleo en la franja media (pasillo-espina desde la puerta) y búsqueda de posiciones A dentro de la franja.
- Techos en varios planos sobre `open_air`.
- Endurecer las preferencias fuertes cuando las zonas vengan dimensionadas.

## 4x. Paso 6.7a, S2.2e (12 oct 2026): presupuesto de superficie, topes de área e interferencia de puertas

**Decisión del cliente (12 oct, 10:18).**
- Acepta la línea base del análisis `claude/spaceplan_6_7a_S2_2e_analisis_areas_puertas.md`.
- El ambiente adicional queda en "proponer".
- Todos los criterios deben poder modificarlos una persona o un LLM.

**Datos.**
- `design_space_standards` 0.6.0:
  - S00-AREA-CAPS (`space.area.*`):
    - topes activados;
    - jerarquía suite ≤ 1.8 × dormitorio recomendado;
    - suite completa ≤ 0.85 × garage;
    - comedor ≤ 0.8 × sala;
    - proporciones ajustadas por tamaño de vivienda (1600 → 3800 sq ft, +25 %);
    - margen de dibujo 6 %;
    - `freed_area` unbuilt/keep;
    - `extra_room_policy` never/propose/auto, con su paquete y un sobrecosto de 40 sq ft.
  - Por tipo: `area_rec_sqft`, `area_cap_sqft` y `area_share_max` en 14 tipos.
- `design_circulation_doors` 0.2.0 P03: R2, R3, `approach_depth_ft` 3, tolerancia, espesor de hoja, E1 y `doorway_max_width_ft` 8.
- Registro 0.4.0: 486 parámetros, con la referencia del garage y las restricciones rec ≤ cap y min ≤ cap.

**Código.**
- `design/lib/area_criteria.py`:
  - máximo efectivo = max(recomendada, mínima del catálogo, min(absoluto, jerarquía, proporción × neto × factor));
  - tope de la suite completa;
  - vistas por capas (código, programa, diseño).
- Herramientas LLM 0.2.0: `get_criteria` y `set_criteria`. CLI: `spaceplan design criteria --house-net N [--group doors]`.
- `program_adjust`:
  - paso 0, topes (`area_cap_sqft` en cada fila);
  - el área liberada sale de la planta (bruta = neta × bruta/neta de la planta; la baja nunca queda menor que la alta);
  - paso 3b, suite completa contra el garage;
  - paso 3c, ambiente adicional (propone o agrega).
- `SpaceSpec.cap_sqft`. `unit_layout._cap_area` reparte el exceso por llenado (water-filling) hasta el tope × (1 + margen).
- `lib_aux/door_geometry.py`: barrido, hoja cerrada y zona de paso con shapely y STRtree; reglas R1, E1, R1b, R2 y R3.
- `space_quality` / `run_quality`:
  - `over_cap`, área por tipo, métricas de la suite contra el garage;
  - puertas por planta;
  - `quality_doors.csv`.
- Esquema: `s21_space.cap_sqft`.

**Piloto (`docs/results/s22e_pilot/`).**
- 32 casas (antes 26).
- Dormitorio principal: mediana 255 sq ft (antes 303), máximo 275 (antes 385); suite/garage máx 0.95 (antes 1.12).
- Espacios sobre su tope: 6.3 % (antes 13.5 %).
- Interferencias exactas: 75 casos de R3 y 2 de R2.
- El paquete adicional cabe en 222 de 291 celdas (solo se propone).

**Pendiente.**
- P3, colocación conjunta de puertas: candidatas posición × lado × sentido × tipo, más reparación o CP-SAT.
- P4, muros con espesor y eficiencia neta/bruta explícita.
- P5, asignación MILP y aplicación de la propuesta del ambiente adicional.
- Decidir si se baja la mínima del catálogo de la suite (250 → 150–180), lo que requiere refrescar los golden.

## 4y. Paso 6.7a, S2.2f (12 oct 2026): estructura de la planta alta, llegada de la escalera y puertas agrupadas

**Decisiones del cliente (12 oct, 12:31).**
- Vigueta de 20 ft.
- Ejes interiores como regla obligatoria.
- Voladizo de 3 ft.
- Sala familiar arriba permitida como loft.

**Datos.**
- `design_structure.json` 0.1.0 (ruleset nuevo del registro):
  - T01 `structure.*`:
    - `joist_span_max_ft` 20 y `beam_span_max_ft` 20;
    - `axes_rule`: `bearing` o `all_zone_walls`;
    - `support_min_fraction` **0.0** (ver piloto); `snap_max_ft` 2.5; `snap_share` 0.25;
    - `partition_weight`, `pair_candidates`.
  - T02 `structure.code.*`: referencias CRC R602.10 y R301.2.2.6, sin verificar.
- `design_circulation_doors` 0.3.0:
  - P07 `circulation.arrival.*`: `node_short_side_max_ft` 8, `single_hall`, `family_loft`, `route_max_ft` 15;
  - P08 `door.grouping.*`: `nearest_corner`, `spread_target_ft` 12, `weight`.
- `stacking_catalog` 0.13.0:
  - voladizo de 3 ft (hard);
  - peso `structure` en S2 (0.15) y en S2.1 (0.1).
- Registro 0.5.0, con 508 parámetros.
- Herramientas LLM 0.3.0: `get_criteria` y `set_criteria` con el grupo `structure`.
- CLI: `spaceplan design criteria --group structure`.

**Código.**
- `lib_aux/structure_grid.py`:
  - muros como aristas V/H de una retícula de etiquetas; desplazamiento entre retículas;
  - `support_report`: muros sobre muros, vigas entre apoyos de abajo, postes; los muros exteriores sobre el
    interior de abajo se parten con postes;
  - `bearing_spans`: luces de vigueta entre líneas portantes, en x o en y;
  - `snap_line` y `box_lines`.
- `zone_grid.rasterize(anchor)`: la planta alta sobre las líneas de la baja (`upper_frame(anchored)`, `space_floor`).
- `core_zoning`:
  - `StructureGuide`: los cortes se corren a los muros de abajo y la llegada es un nodo de ≤ 8 ft, ajustado al
    descanso; la circulación cede su área a las otras zonas de su banda;
  - puntaje `structure`; violaciones `arrival:node` y `structure:*` (en S2 solo puntúan).
- `zone_cell`:
  - con estructura (solo etapa S2.1), la planta baja se busca primero; para las 3 mejores, la alta guiada sobre
    cada una más las libres (con nodo);
  - las alternativas se cruzan (`cross`).
- `space_cell` (S2.1):
  - planta baja primero, puntuada por cuánto carga los muros de zona de arriba (`above`), con la luz de vigueta
    obligatoria bajo la planta alta;
  - luego cada zonificación alta sobre las mejores bajas;
  - los cortes de los cuartos se corren a los muros de abajo (`below_lines`);
  - verificación obligatoria `structure:bearing`; bloques `structure` y `arrival` en la salida.
- `lib/floor_structure.py`: muros de abajo sin los bordes abiertos de la gran sala, verificación, luces de
  vigueta, agrupamiento de puertas, métricas de llegada.
- `door_placement`: la puerta del dormitorio va en la esquina más cercana a la llegada.
- `unit_layout`: un solo pasillo (contacto a todo el ancho) y cortes imantados.
- `space_quality`:
  - `structure_summary` y `arrival_summary`;
  - esquema: `s21.structure`, `s21.arrival`, `upper_placement: cantilever_rear` (faltaba).

**Piloto (`docs/results/s22f_pilot/`).**
- 25 casas (S2.2e: 32).
- Todas con luces de vigueta ≤ 20 ft (mediana 15.5).
- Llegada con lado corto ≤ 8 ft (mediana 5.5; antes llegaba a 16).
- Recorrido a los dormitorios: mediana 9.7 ft (antes 12.6).
- Muros de arriba sobre muros de abajo: 4 % → 9 % (mediana).
- Con `support_min_fraction` 0.5 el lote interior baja de 5 casas a 1. Queda en 0.0: líneas portantes
  obligatorias sobre muros o vigas, alineación premiada.

**Pendiente (S2.2g, propuesto).**
- Retícula estructural primero: crujías ≤ 20 ft definidas en la planta baja y zonas altas como fusión o
  subdivisión de esas bahías.
- Después, subir `support_min_fraction`.
- Láminas con vigas y postes.

## 4z. Paso 6.7a, S2.2g (12 oct 2026): marco estructural primero, posiciones por optimización y techos en varios planos

**Decisiones del cliente (18:45–18:51).**
- Enfoque C + E: soporte primero (Habraken/SAR), con posiciones por MILP.
- Planta alta de 30–40 ft: pasillo central con 2 ejes.
- Sobrante de la planta baja: porche o huella menor.
- El eje del núcleo de la escalera es un candidato más.
- Techos en varios planos.

**Datos.**
- `design_structure.json` 0.2.0:
  - T03 `structure.frame.*`:
    - `enabled` (hard), `bay_min_ft` 10, `spine_from_ft` 30, `variants` 3;
    - `axis_window_ft` 2, `fixed_pull_ft` 2.5, `surplus_min_sqft` 15;
    - `ground_surplus` (porch / unbuilt / either), `surplus_weight` 0.2;
    - `posts_per_axis_max` 1, `optimize`, `align_bonus_sqft` 10, `line_wall_bonus` 0.1.
  - T04 `structure.roofs.*`: `multi_plane`, `lower_kind` shed, `porch_kind` shed, `lower_pitch` 0.25,
    `min_piece_sqft` 20.
- Registro de 526 parámetros; `design_tools.json` regenerado. El grupo `structure` de las herramientas LLM ya los
  cubre.

**Código.**
- `lib/structural_frame.py` + `lib_aux/frame_geometry.py`:
  - patrón por el lado corto de la planta alta: una crujía, dos crujías o pasillo central;
  - candidatos: núcleo, garage, posición equilibrada y extremos de ventana;
  - junta de la planta alta sobre la baja; 3 variantes.
- `lib/frame_bands.py` + `core_zoning` (modo enmarcado, `FrameGuide`):
  - cortes de banda sobre las líneas del marco (cualquier subconjunto; la línea que no es corte queda dentro de una
    zona, con muro o viga en S2.1);
  - la crujía del pasillo central solo lleva circulación;
  - franja de circulación junto a un eje, con un pasillo mínimo junto a la escalera;
  - unidades al área de programa; el sobrante de cada banda queda al aire libre (techo arriba; porche o huella menor
    abajo);
  - la planta baja también prueba las topologías libres de S2 (ejes con viga);
  - bono por líneas que son muros de zona.
- `zone_cell`:
  - una búsqueda por variante de marco;
  - la baja solo se empareja con altas de su marco;
  - las alternativas de S2.1 alternan bajas enmarcadas y libres;
  - bloque `s2.frame` (estado framed / failed / fallback / none);
  - `open_air` por planta.
- `lib/frame_positions.py` + `lib_aux/milp_tools.py`:
  - corrimiento exacto de ejes libres dentro de su ventana;
  - MILP (HiGHS, sin presolve) para alinear muros de zona entre plantas;
  - verificación exacta (`FloorSearch.recheck`).
- S2.1:
  - el aire libre de S2 queda fuera (`unit_frame`);
  - cortes imantados a los ejes;
  - `floor_structure.frame_report`: muro o viga en cada eje, con postes como máximo `posts_per_axis_max` (hard);
  - en modo enmarcado no se aplican las verificaciones de luz de S2.2f;
  - bloques `s21.frame` y `s21.roofs` (`lib/roof_planes.py` + `lib_aux/roof_geometry.py`).
- `space_quality`: `frame_summary` y `roofs_summary`. Esquema: `s2.frame`, `s2_floor.open_air`, `s21.frame`,
  `s21.roofs`. Láminas: ejes, porche, techo bajo.
- Pruebas: `tests/stacking/test_stage_s22g.py`.

**Piloto (`docs/results/s22g_pilot/`).**
- 39 casas (S2.2f: 25; S2.2e: 32).
- Misma dirección en 39 / 39; 43 ejes compartidos, todos con muro o viga; 67 % de su largo con muro; 20 postes.
- Muros de zona sobre muros de abajo: 48 % (S2.2f: 39 %). Todos los muros: 26 %, sin cambio.
- Proporciones algo mejores; R3 sube a 95.
- Techos: mediana de 5 planos por casa.

**Pendiente.**
- Alinear tabiques en S2.1: los cuartos de arriba se cortan sobre los de abajo, con un MILP de cortes de cuarto.
- Limitar la profundidad de los techos de una caída (cortar a dos aguas o en varios tramos).
- Láminas de techos en el módulo `viz`.

## 4aa. Paso 6.7a, S2.2h (12 oct 2026): pasillo de la planta alta recortado

**Decisiones del cliente (21:42–22:03).**
- Vestíbulo de 3 ft como mínimo (obligatorio) y hasta 4 ft (preferido) antes de la primera puerta de dormitorio.
- Clóset de blancos con el ancho del pasillo, de muro a muro, y 2 ft de fondo.
- Remanente entre dos cuartos: clósets de 2 ft y el resto al cuarto (walk-in desde 5 ft).
- Remanente de un cuarto o sin dormitorio: techo si da a fachada; si no, clóset o se suma al vecino.
- Fase 2 (circulación por servicio en S2) después de medir.

**Datos.**
- `design_circulation_doors` 0.4.0, P09 `circulation.upper_hall.*`: `trim`, `vestibule_min_ft` 3 (hard),
  `vestibule_pref_ft` 4, `door_margin_ft` 0.5, `linen`, `walk_in_from_ft` 5, `tail_one_room` roof/closet,
  `tail_no_room` roof/neighbour, `dead_end_target_sqft` 15.
- Registro de 535 parámetros. El grupo LLM `structure` incluye `circulation.upper_hall.`.

**Código.**
- `door_placement`:
  - las puertas de dormitorio sobre circulación quedan al menos a `vestibule_min_ft` del descanso
    (`landing_gap`);
  - posiciones que se alejan de la esquina celda por celda (`_positions`).
- `lib/hall_trim.py` + `lib_aux/hall_geometry.py`:
  - pasillo servido (descanso + franja frente a cada puerta);
  - remanentes por rectángulo;
  - clóset de blancos de muro a muro;
  - remanentes a clósets, walk-in, techo (`upper_roof`), cuarto o vecino.
- `space_cell._trimmed`: tras las puertas, recorte; puertas otra vez; si falla, se conserva el pasillo. Bloque
  `s21.upper.hall_trim`.
- `space_quality.circulation_summary`. Esquema: `s21_floor.hall_trim`. Pruebas: `tests/stacking/test_stage_s22h.py`.

**Piloto (`docs/results/s22h_pilot/`).**
- 39 casas, sin pérdida; 30 plantas recortadas.
- Pasillo más allá de lo que sirve: mediana 20.8 → 0 ft².
- Pasillo arriba: 157 → 118 ft².
- Circulación: 20.6 → 18.2 %.
- 0 puertas a menos de 3 ft del descanso.
- 31 clósets de blancos y 27 de dormitorio; 605 ft² a techo.

**Pendiente (fase 2).**
- Pasillos anchos de llegada (6.5–8 ft) y franjas junto a la escalera: dimensionar la circulación por servicio desde
  S2.

## 4ab. Paso 6.7a, S2.2i (13 oct 2026): planta alta — principal, puertas, baños, cercanía y vano de escalera

**Decisiones del cliente (17:06).**
- Dormitorio principal con walk-in, también con la suite abajo.
- Las puertas se corren para no chocar.
- Baños en muros laterales.
- Puertas de dormitorios lo más cerca posible de la escalera, sin máximo.
- Vano de escalera por altura libre.

**Datos.**
- `design_space_standards` 0.7.0: S00 `space.master_bedroom.*` (`enabled`, `walk_in`, `extra_share` 0.15).
- `design_circulation_doors` 0.5.0:
  - P03 `door.conflicts.shift_on_placement` y `off_corner`;
  - P10 `circulation.upper_rooms.*`: `bed_near_weight` 0.3, `near_scale_ft` 6, `bath_side_weight` 0.2,
    `bath_walls` low_x / high_x.
- `design_structure` 0.3.0: `structure.stair_opening`, `structure.floor_depth_in` 12.
- Registro de 546 parámetros. Grupo LLM `structure` ampliado (`circulation.upper_rooms.`, `space.master_bedroom.`).

**Código.**
- `program_adjust`, paso 2b: principal (el "primary" o el mayor). Más área tomada de los otros dormitorios y walk-in
  hospedado; el principal recibe primero el baño en suite; el bruto y S1 no cambian.
- `door_placement`:
  - zona de paso (`approach`) de cada puerta colocada;
  - una hoja no entra en el paso de otra, ni otra en el suyo;
  - posiciones en la otra esquina y corridas por el muro (`off_corner`);
  - corredizas corridas.
- `unit_layout._upper_parts`: puntaje de cercanía de los dormitorios al descanso (transformada de distancia) y de
  baños en los muros preferidos.
- `space_cell._floor_parts`: cercanía real de las puertas.
- `floor_frame.stair_cover_ft` / `with_stair_opening` + `stair_geometry.covered_start`:
  - el vano de la planta alta;
  - `unit_frame._covered_stair`: el arranque cubierto va al cuarto vecino si queda rectangular; si no, vuelve a la
    escalera;
  - `hall_trim.stair_cover_closet` lo convierte en clóset del espacio que toca.
- Salida `s21.upper.stair_opening`, `stair_covered_sqft`, `stair_cover`.
- `space_quality.upper_rooms_summary`. Láminas: vano en vez de la huella. Esquema. Pruebas:
  `tests/stacking/test_stage_s22i.py`. `test_stage_s21b`: la regla de la hoja contra el muro aplica a las puertas en
  esquina.

**Piloto (`docs/results/s22i_pilot/`).**
- 42 casas (S2.2h: 39).
- Walk-in en 21 de 21 casas con ≥ 2 dormitorios arriba.
- R3: 94 → 45.
- Baños con muro exterior: 56 → 80 %.
- Puerta de dormitorio: mediana 6.8 → 3.5 ft de la llegada.
- Arranque de escalera cubierto: 7.5 ft²; 39 clósets.

**Pendiente.**
- El principal debe ser el dormitorio mayor también al dibujarlo en S2.1.
- Mobiliario que no cabe: 16.9 → 20.6 %.
- Conflictos dentro de los baños.

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

- Altura 24/30 ft: leída en 6.7a como 24 ft en el retiro lateral → 30 ft total (Diagrama 131-04L, provisional; V01). Medición 113.0270, sótanos 113.0234(a)(2), pisos 113.0261 y garaje en el FAR **verificados** (reglas V02–V05). Pendiente: definición de *steep hillsides*, mapa C-1041, retiros de estructuras subterráneas y si el sótano cuenta en el IO.
- Ancho y profundidad de lote irregular y posterior en lotes triangulares (Cap. 11).
- Si el deck cuenta como pavimento (131.0447): **decide los 18 máximos inviables del lote fan-curve** (62.5 % con deck, 52 % sin él; sección 4n). Si garaje/deck/bodega cuentan en el FAR.
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
| 6.7a | Apilamiento: ~~S0 niveles y altura (sección 4j)~~ **hecho**; ~~S1 escalera, polígono por nivel con 131.0444, contención (sección 4k)~~ **hecho**; ~~S1.1 configuraciones, bajo escalera, llegada y arranque (4l)~~ **hecho**; ~~S2 zonificación de ambas plantas alrededor del núcleo (4o)~~ **hecho**; ~~S1.2 escalera desde la puerta (4p, 4q)~~ **hecho**; ~~S2.1 v1 espacios y puertas (4r)~~ **hecho** (47 %); ~~S2.1b puertas, baños, salidas, voladizo, antejardín (4s)~~ **hecho** (45 %, 0 sin acceso); S2.1c cobertura de plantas bajas; S2.2 calidad de espacios: ~~S2.2a registro y KPIs (4t)~~ **hecho**, ~~S2.2b registro en S2.1, perfil intermedio (4u)~~ **hecho** (43 casas, baños 100 % en rango), ~~S2.2c baños, walk-in, planta abierta (4v)~~ **hecho** (39), S2.2d parte 1 escalera K12 + techo/terraza (4w) **hecho** (26), S2.2d parte 2–f (oct–dic 2026) | oct 2026–ene 2027 | 8 | Los mejores esquemas de 2 pisos de 6.6 con planta dibujada |
| 6.7b | Nivel −1: sótano de servicio y walkout (B0–B3), terreno por borde (brief 0.6), costo de excavación | ene 2027 | 4–6 | Hipótesis H1–H4 contrastadas |
| 6.8 | Puntaje de calidad común, Pareto del portafolio, codo costo–calidad, detector de soluciones forzadas, retroceso por columna, perfiles por tipo de lote | feb 2027 | 8 | Opción recomendada con alternativas y explicación |

Total ≈ 50 h (6.6 tomó 8 h por los esquemas verticales, los índices y el lote bandera). Mínimo viable ≈ 14 h: 6.5a con 4 arquetipos, 6.5b nivel base, 6.5c solo cocina y matriz D/I/N.
El paso 7 detallado (zonificación por piso con la junta como núcleo) queda para un curso o después de F3.

### Reestructuración modular (opción A, 8–9 oct 2026) — **hecha** (sección 4i)
spaceplan quedó en módulos por etapa con contratos JSON ejecutables, en 4 tandas programadas sobre la rama
`spaceplan-modular` del repositorio `Remolino777/rule_forge` (ramas instantáneas `refactor/tanda-0` a
`refactor/tanda-4`). Plan: `docs/refactor/REFACTOR_PLAN.md`; informes: `docs/refactor/log/`; verificación de que
nada cambia: `python tools/golden_check.py check`. El paso 6.7 se construye como módulo nuevo `stacking`
(propuesta: consume `lot_capacity`, `site_plan` y `area_matrix`; produce un contrato nuevo, p. ej. `stacked_scheme`).

## 9. Posibilidades de innovación registradas

- (paso 6.7a S2.2) Agente LLM de diseño sobre las herramientas del registro (dialoga con el cliente, propone y valida
  cambios, compara variantes con trazas; encaja con el marco multiagente de F3); aprender rangos y pesos de las
  elecciones del cliente (preferencias por pares); puntaje de calidad aprendido de RPLAN / CubiCasa5k; agente de
  mobiliario; simulación de luz diurna (Radiance / Honeybee) y orientación solar de San Diego; costo de ventilación
  mecánica (Qtot 62.2) en el índice de costo.

- (paso 6.7a S2.1) Retroceso S2.1 → S2 → S1 como búsqueda en cascada con presupuesto (hoy: 3 zonificaciones × 4
  escaleras); zonificación consciente del pasillo (la franja interior como parte del objetivo de área); grafo de puertas
  con arista vertical como métrica de privacidad (profundidad de la suite) y descriptor de MAP-Elites; muro libre para
  mobiliario; exportación directa a IfcSpace/IfcDoor (paso 13); reglas de puerta y escape como caso RuleForge con traza
  por espacio; el plano `s21` como sustituto del paso 6 de planogen.

- (paso 6.7a S2) Retroceso entre etapas generalizado (S2 ya pide a S1 otra colocación o escalera; falta S1 → áreas:
  dimensionar la planta alta con la huella real de la escalera); profundidad sintáctica entre pisos con arista
  vertical como métrica de privacidad para 6.8 y MAP-Elites (descriptores: arranque A/B/C, receptor de llegada, zona
  partida a ambos lados del hall); reparto tipo mochila de 9a guiado por la penalización de adyacencias de S2; tres
  capas de reglas (normativa, cliente, matriz) con precedencia y trazas `overridden_by` como caso RuleForge; zonas en
  L o con quiebre alrededor del núcleo; lado del garaje desde el contrato de sitio.

- (reestructuración modular) Contratos como frontera para ejecutar módulos en paralelo o como servicios, con caché
  por `input_sha256`; rehidratar la geometría desde `lot_capacity` para que `site` y `zoning` corran solo con
  contratos; generar los esquemas desde los tipos (`dataclasses` → JSON Schema); selección de pruebas por impacto con
  el grafo de módulos generado; contratos versionados por fragmento del catálogo para saber qué módulo cambió un
  resultado; un módulo `stacking` (6.7) y luego `ifc_export` (paso 13) como consumidores puros de contratos.

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

> Continuamos el módulo spaceplan del capstone (repositorio `Remolino777/rule_forge`, rama `stacking/6.7a-s2.2`,
> secciones 4t–4ab del HANDOFF). S2.2i dejó la planta alta con dormitorio principal con walk-in, puertas corridas
> para no chocar (R3 94 → 45), baños en muros exteriores (80 %), puertas a 3.5 ft de la escalera y el vano de
> escalera por altura libre; 42 casas. Pendiente: el principal como el dormitorio mayor en S2.1, el mobiliario y la
> fase 2 de circulación por servicio. Mide con `spaceplan quality` contra `docs/results/s22i_pilot/`. Respeta las
> reglas de la sección 1. Primero haz el análisis lógico y el plan, y pregúntame antes de programar.
