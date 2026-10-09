# Informe de la tanda 3 — puntos calientes

Fecha: 9-oct-2026 · Rama: `spaceplan-modular` · Punto de partida: `refactor/tanda-2` (`1aee2ae`)
Ejecución: tarea programada, sin intervención del usuario (autorización del 8-oct-2026).

## Resultado

**Aceptada.** Pytest completo: **1,107 pruebas pasan** (1,062 al inicio + 45 nuevas, ninguna eliminada). Las 536
pruebas que no son de arquitectura son exactamente las mismas; la prueba de arquitectura pasa de 526 a 571 casos.
`python tools/golden_check.py check` → `GOLDEN CHECK PASSED (16 frozen files)` antes (2 min 19 s) y después de los
cambios (3 min 38 s, en paralelo con pytest).
`ruff check`: ningún aviso nuevo (88 → 88 por archivo, código y mensaje). El único "cambio" son los dos C408
heredados de `plot_review_sheet`, que se mudaron de `visualize.py` a `review_sheets.py` con el mismo código.

Verificación adicional de pureza (fuera de la instantánea dorada): antes y después se generaron, desde un árbol
aislado de `refactor/tanda-2`, las salidas de `derive_household` (8 arquetipos + apartamento con modelo `shape`),
`run_profiles` (lote con zonificación y láminas; hogar sin lote), `parameter_table`, `run_area_matrix` con E2 y
figuras (2 lotes × 2 hogares, `zone_top=2`) y los comandos `household` y `program` del CLI. **Los 15 archivos son
idénticos byte a byte** (sin los campos volátiles `seconds`, `package_id`, `generator`).

## Arranque (sección 2)

- `refactor/tanda-2` existe y apunta a `1aee2ae`, el mismo commit que `spaceplan-modular`.
- `pip install -e ".[dev]"` sin errores. Golden check previo: PASSED.

## Qué se hizo

### 1. Ciclo `zoning` ↔ `space_layout` roto

- Nuevo `modules/zoning/lib/band_enumeration.py` con `_compositions`, `_set_partitions`, `BandGeometry`,
  `_column_ok` y `band_arrangements`, **movidos sin cambios** desde `zoning.py`.
- `space_layout.py` importa `band_arrangements` de ahí (antes: importación diferida desde `zoning.py`, que a su
  vez importa `space_layout`). `zoning.py` importa los cinco nombres y los reexporta (el puente de la tanda 2 y
  `tests/test_zoning.py` usan los privados).

### 2. Interfaz pública del sitio

- `site_partition.py` declara su interfaz con `__all__` y publica `front_yard_area(ctx)`; `areas/lib/area_budget.py`
  la usa en vez de leer el atributo interno `ctx.front_yard.area` del contexto del sitio.
- `orientation.py` declara `__all__`; `backyard.py` agrega `backyard_for_site` a su `__all__` (lo usaba el
  pipeline pero no estaba declarado).
- Pruebas nuevas: ningún módulo importa nombres privados (`_x`) de otro módulo, y cuando un archivo declara
  `__all__` los demás módulos solo importan nombres de esa lista.

### 3. `run_capacity` como orquestador delgado; sin cadena `main` → `main`

