# Plan de reestructuración modular de spaceplan (opción A, 4 tandas programadas)

Repositorio: `Remolino777/rule_forge`, rama **`spaceplan-modular`**, carpeta `spaceplan/`.
Punto de partida: rama instantánea **`refactor/tanda-0`** (pasos 1–6.6 completos, 620 pruebas, instantánea dorada en `tests/golden/`).
Autorización del usuario (8-oct-2026): las tandas 1–4 **programan sin preguntar**, con las salvaguardas de este
documento. Fuera de estas tandas vuelve a regir la regla "preguntar antes de programar".

## 0. Reglas que toda tanda respeta

1. Respuestas e informes en **español**; código, nombres y comentarios en **inglés**.
2. Cada módulo se organiza en `main/` (workflow), `lib/` (funciones de dominio) y `lib_aux/` (sin dominio).
3. Ningún número normativo en el código (DSL `data/rules/*.json`; parámetros en el catálogo con fuente y estado).
4. **Refactorización pura: no cambia ningún resultado.** Si se encuentra un error, se anota en el informe de la tanda
   y NO se corrige.
5. **Nunca** se editan los archivos de `tests/golden/` ni la rama `main`. Solo se trabaja en `spaceplan-modular`.
6. Commits con estas líneas al final:
   ```
   Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   ```
7. F3 (RuleForge) no se toca.

## 1. Criterio de aceptación de cada tanda (obligatorio)

- `pytest -q` completo pasa (620 pruebas al inicio; puede crecer, nunca bajar sin justificación escrita). La suite tarda
  ≈ 9 min: correrla en tandas de archivos con timeout de 10 min cada una.
- `python tools/golden_check.py check` imprime `GOLDEN CHECK PASSED` (≈ 2 min).
- `ruff check` sin errores nuevos en los archivos creados o movidos (el repositorio ya tenía 67 avisos heredados).
- Si se cumplen: commit, `git push origin spaceplan-modular` y rama instantánea
  `git push origin spaceplan-modular:refs/heads/refactor/tanda-N` (las etiquetas no pasan por el proxy de git).
- Si NO se cumplen al final de la sesión: subir el trabajo a la rama `spaceplan-modular-tanda-N-wip` (sin rama instantánea),
  dejar `spaceplan-modular` intacta y explicar en el informe qué falta.
- Siempre: escribir `docs/refactor/log/tanda-N.md` (qué se hizo, archivos movidos, decisiones, tiempos de la suite,
  errores encontrados sin corregir, pendientes para la tanda siguiente) y subirlo en la rama que corresponda.

## 2. Procedimiento de arranque de cada tanda

```bash
git clone --depth 50 --branch spaceplan-modular https://github.com/Remolino777/rule_forge /home/claude/rule_forge
cd /home/claude/rule_forge
git ls-remote --heads origin "refactor/tanda-*"   # debe existir refactor/tanda-(N-1) y apuntar al mismo commit
                                                  # que spaceplan-modular; si no: DETENERSE e informar
cd spaceplan && pip install -e ".[dev]" --break-system-packages
python tools/golden_check.py check  # debe pasar ANTES de empezar; si no: DETENERSE e informar
```
Leer este documento, `HANDOFF_spaceplan.md` (secciones 1, 3 y 4h) y el informe de la tanda anterior.

## 3. Arquitectura objetivo

```
spaceplan/                      (paquete instalable, mismo nombre)
  core/                         núcleo compartido, no importa ningún módulo
    lib_aux/                    geometry, quantity, hashing, json_io, tolerances, section, predicates, knee,
                                weighted, allocation, pareto
    lib/                        enums, rules (acceso al DSL), catalog (cargador y validador que fusiona
                                fragmentos), schema_validation, relation_graph
  contracts/                    esquemas JSON de las fronteras entre módulos (*.schema.json) + README
  modules/
    lotcap/   {main,lib,lib_aux}  lote, linderos, métricas, variantes de reglas, alcance, capacidad, lote bandera
    site/     {main,lib,lib_aux}  partición del sitio, orientación, patio
    household/{main,lib,lib_aux}  hogar, catálogo de hogar, reglas, cultura, programa, revisión del programa
    cost/     {main,lib,lib_aux}  ficha de cantidades, modelos de costo, presupuesto, sensibilidad
    profiles/ {main,lib,lib_aux}  curva de expansión, mínimo / óptimo / máximo, por etapas, accesible
    zoning/   {main,lib,lib_aux}  zonificación, espacios, circulación, matriz D/I/N, estrategias, poligonal,
                                  correcciones, unidad de apartamento
    areas/    {main,lib,lib_aux}  esquemas verticales, índices IC/IO, presupuesto de áreas, matriz por lote
    viz/      {main,lib,lib_aux}  dibujos y láminas; leen contratos, nunca calculan dominio
  pipeline/
    main/                       orquestador (run_capacity delgado), CLI, ensamblado del paquete
    lib/                        package (ensamblado), catalog_table (documentación)
  data/                         schemas/, rules/, briefs/, catalog/ (fragmentos por módulo)
```

