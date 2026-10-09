# Informe de la tanda 4 — contratos ejecutables, pruebas por módulo, cierre

Fecha: 9-oct-2026 · Rama: `spaceplan-modular` · Punto de partida: `refactor/tanda-3` (`ae2db90`)
Ejecución: tarea programada, sin intervención del usuario (autorización del 8-oct-2026).

## Resultado

**Aceptada.** Pytest completo: **1,026 pruebas pasan** (1,107 al inicio; ver la justificación de la baja abajo).
`python tools/golden_check.py check` → `GOLDEN CHECK PASSED (16 frozen files)` antes (2 min 31 s) y después
(2 min 36 s). `ruff check`: ningún aviso nuevo en los archivos creados o movidos (89 → 73 avisos en el informe
completo; los que cambian de nombre son heredados con la ruta nueva, ver abajo).

Verificación adicional de pureza (fuera de la instantánea dorada, que redondea y ordena claves): desde un árbol
aislado de `refactor/tanda-3` y desde el árbol final se generaron los **paquetes en bruto** (`json.dumps` sin
ordenar claves ni redondear, solo sin `meta.generator`) de los 15 briefs con opciones por omisión, más
`interior_50x100`, `fan_cul_de_sac_35_80x100` e `interior_50x100_multigen_latino` con `--budget ample
--cost-model shape` y con `--no-corrections`: **los 21 archivos son idénticos byte a byte** (incluidos el orden de
claves, `package_id` y los bloques `household` y `cost`, que el paquete no redondea).

## Arranque (sección 2)

- `refactor/tanda-3` existe y apunta a `ae2db90`, el mismo commit que `spaceplan-modular`.
- `pip install -e ".[dev]"` sin errores. Golden check previo: PASSED (2 min 31 s).
- Nota de entorno: el clon local tenía la cabeza separada (`HEAD detached`) y una rama local `spaceplan-modular`
  vieja (`fee4ec0`); antes del commit se reubicó la rama local en `origin/spaceplan-modular` (`ae2db90`).

## Qué se hizo

### 1. Contratos ejecutables (`to_contract` / `from_contract`) y pipeline que encadena contratos

- `core/lib/contracts.py` (nuevo): `make_contract` (sobre + carga, valida), `read_contract` (valida y devuelve los
  bloques sin el sobre), `validate_contract`, `load_contract`, `write_contract`, `ContractValidationError`,
  `serialize` (movido sin cambios desde `pipeline/lib/package.py`), `package_json` (igual que el paquete:
  serializar, ida y vuelta JSON, 4 decimales) y `plain_json` (solo ida y vuelta JSON). Validadores en caché.
- `modules/<m>/main/contract.py` en los 7 productores, cada uno con `NAME`, `to_contract` y `from_contract`:

| Módulo | `to_contract` recibe | Contrato |
|---|---|---|
| lotcap | brief planificado, `ScopeResult`, `LotSetup`, estrategia, lote bandera | `lot_capacity` |
| site | brief, partición del sitio (con patio), avisos del sitio | `site_plan` |
| household | brief con programa, revisión del programa, bloque de hogar | `program` |
| cost | bloque de costo (y `cost_from_contracts`, que lee `lot_capacity`, `site_plan` y `program`) | `cost_report` |
| profiles | portafolio y sus entradas | `program_portfolio` |
| zoning | brief, zonificación, unidad, corrección, estrategia | `zoning_scheme` |
| areas | resultado de la matriz (entradas = `meta`) | `area_matrix` |

- `_boundaries` y el armado de avisos del lote pasaron, sin cambios, de `pipeline/lib/package.py` a
  `lotcap/main/contract.py` (`boundary_rows`, `lot_warnings`); el bloque `unit` del apartamento, de
  `pipeline/main/run_capacity.py` a `zoning/main/run_zoning.py` (`unit_record`).
- `pipeline/lib/package.py`: `package_from_contracts(brief, ruleset, scope, program, strategy, lot_capacity,
  site_plan, zoning_scheme)` reemplaza a `assemble_package(PackageInputs)`; solo importa `core` (lo verifica una
  prueba). Los avisos conservan el orden histórico (lote, sitio, zonificación, corrección, revisión).