| Antes | Ahora |
|---|---|
| `run_capacity` resolvía el lote bandera con `lotcap.lib.flag_lot` y armaba el aviso | `lotcap/main/run_lotcap.py`: `flag_lot_body`, `flag_lot_warning` |
| `run_capacity` elegía la estrategia de realización (auto / pedida / A sin perfil) | `lotcap/main/run_lotcap.py`: `select_strategy` |
| `run_capacity` llamaba a `build_site_partition` y `backyard_for_site` | `site/main/run_site.py` (nuevo): `plan_site`, `plan_site_backyard` |
| `run_capacity` llamaba a `zone_site_options`, `search_corrections`, `build_unit`, `zone_unit` | `zoning/main/run_zoning.py` (nuevo): `zone_house`, `zone_apartment` |
| `household/main/run_household.derive_household` llamaba a `cost/main/run_cost.household_cost` | el hogar recibe un `stage_cost` opcional; `pipeline/main/run_household_report.derive_household` lo compone con el costo (misma firma y salida) |
| `household/main/run_program.parameter_table` usaba `pipeline/lib/catalog_table` | `pipeline/main/run_catalog.py`: `parameter_table` (decisión 3 de la tanda 2) |
| `profiles/main/run_profiles.run_profiles` llamaba al hogar, a `run_capacity`, construía el lote y dibujaba | `pipeline/main/run_portfolio.py`: `run_profiles`, `run_profiles_file`; el `main` de profiles queda con las piezas del portafolio que reciben datos (`portfolio_model`, `portfolio_reading`, `assess_profiles`, `zoning_summary`, `review_sheet_header`, `portfolio_summary`, `portfolio_sheet_texts`, `household_line`, `lot_limits`) |
| `profile_programs` en `profiles/main` (usado por `areas/main`) | `profiles/lib/program_profiles.py` (sin cambios) |
| `areas/main/run_area_matrix.run_area_matrix` llamaba a lotcap/main, household/main, profiles/main, `run_capacity` y viz | `pipeline/main/run_area_analysis.py`: `run_area_matrix` y `_e2`; el `main` de areas queda con `analyze_lot` (E0/E1 de un lote ya preparado, para todos los hogares), `matrix_meta`, `lot_summary`, `write_tables`, `load_lot_brief`, `default_households`, `household_id` |

`pipeline/main/run_capacity.py` ahora solo compone: hogar → validación → bandera → revisión/alcance → lote →
estrategia → sitio → zonificación (+ corrección) → patio → paquete → validación → costo → figuras.
El CLI usa las rutas nuevas del pipeline.

### 4. `visualize.py` repartido por tema en `viz/lib/`

| Archivo nuevo | Contenido (movido sin cambios) |
|---|---|
| `lot_site_plots.py` | `plot_capacity`, `plot_site` y sus colores |
| `zoning_plots.py` | `plot_zoning` y sus colores |
| `review_sheets.py` | `plot_review_sheet`, `space_label_fn`, colores de las láminas |
| `portfolio_sheet.py` | `plot_portfolio_sheet`, `move_label` |
| `area_matrix_plots.py` | `plot_decision_map`, `plot_area_budget`, `plot_ic_io`, `plot_scheme_matrix` y constantes |

`visualize.py` queda como **fachada** que reexporta los cinco archivos (para el puente `spaceplan.lib.visualize`);
ningún archivo real lo importa (prueba nueva). Se elimina con los puentes en la tanda 4.

### 5. Excepciones temporales eliminadas; pruebas sin ciclos

- `TEMPORARY_EXCEPTIONS` queda vacía (las 13 de la tanda 2 se resolvieron); `test_temporary_exceptions_are_resolved`
  lo exige.
- `test_module_graph_has_no_cycles`: el grafo **real** entre módulos (sin puentes) es acíclico.
- `test_file_import_graph_has_no_cycles`: ningún ciclo entre archivos, contando importaciones diferidas y
  `from paquete import módulo`. Antes de esta tanda el único ciclo era `zoning` ↔ `space_layout`.
- `test_capacity_pipeline_is_a_thin_orchestrator`: `run_capacity` usa los `main` de household, cost, lotcap, site y
  zoning, y no importa las `lib` de cost, site, zoning ni `flag_lot`/`capacity` de lotcap.
- Tabla de archivos (3.1) actualizada con los archivos nuevos.

### 6. Puentes

Los puentes `spaceplan.main.run_household`, `run_program`, `run_profiles` y `run_area_matrix` reexportan su módulo
y, además, los flujos que pasaron al pipeline (`derive_household`, `parameter_table`, `run_profiles`,
`run_profiles_file`, `run_area_matrix`), de modo que las pruebas y `tools/golden_check.py` siguen importando por las
rutas viejas y obtienen el mismo comportamiento. La prueba de puentes lo verifica (identidad de objetos) con la
tabla `BRIDGE_PIPELINE_NAMES`.

## Decisiones de diseño tomadas sin el usuario (para revisar)

1. **Composiciones en `pipeline/main/`** con nombres nuevos (`run_household_report`, `run_catalog`,
   `run_portfolio`, `run_area_analysis`) para no repetir los nombres de los `main` de los módulos.