### 3.1 Asignación de archivos actuales

| Archivo actual | Destino |
|---|---|
| `lib_aux/*` (todos) | `core/lib_aux/` |
| `lib/enums, rules, catalog, schema_validation, relation_graph` | `core/lib/` |
| `lib/lot, boundaries, lot_metrics, rule_variants, scope, capacity, flag_lot` | `modules/lotcap/lib/` |
| `main/run_capacity.prepare_lot` (+ `LotSetup`) | `modules/lotcap/main/` |
| `lib/site_partition, orientation, backyard` | `modules/site/lib/` |
| `lib/household, household_catalog, household_rules, culture, program_builder, program_review` | `modules/household/lib/` |
| `main/run_household, run_program` | `modules/household/main/` |
| `lib/quantities, cost_models, budget, cost_sensitivity` | `modules/cost/lib/` |
| `main/run_cost` | `modules/cost/main/` |
| `lib/program_profiles` | `modules/profiles/lib/` |
| `main/run_profiles` | `modules/profiles/main/` |
| `lib/zoning, space_layout, circulation, relation_matrix, realization, polygonal, corrections, unit` | `modules/zoning/lib/` |
| `main/run_corrections` | `modules/zoning/main/` |
| `lib/vertical_split, building_indices, area_budget, area_matrix` | `modules/areas/lib/` |
| `main/run_area_matrix` | `modules/areas/main/` |
| `lib/visualize, review_notes` | `modules/viz/lib/` (repartir `visualize` por módulo en la tanda 3) |
| `lib/package, catalog_table` | `pipeline/lib/` |
| `main/run_capacity` (resto), `main/cli` | `pipeline/main/` |

### 3.2 Dependencias permitidas entre módulos (grafo acíclico)

```
core      <- todos
lotcap    <- core
household <- core
cost      <- core
site      <- core, lotcap
profiles  <- core, household, cost
zoning    <- core, lotcap, site
areas     <- core, lotcap, site, household, cost, profiles
viz       <- core (y contratos; puede leer tipos de lotcap para dibujar el lote)
pipeline  <- todos
```
Ningún `main/` de un módulo importa el `main/` de otro módulo: solo `pipeline` compone.

### 3.3 Contratos (fronteras)

| Contrato | Produce | Consume | Contenido mínimo |
|---|---|---|---|
| `brief` (existe) | usuario | pipeline | esquema actual 0.5 |
| `lot_capacity` | lotcap | site, zoning, areas, viz | lote (GeoJSON), linderos, retiros, variantes, envolvente, FAR, cobertura, capacidad realizable por estrategia, conformidad, sensibilidad |
| `site_plan` | site | zoning, areas, viz | opciones por pisos, accesos, pavimento, jardín, fachadas, patio |
| `program` | household | profiles, zoning, cost | programa (espacios), necesidades por nivel, traza de reglas, bloque de hogar con privacidad |
| `cost_report` | cost | profiles, areas, pipeline | ficha de cantidades, índice por modelo, presupuesto, tornado |
| `program_portfolio` | profiles | areas, viz | curva, cinco perfiles, techos |
| `zoning_scheme` | zoning | viz, pipeline | opciones, esquemas de zonas y espacios, circulación, correcciones |
| `area_matrix` | areas | viz | presupuesto del lote, celdas, rangos, Pareto, E2 |
| `package` (existe) | pipeline | usuario | esquema actual 0.9, sin cambios |

Cada contrato lleva `contract`, `version`, `produced_by` y `input_sha256`.

## 4. Tandas