- `pipeline/main/run_capacity.py`: nuevo `run_capacity_contracts(brief, ...) -> (paquete, contratos)`;
  `run_capacity` devuelve el paquete (misma firma). Casa en alcance: `program` → `lot_capacity` → `site_plan` →
  `zoning_scheme` → paquete desde contratos → `cost_report` con `cost_from_contracts` (el costo lee los contratos
  como JSON; `cost` no importa código de lotcap, site ni household). Apartamento: `program` + `zoning_scheme`.
  Fuera de alcance: `program`. Las figuras `--plot/--site-plot/--zoning-plot` se dibujan desde los contratos.
- `modules/viz/main/run_viz.py` (nuevo): `package_view` (vista con forma de paquete armada desde contratos),
  `draw_capacity`, `draw_site`, `draw_zoning`, `draw_area_matrix` y `area_matrix_figures` (movido sin cambios desde
  `pipeline/main/run_area_analysis.py`). El lote se redibuja desde el bloque `lot` del brief que lleva el contrato.
- Esquemas 0.2.0 (`$id` `.../0.2.0`): `brief_id` opcional en el sobre de todos; `lot_capacity` agrega
  `lot.lot_block`, `terrain`, `realization_strategy`; `site_plan` agrega `warnings`; `zoning_scheme` agrega
  `dwelling_type`, `realization_strategy`; `program_portfolio` y `area_matrix` detallados (perfiles con programa
  validado contra el esquema del brief; celdas con 16 claves obligatorias). `contracts/README.md` actualizado.

### 2. CLI por módulo (los comandos actuales siguen igual)

`pipeline/main/run_modules.py` (nuevo) con `capacity_contracts`, `program_contract_for`, `cost_contract_for`,
`portfolio_contract_for`, `area_matrix_contract_for`. Comandos nuevos: `spaceplan lotcap|site|zoning BRIEF -o C`,
`spaceplan cost --lot-capacity --site-plan --program [--brief] [--budget] [--cost-model]`, `spaceplan viz
[--lot-capacity] [--site-plan] [--zoning-scheme] [--area-matrix] --capacity-plot|--site-plot|--zoning-plot|--sheets`;
opciones nuevas `household BRIEF.json --contract`, `profiles --contract`, `areas --contract`, `capacity
--contracts DIR`. Un contrato del tipo equivocado sale con código 2 y el mensaje del validador.

### 3. Pruebas por módulo con contratos fijos

- Pruebas movidas con `git mv` a `tests/<módulo>/`: core (geometry, catalog, catalog_fragments, schemas,
  contracts), lotcap (scope, rule_variants, capacity_reference), site (site_partition, backyard, orientation),
  household (household, culture, program), cost, profiles, zoning (zoning, circulation, realization, strategy_b),
  areas (area_matrix), pipeline (cli, architecture). `conftest.py` común en `tests/` (más `load_fixture`,
  `golden_package`, `normalized`, `assert_close`, `without_seconds`).
- 14 contratos fijos en `tests/<módulo>/fixtures/` generados por `tools/make_fixtures.py` (nuevo): casas
  `interior_50x100` e `interior_50x100_multigen_latino`, apartamento `apt_2br_interior`, portafolio
  `empty_nest.anglo`, matriz `interior_50x100 × empty_nest.anglo`. La herramienta **solo escribe** si el paquete
  armado con esos contratos es idéntico a la instantánea dorada y si las celdas de la matriz son filas de la
  tabla dorada; `check` compara sin escribir.
- Pruebas nuevas (60): `tests/<m>/test_<m>_contract.py` en lotcap (9), site (5), household (8), cost (8),
  profiles (5), zoning (7), areas (5), viz (4); `tests/pipeline/test_pipeline_contracts.py` (7: paquete armado solo
  con contratos fijos = paquete dorado; contratos del pipeline = fijos; CLI por módulo de ida y vuelta; contrato
  equivocado rechazado) y `tests/pipeline/test_docs.py` (2). Patrón de cada archivo: salida del módulo = contrato
  fijo; contrato fijo = bloques dorados; valida contra su esquema; el consumidor lo acepta; un contrato alterado
  se rechaza. `cost` se prueba solo con contratos (sin calcular lote, sitio ni zonificación).

### 4. Rutas nuevas, puentes y catálogo original eliminados

- Pruebas y `tools/golden_check.py` importan las rutas canónicas (reescritura por AST que resuelve cada nombre en
  el módulo que lo define; solo cambiaron líneas de importación).