2. **Inyección de dependencia en el hogar** (`stage_cost`) en vez de mover `derive_household` entero: el hogar no
   conoce el costo y el orden de las claves de la salida se conserva. Efecto lateral: `resolve_brief_household` ya
   no calcula un costo que descartaba (misma salida, algo más rápido).
3. **`site/main` y `zoning/main` nuevos** (`run_site`, `run_zoning`) para que el pipeline componga flujos de módulo
   y no llame a sus `lib`. Son envoltorios delgados sin lógica nueva.
4. **`visualize.py` como fachada** hasta la tanda 4 (en lugar de borrarlo), por el puente `spaceplan.lib.visualize`.
5. **`__all__` agregados** en `site_partition`, `orientation`, `run_program` y en los `main` reescritos: los puentes
   con `import *` ahora exportan solo esa interfaz (antes también exportaban nombres importados como `Catalog`).
   Ninguna prueba ni herramienta usaba esos nombres.
6. **`catalog_table` sigue en `pipeline/lib`** (importa `household.lib`, así que no puede ir a `core`).

## Tiempos de la suite (este entorno, 2 núcleos, `python -m pytest`)

| Tanda de archivos | Pruebas | Tiempo |
|---|---|---|
| architecture, catalog, catalog_fragments, contracts, schemas, geometry, scope, orientation, rule_variants, capacity_reference | 696 | 3 min 47 s (en paralelo con golden check y la siguiente) |
| zoning, program | 93 | 4 min 54 s (en paralelo) |
| site_partition, backyard, circulation, realization, strategy_b | 58 | 58 s |
| household, culture, cost, cli | 186 | 36 s |
| profiles, area_matrix | 74 | 49 s |
| **Total** | **1,107** | **≈ 7 min de reloj (≈ 11 min sumando tandas)** |

Golden check: 2 min 19 s solo; 3 min 38 s en paralelo con pytest. Las 45 pruebas nuevas de arquitectura suman < 1 s.

## Errores encontrados sin corregir

- Ninguno de comportamiento.
- Avisos de ruff heredados en archivos tocados: `space_layout.py` (F401 `itertools` y `RealizedZones`, F841
  `along_x`), `backyard.py` (F401 `Polygon`, RUF022), `review_sheets.py` (C408 ×2, antes en `visualize.py`).
- El mensaje de `validate_brief` sigue citando `spaceplan.main.run_household.resolve_brief_program` (ruta válida por
  el puente; se actualiza en la tanda 4).

## Pendientes para la tanda 4

- Actualizar pruebas y `tools/golden_check.py` a las rutas nuevas (incluidas las del pipeline:
  `pipeline.main.run_household_report.derive_household`, `run_catalog.parameter_table`,
  `run_portfolio.run_profiles`, `run_area_analysis.run_area_matrix`), eliminar los 61 puentes, la fachada
  `viz/lib/visualize.py`, `BRIDGE_PIPELINE_NAMES` y el `residential_catalog.json` original.
- `to_contract` / `from_contract` por módulo: los puntos de corte ya existen (`prepare_lot`/`select_strategy`,
  `plan_site`, `zone_house`, `household_stages`, `assess_profiles`, `analyze_lot`, `package_cost`).
- CLI por módulo y pruebas por módulo con contratos de ejemplo; documentación `docs/architecture/modules.md`.
- Considerar mover los validadores de `FRAGMENT_CHECKS` a cada módulo con un registro (pendiente de la tanda 2).

## Posibilidades de innovación

- Con el grafo de archivos sin ciclos, generar automáticamente el diagrama de dependencias (módulos y archivos)
  en `docs/architecture/modules.md` desde `_file_graph()` en cada tanda.
- La inyección `stage_cost` es el primer "puerto" intercambiable entre módulos: el mismo patrón permite conectar
  más adelante un módulo de costo real (regla 7 del HANDOFF) sin tocar el módulo de hogar.
- Selección de pruebas por impacto: con el grafo acíclico, correr solo las pruebas de los módulos alcanzados por un
  cambio bajaría los ≈ 7 min de la suite en cambios locales.
- Instantáneas doradas adicionales para las salidas que hoy verificó a mano esta tanda (hogar, portafolio, E2):
  convertir `purity.py` en un modo de `golden_check.py` (requiere decisión del usuario: no se tocó `tests/golden/`).