### Tanda 1 — contratos, núcleo y catálogo (hoy 9:00)
1. Escribir `spaceplan/contracts/*.schema.json` para los 7 contratos nuevos (Draft 2020-12, basados en los bloques
   que hoy existen en el paquete y en los objetos que se pasan entre etapas) y `contracts/README.md` (español).
2. Crear `core/` y mover allí los archivos de 3.1 (`git mv`). En las rutas viejas dejar **módulos puente** que
   reexportan (`from spaceplan.core.lib.rules import *` más los nombres privados que usen las pruebas), para que
   nada más cambie en esta tanda.
3. Partir `data/catalog/residential_catalog.json` en fragmentos por módulo (`data/catalog/fragments/<módulo>.json`
   + `index.json` con el orden). El cargador fusiona los fragmentos en el **mismo diccionario**; prueba nueva: el
   diccionario fusionado es idéntico al archivo original (que se conserva hasta la tanda 4 como referencia).
   La validación semántica se reparte por fragmento. El catálogo de hogar queda en el módulo `household`.
4. Prueba de arquitectura v2: `core` no importa nada fuera de `core`.
5. Aceptación (sección 1), rama `refactor/tanda-1`.

### Tanda 2 — paquetes de módulo (hoy 15:00)
1. Crear `modules/<m>/{main,lib,lib_aux}` y `pipeline/` y mover los archivos según 3.1 con `git mv`, con módulos
   puente en las rutas viejas (`spaceplan.lib.*`, `spaceplan.main.*`).
2. Mover `prepare_lot`/`LotSetup` a `modules/lotcap/main/`.
3. Prueba de arquitectura v3: el grafo de 3.2 (por módulo, sin contar los puentes); falla si aparece una arista no
   permitida. Si una dependencia actual lo viola, anotarla en el informe y resolverla en la tanda 3 (marcarla como
   excepción temporal con fecha).
4. `pyproject.toml`: incluir los paquetes nuevos y los datos.
5. Aceptación, rama `refactor/tanda-2`.

### Tanda 3 — puntos calientes (hoy 21:00)
1. Romper el ciclo `zoning` ↔ `space_layout` (extraer lo compartido a un tercer archivo del módulo).
2. Interfaz pública del sitio: `areas` no usa funciones privadas de `site_partition` (publicar lo necesario).
3. `run_capacity` en `pipeline` queda como orquestador delgado: la resolución del hogar pasa al `main` de
   `household`, el costo al de `cost`, el lote bandera al de `lotcap`. Eliminar la cadena `main` → `main`.
4. Repartir `visualize.py` en archivos por módulo dentro de `viz/lib/` (lote y sitio, zonificación, portafolio,
   matriz de áreas, láminas de revisión).
5. Quitar las excepciones temporales de la tanda 2; prueba "sin ciclos" sobre todos los módulos.
6. Aceptación, rama `refactor/tanda-3`.

### Tanda 4 — contratos ejecutables, pruebas por módulo, cierre (mañana 3:00)
1. Funciones `to_contract` / `from_contract` por módulo, validadas contra su esquema; el `pipeline` encadena
   contratos (el paquete final no cambia: lo verifica la instantánea dorada).
2. CLI por módulo: `spaceplan lotcap|site|household|cost|profiles|zoning|areas|viz ...` que lee y escribe contratos.
   Los comandos actuales (`capacity`, `profiles`, `areas`, ...) siguen funcionando.
3. Pruebas por módulo en `tests/<módulo>/` con contratos fijos de ejemplo (`tests/<módulo>/fixtures/*.json`
   generados desde la instantánea), de modo que cada módulo se pruebe sin correr el pipeline completo. Prueba de
   contrato: la salida de cada módulo valida contra su esquema y el consumidor la acepta.
4. Actualizar las pruebas a las rutas nuevas, eliminar los módulos puente y el `residential_catalog.json` original.
5. Documentación: `docs/architecture/modules.md` (grafo de módulos generado desde el código, contratos, cómo agregar
   un módulo), README y HANDOFF (nueva sección 4i; estado; tabla de archivos). Medir y anotar el tiempo de la suite
   completa y el de cada módulo.
6. Aceptación, rama `refactor/tanda-4`.

## 5. Informe final (tanda 4)

Resumen para el usuario en español: estado de las 4 ramas `refactor/tanda-N`, número de pruebas, tiempo de la suite antes y
después, módulos y contratos creados, errores encontrados sin corregir y siguiente paso sugerido (paso 6.7 como
módulo nuevo `stacking`).
