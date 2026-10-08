# Informe de la tanda 2 — paquetes de módulo

Fecha: 8-oct-2026 · Rama: `spaceplan-modular` · Punto de partida: `refactor/tanda-1` (`fbf1d3c`)
Ejecución: tarea programada, sin intervención del usuario (autorización del 8-oct-2026).

## Resultado

**Aceptada.** Pytest completo: **1,062 pruebas pasan** (725 al inicio + 337 nuevas, ninguna eliminada). Las 536
pruebas que no son de arquitectura son exactamente las mismas; la prueba de arquitectura pasa de 189 a 526 casos
(parametrizada por archivo).
`python tools/golden_check.py check` → `GOLDEN CHECK PASSED (16 frozen files)` antes (3 min 4 s) y después de los
cambios (3 min 8 s).
`ruff check`: ningún aviso nuevo. Comparado con `tanda-1` por (archivo, código, mensaje): 92 → 88; el único
"nuevo" es el F401 heredado de `space_layout.py` (`RealizedZones`) con la ruta nueva en el mensaje, y desaparecen
4 I001 heredados porque se ordenaron las importaciones de los archivos movidos.

## Arranque (sección 2)

- `refactor/tanda-1` existe y apunta a `fbf1d3c`, el mismo commit que `spaceplan-modular`.
- `pip install -e ".[dev]"` sin errores. Golden check previo: PASSED.
- Nota de entorno: el ejecutable `pytest` de este contenedor vive en otro entorno de Python (uv) y no ve el paquete;
  hay que usar `python -m pytest`.

## Qué se hizo

### 1. Paquetes `modules/<m>/{main,lib,lib_aux}` y `pipeline/{main,lib}` (con `git mv`, tabla 3.1)

| Antes | Ahora |
|---|---|
| `lib/{lot, boundaries, lot_metrics, rule_variants, scope, capacity, flag_lot}` | `modules/lotcap/lib/` |
| `main/run_capacity.prepare_lot` + `LotSetup` (+ `_measurement_methods`) | `modules/lotcap/main/run_lotcap.py` (nuevo) |
| `lib/{site_partition, orientation, backyard}` | `modules/site/lib/` |
| `lib/{household, household_catalog, household_rules, culture, program_builder, program_review}` | `modules/household/lib/` |
| `main/{run_household, run_program}` | `modules/household/main/` |
| `lib/{quantities, cost_models, budget, cost_sensitivity}` | `modules/cost/lib/` |
| `main/run_cost` | `modules/cost/main/` |
| `lib/program_profiles` | `modules/profiles/lib/` |
| `main/run_profiles` | `modules/profiles/main/` |
| `lib/{zoning, space_layout, circulation, relation_matrix, realization, polygonal, corrections, unit}` | `modules/zoning/lib/` |
| `main/run_corrections` | `modules/zoning/main/` |
| `lib/{vertical_split, building_indices, area_budget, area_matrix}` | `modules/areas/lib/` |
| `main/run_area_matrix` | `modules/areas/main/` |
| `lib/{visualize, review_notes}` | `modules/viz/lib/` |
| `lib/{package, catalog_table}` | `pipeline/lib/` |
| `main/{run_capacity (resto), cli}` | `pipeline/main/` |

- 37 archivos de `lib/` y 8 de `main/` movidos; cada módulo tiene `main/`, `lib/` y `lib_aux/` (los `lib_aux/` y
  `site/main`, `viz/main` quedan vacíos por ahora).
- **Todas las importaciones del código real** (incluidas las diferidas dentro de funciones y las de la forma
  `from spaceplan.lib import rule_variants as rv`) se reescribieron a las rutas canónicas `spaceplan.core.*`,
  `spaceplan.modules.*` y `spaceplan.pipeline.*`; ningún archivo real importa un puente (lo verifica una prueba).
  Las importaciones de los archivos movidos se ordenaron con `ruff --select I --fix` (solo orden).
- Solo cambiaron líneas de importación: el diff sin las líneas `import`/`from` contiene únicamente docstrings de
  los `__init__.py` nuevos y la referencia a `LotSetup` en el docstring de `area_budget.lot_budget`.
- `prepare_lot`/`LotSetup` se movieron **sin cambios** a `modules/lotcap/main/run_lotcap.py`;
  `pipeline/main/run_capacity.py` los importa y los reexporta, así que `spaceplan.main.run_capacity.prepare_lot`
  sigue siendo el mismo objeto. `run_area_matrix` ahora toma `prepare_lot` de `lotcap` (antes de `run_capacity`).