- Eliminados: los 61 puentes (`spaceplan/lib/` 37 + `__init__`, `spaceplan/lib_aux/` 11 + `__init__`,
  `spaceplan/main/` 8 + `__init__`), la fachada `viz/lib/visualize.py` y `data/catalog/residential_catalog.json`.
  El SHA-256 del catálogo original (`4505…034e`, 0.11.0) quedó fijado en `tests/core/test_catalog_fragments.py`
  (el diccionario fusionado debe dar ese hash y el orden de `key_order`); se sigue aceptando un catálogo de un solo
  archivo por ruta (probado con un archivo temporal).
- `validate_brief` cita ahora `spaceplan.modules.household.main.run_household.resolve_brief_program` (pendiente de
  la tanda 2; cambia solo el texto de un error).
- Prueba de arquitectura: sin puentes ni fachada (`test_old_packages_are_gone`, `test_visualize_facade_is_gone`),
  tabla 3.1 con `contract` y `run_viz`, más 5 pruebas de contratos (11 casos) (cada productor tiene `to_contract` /
  `from_contract`; el paquete se arma solo con `core`; `run_capacity` usa los `contract` de 5 módulos; `cost` no
  importa lotcap/site/household; `viz/main` dibuja desde contratos).

### 5. Documentación

- `docs/architecture/modules.md` **generado** por `tools/module_graph.py` (nuevo) desde las importaciones (grafo
  Mermaid con número de archivos por arista, tabla importa/importado por, archivos por capa) y desde los esquemas
  (tabla de contratos), más la sección fija "Cómo agregar un módulo". `tests/pipeline/test_docs.py` falla si queda
  desactualizado.
- README (sección "Modular architecture", "Layout", "Usage"), `contracts/README.md` y HANDOFF (estado, reglas 4 y
  5, sección 2, sección 3 con tabla por módulo, **nueva sección 4i**, sección 8, innovación y mensaje sugerido).

## Justificación de la baja en el número de pruebas (1,107 → 1,026)

| Cambio | Casos |
|---|---|
| Pruebas de puentes eliminadas con los puentes: `test_bridge_modules_reexport_core` (16), `test_tanda2_bridges_reexport_their_module` (45), `test_tanda2_bridges_cover_the_old_files` (1), `test_lib_aux_is_leaf` (12), `test_lib_does_not_import_main` (43), fachada `visualize` (2) | −119 |
| `test_no_extractor_imports` parametrizada por archivo: 64 archivos menos (puentes y fachada) y 9 nuevos | −55 |
| Arquitectura nueva: archivos nuevos en `test_layers_inside_each_module` (+9), `test_real_modules_do_not_import_bridges` (+9), `test_core_imports_only_core` (+1), 5 pruebas de contratos (+11 casos), puentes y fachada eliminados (+2) | +32 |
| Pruebas por módulo y de pipeline con contratos fijos, documento generado | +60 |
| `test_catalog_fragments` (prueba de que el archivo original ya no existe) | +1 |
| **Total** | **−81** |

Las 536 pruebas que no son de arquitectura de la tanda 3 siguen todas (movidas de carpeta, con importaciones
canónicas; 3 de `test_catalog_fragments` comparan ahora contra el hash fijo en vez del archivo eliminado); la de arquitectura pasa de 571 a 429 casos porque la mayoría de los casos eliminados verificaban
puentes que ya no existen.

## Tiempos de la suite (este entorno, 2 núcleos, `python -m pytest tests/<módulo>`, carpetas en serie)

| Carpeta | Pruebas | Tiempo |
|---|---|---|
| core | 79 | 1 min 32 s |
| lotcap | 50 | 1 min 55 s |
| site | 36 | 1 min 6 s |
| household | 233 | 3 min 46 s |
| cost | 37 | 14 s |
| profiles | 33 | 43 s |
| zoning | 62 | 1 min 9 s |
| areas | 51 | 15 s |
| viz | 4 | 3 s |
| pipeline | 441 | 32 s |
| **Total** | **1,026** | **≈ 11 min 17 s en serie** |

Comparación: al inicio de la tanda la suite tardaba ≈ 7–9 min de reloj (≈ 11 min sumando tandas de archivos). Por
carpetas en serie tarda ≈ 11 min 17 s en serie. La mayor parte es `household` (por `test_program`, que corre los 5 briefs de
casa con el fixture de sesión `packages`) y `lotcap`/`core` (los mismos fixtures de sesión se recalculan en cada
carpeta). Las 60 pruebas nuevas de contratos suman ≈ 20 s; un módulo se prueba en segundos (`cost` ≈ 12 s,
`areas` ≈ 15 s, `viz` ≈ 3 s). Golden check: 2 min 36 s.