- Historial: commit 1 solo con `git mv` + reescritura de importaciones (no ejecutable por sí solo, para que
  `git log --follow` siga la historia); commit 2 con puentes, `run_lotcap`, pruebas, `pyproject` e informe.

### 2. Módulos puente en las rutas viejas

- **45 puentes** (`spaceplan/lib/*.py` 37 y `spaceplan/main/*.py` 8): `from <ruta nueva> import *`. Los 16 puentes
  de la tanda 1 hacia `core` siguen igual.
- Un análisis AST de `tests/` y `tools/` (importaciones `from ... import` y atributos sobre alias de módulo) mostró
  que las pruebas usan 8 nombres que `import *` no lleva porque `zoning.py` y `space_layout.py` declaran `__all__`:
  `zoning` → `BandGeometry`, `_column_ok`, `_compositions`, `_set_partitions`, `first_violation`, `front_precheck`,
  `merge_options`; `space_layout` → `fit_lengths`. Esos dos puentes los reexportan explícitamente.
- El puente `spaceplan.main.cli` conserva `if __name__ == "__main__": main()` (`python -m spaceplan.main.cli` sigue
  funcionando).
- Docstrings de `spaceplan/lib/__init__.py` y `spaceplan/main/__init__.py` actualizados: solo puentes.

### 3. Prueba de arquitectura v3 (`tests/test_architecture.py`)

- Cada módulo tiene `main/lib/lib_aux`; los archivos están donde dice la tabla 3.1.
- Dentro de cada módulo (y en `core`/`pipeline`): `lib_aux` no importa `lib`/`main`; `lib` no importa ningún `main`.
- **Grafo 3.2 por módulo, sin contar los puentes**: falla con cualquier arista no permitida que no esté en
  `TEMPORARY_EXCEPTIONS`. Regla aparte: ningún `main` de un módulo importa el `main` de otro (solo `pipeline`).
- `test_temporary_exceptions_are_still_needed`: si una excepción deja de existir hay que borrarla de la lista (la
  tanda 3 la deja vacía). `test_allowed_graph_is_acyclic` comprueba que el grafo permitido es acíclico.
- Los 45 puentes nuevos solo importan su módulo y reexportan **los mismos objetos** (identidad `is`).
- `prepare_lot` vive en `lotcap` y el puente devuelve el mismo objeto.

### 4. `pyproject.toml`

- Punto de entrada `spaceplan = "spaceplan.pipeline.main.cli:main"`.
- `packages.find include = ["spaceplan*"]` ya incluye `core`, `modules.*`, `pipeline` y los puentes (se anotó en un
  comentario); los datos ya estaban declarados desde la tanda 1 (no hay datos nuevos en esta tanda).

### 5. Pruebas que leen código fuente por ruta

Tres pruebas leen el archivo `.py` por su ruta (no lo importan). Con el puente en la ruta vieja una fallaría
(`run_corrections` debe llamar a `zone_site_options(retry=False)`) y las otras dos quedarían vacías (el puente no
tiene números). Se cambió **solo la ruta** a la nueva ubicación:
`test_profiles.test_breakfast_nook_is_social_and_retry_is_off_in_corrections`,
`test_architecture.test_no_normative_numbers_in_rule_variants` / `test_no_crc_numbers_in_program_review` y
`test_area_matrix.test_no_normative_number_in_new_code`. El resto de las pruebas sigue importando por las rutas
viejas (se actualizan en la tanda 4).

## Excepciones temporales al grafo de dependencias (8-oct-2026, resolver en la tanda 3)

| Archivo que importa | Importa | Regla que rompe |
|---|---|---|
| `modules/areas/main/run_area_matrix.py` | `pipeline.main.run_capacity` | areas → pipeline |
| `modules/areas/main/run_area_matrix.py` | `viz.lib.review_notes`, `viz.lib.visualize` | areas → viz |
| `modules/areas/main/run_area_matrix.py` | `household.main.run_household` | main → main |
| `modules/areas/main/run_area_matrix.py` | `profiles.main.run_profiles` | main → main |
| `modules/areas/main/run_area_matrix.py` | `lotcap.main.run_lotcap` | main → main |
| `modules/household/main/run_household.py` | `cost.main.run_cost` | household → cost y main → main |
| `modules/household/main/run_program.py` | `pipeline.lib.catalog_table` | household → pipeline |
| `modules/profiles/main/run_profiles.py` | `pipeline.main.run_capacity` | profiles → pipeline |
| `modules/profiles/main/run_profiles.py` | `lotcap.lib.lot` | profiles → lotcap |
| `modules/profiles/main/run_profiles.py` | `viz.lib.review_notes`, `viz.lib.visualize` | profiles → viz |
| `modules/profiles/main/run_profiles.py` | `household.main.run_household` | main → main |