## Decisiones de diseño tomadas sin el usuario (para revisar)

1. **`contract.py` en `main/`** de cada módulo (no en `lib/`): `lotcap` arma el contrato desde `LotSetup` (de
   `main`) y `cost` reutiliza `run_cost.package_cost`; en `lib` violaría "lib no importa main".
2. **Se eliminó `assemble_package(PackageInputs)`**: el único camino para armar el paquete es desde contratos
   (`package_from_contracts`). Nadie fuera de `run_capacity` lo usaba.
3. **Serialización como el paquete**: `package_json` (4 decimales) para lote, sitio, zonificación y revisión;
   `plain_json` para hogar, costo, programa, portafolio y matriz (el paquete no los redondea). Así el paquete armado
   desde contratos es idéntico byte a byte.
4. **`site` y `zoning` no se rehidratan desde `lot_capacity`**: necesitan objetos de shapely, el marco local y el
   perfil de la envolvente en memoria. Sus comandos CLI corren los módulos previos; la prueba de `site` arma el
   patio leyendo la zonificación del contrato fijo y difiere < 0.01 sq ft solo en el patio (se prueba con
   tolerancia y el resto con igualdad exacta). El pipeline no usa ese camino, para no cambiar resultados.
5. **Nombres de comandos**: `household`, `profiles` y `areas` ya existían; escriben su contrato con `--contract`.
   `lotcap`, `site`, `zoning`, `cost` y `viz` son subcomandos nuevos.
6. **Contratos 0.2.0** con campos opcionales nuevos (no cambian el paquete): `brief_id`, `lot.lot_block`,
   `terrain`, `realization_strategy`, `site_plan.warnings`, `zoning_scheme.dwelling_type`.
7. **Pruebas por carpeta de módulo** con un solo `conftest.py` en `tests/` (las pruebas siguen importando
   `from conftest import ...`).
8. **Validación de contratos siempre activa** en el pipeline (≈ +4 % en el golden check: 2 min 31 s → 2 min 40 s).

## Errores encontrados sin corregir

- Ninguno de comportamiento.
- Avisos de ruff heredados que cambian de ruta: F401 `household_cells` sin usar en `tests/areas/test_area_matrix.py`
  y `CULTURE_ASPECTS` en `tests/household/test_culture.py`; ISC004 heredados en `cli.py` y `run_capacity.py`.
  Desaparecen 16 I001 heredados de las pruebas (se ordenaron las importaciones reescritas).
- Identificadores de esquema heredados (tanda 1): `package.schema.json` declara `$id .../package/0.6` con paquete
  0.9 y `brief.schema.json` `.../brief/0.2` con brief 0.5 (los contratos los referencian; no se tocan).
- HANDOFF sección 6, punto 9 ("las pruebas tardan ~65 s") está desactualizado desde antes de la reestructuración;
  se deja como registro histórico (los tiempos actuales están en la sección 4i).
- Fixtures de sesión (`packages`, `apartments`) se recalculan en cada carpeta cuando la suite se corre por módulo:
  suma tiempo en serie, no cambia resultados.

## Pendientes (fuera del plan de 4 tandas)

- Rehidratar la geometría de `lotcap` desde `lot_capacity` para que `site` y `zoning` corran solo con contratos.
- Paso 6.7 como módulo nuevo `stacking` (ver "Cómo agregar un módulo" en `docs/architecture/modules.md`). Fuera
  de estas tandas vuelve a regir "preguntar antes de programar".
- Llevar los validadores de `FRAGMENT_CHECKS` a cada módulo con un registro (pendiente desde la tanda 2).

## Posibilidades de innovación

- Caché por `input_sha256`: un módulo no se recalcula si su contrato de entrada no cambió (útil en la matriz del
  piloto y en el portafolio, que llaman a `run_capacity` muchas veces).
- Selección de pruebas por impacto con el grafo generado: correr solo `tests/<m>/` de los módulos alcanzados por
  un cambio.
- Contratos como API: servir cada módulo detrás de un esquema (p. ej. para que RuleForge consuma `lot_capacity`
  sin importar spaceplan) y versionarlos por separado.
- Generar los esquemas desde los tipos y los contratos fijos desde la instantánea en CI.