Todas están en los `main/`: ninguna `lib/` rompe el grafo. Las aristas `lib` entre módulos (site → lotcap,
zoning → site, areas → site/lotcap/cost, profiles → household/cost, viz → lotcap, pipeline → todos) ya cumplen 3.2.

## Decisiones de diseño tomadas sin el usuario (para revisar)

1. **Nombre `run_lotcap.py`** para el `main` de `lotcap` (consistente con `run_*`).
2. **`run_area_matrix` toma `prepare_lot` de `lotcap/main`** en vez de `pipeline` (cambia una excepción
   areas → pipeline por una main → main, más fácil de quitar en la tanda 3); sigue usando `run_capacity` del pipeline
   para E2.
3. **`catalog_table` queda en `pipeline/lib`** como dice la tabla 3.1, aunque `household/main/run_program` lo usa.
   Propuesta para la tanda 3: llevar `parameter_table` (comando `catalog`) al `pipeline` o mover `catalog_table`
   a `core` (documenta el catálogo, que es de `core`).
4. **Puentes con nombres extra solo donde hace falta** (zoning, space_layout), con `noqa: F401`.
5. **Validadores semánticos del catálogo (`FRAGMENT_CHECKS`) siguen en `core/lib/catalog.py`.** Llevarlos a los
   módulos exige un registro (core no puede importar módulos); se deja para la tanda 3/4.
6. **Orden de importaciones** de los archivos movidos normalizado con ruff (cosmético).
7. **Mensaje de error sin cambiar**: `validate_brief` sigue citando `spaceplan.main.run_household.resolve_brief_program`
   (ruta válida por el puente). Cambiarlo cambiaría la salida; se actualiza al quitar los puentes en la tanda 4.

## Tiempos de la suite (este entorno, 2 núcleos, `python -m pytest`)

| Tanda de archivos | Pruebas | Tiempo |
|---|---|---|
| architecture, catalog, catalog_fragments, contracts, schemas, geometry, scope, orientation, rule_variants, capacity_reference | 651 | 3 min 11 s (en paralelo con la siguiente) |
| site_partition, backyard, circulation, realization, strategy_b | 58 | 1 min 18 s |
| zoning, program | 93 | 4 min 36 s (en paralelo con la siguiente) |
| household, culture, cost, cli | 186 | 49 s |
| profiles, area_matrix | 74 | 1 min 6 s |
| **Total** | **1,062** | **≈ 9 min de reloj (≈ 11 min sumando tandas)** |

Golden check: 3 min 8 s. Las 337 pruebas nuevas de arquitectura suman ≈ 3 s.

## Errores encontrados sin corregir

- Ninguno de comportamiento.
- El mensaje de `validate_brief` mencionado arriba (ruta vieja en el texto).
- Avisos de ruff heredados en archivos movidos sin cambios (p. ej. F401 `RealizedZones` en `space_layout.py`,
  ISC004 en `pipeline/main/run_capacity.py`, RUF059/C408/RUF007 en pruebas).

## Pendientes para la tanda 3

- Vaciar `TEMPORARY_EXCEPTIONS` (tabla de arriba): `run_capacity` delgado con hogar → `household/main`, costo →
  `cost/main`, lote bandera → `lotcap/main`; `run_household` no llama a `run_cost` (lo compone el pipeline);
  `run_profiles` y `run_area_matrix` no llaman al pipeline ni a otros `main` (recibir resultados o contratos), y
  dibujan a través del pipeline o de `viz`; `profiles` no construye lotes (recibir el lote de `lotcap`).
- Resolver `run_program` → `catalog_table` (decisión 3).
- Romper el ciclo `zoning` ↔ `space_layout`; interfaz pública del sitio para `areas` (hoy `area_budget` usa
  `site_partition` y `rule_variants`); repartir `visualize.py` por módulo.
- Prueba "sin ciclos" sobre el grafo real (hoy se verifica que el grafo **permitido** es acíclico).
- Considerar mover los validadores de `FRAGMENT_CHECKS` a cada módulo con un registro.

## Posibilidades de innovación

- Generar el grafo de módulos (`docs/architecture/modules.md`) directamente desde `_module_edges()` de la prueba
  de arquitectura, para que la documentación no se desactualice.
- Medir el acoplamiento por módulo (aristas entrantes/salientes) en cada tanda como métrica de salud del diseño.
- Ejecutar solo las pruebas de los módulos afectados por un cambio usando el mismo grafo (selección de pruebas por
  impacto), lo que bajaría los ≈ 9 min de la suite para cambios locales.
