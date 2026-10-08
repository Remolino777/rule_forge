# Informe de la tanda 1 — contratos, núcleo y catálogo

Fecha: 8-oct-2026 · Rama: `spaceplan-modular` · Punto de partida: `refactor/tanda-0` (`fee4ec0`)
Ejecución: tarea programada, sin intervención del usuario (autorización del 8-oct-2026).

## Resultado

**Aceptada.** Pytest completo: **725 pruebas pasan** (620 al inicio + 105 nuevas, ninguna eliminada).
`python tools/golden_check.py check` → `GOLDEN CHECK PASSED (16 frozen files)` (antes y después de los cambios).
`ruff check`: 0 errores en los archivos nuevos; el conjunto de avisos heredados es idéntico al de `tanda-0`
(92 líneas con la versión de ruff de este entorno; el plan hablaba de 67 con otra versión), solo cambian las rutas
de los archivos movidos.

## Arranque (sección 2)

- `refactor/tanda-0` existe y apunta a `fee4ec0`, el mismo commit que `spaceplan-modular`.
- `pip install -e ".[dev]"` sin errores. Golden check previo: PASSED (2 min 45 s).

## Qué se hizo

### 1. Contratos (`spaceplan/spaceplan/contracts/`)
- 7 esquemas Draft 2020-12 en `contracts/schemas/`: `lot_capacity`, `site_plan`, `program`, `cost_report`,
  `program_portfolio`, `zoning_scheme`, `area_matrix`. Todos con sobre `contract` (constante), `version` (0.1.0),
  `produced_by` (constante), `input_sha256` y `consumers` (opcional).
- Los bloques **reutilizan por `$ref`** las definiciones del esquema del paquete (0.9) y del brief (0.5); el lote
  de `lot_capacity` es un polígono GeoJSON en pies (marco local) y puede llevar la lectura de lote bandera.
- `contracts/README.md` en español (tabla de contratos, cómo se resuelven las referencias, decisiones).
- Funciones nuevas en `core/lib/schema_validation.py`: `CONTRACTS`, `load_contract_schema`, `contract_registry`
  (registro `referencing` con brief, paquete y contratos), `contract_errors`.
- Prueba nueva `tests/test_contracts.py` (20 pruebas): esquemas válidos, `$id` únicos, sobre correcto e instancias
  armadas desde los paquetes de la instantánea dorada (6 casas, 1 apartamento), `run_profiles` y `run_area_matrix`
  que validan; sobres erróneos se rechazan.

### 2. Núcleo `core/` (con `git mv`)
| Antes | Ahora |
|---|---|
| `lib_aux/{allocation, geometry, hashing, json_io, knee, pareto, predicates, quantity, section, tolerances, weighted}.py` | `core/lib_aux/` |
| `lib/{enums, rules, catalog, schema_validation, relation_graph}.py` | `core/lib/` |

- Dentro de `core/` las importaciones se reescribieron a `spaceplan.core.*` (incluida la importación diferida de
  `section.py`).
- En las rutas viejas quedan **16 módulos puente** de una línea (`from spaceplan.core.<capa>.<m> import *`).
  Un análisis AST de `spaceplan/`, `tests/` y `tools/` mostró que **nadie importa nombres privados** de esos
  módulos y que todos los nombres importados existen en los puentes (incluidos los tres módulos con `__all__`:
  `allocation`, `pareto`, `section`), por lo que no fue necesario reexportar nombres privados.
- El resto del código (`lib/`, `main/`) no cambió: sigue importando por las rutas viejas.

### 3. Catálogo en fragmentos (`data/catalog/fragments/`)
| Fragmento | Claves |
|---|---|
| `core` | `catalog_id`, `catalog_version`, `units`, `default_source`, `scales`, `zones`, `space_types` |
| `household` | `profiles`, `target_rounding_sqft`, `garage_by_cars`, `typologies` |
| `site` | `site_zone_types`, `orientation_model`, `backyard_policy`, `backyard_elements` |
| `zoning` | `zoning`, `zone_parts`, `zoning_profiles`, `circulation`, `relation_matrix`, `realization`, `corrections`, `polygonal_extension` |
| `cost` | `cost_index` |
| `profiles` | `accessibility` |
| `areas` | `area_analysis`, `vertical_schemes` |
| `viz` | `display` |

- `index.json`: orden de los fragmentos, `key_order` (orden original de claves) y `separate_catalogs`
  (`household_catalog.json` sigue siendo un catálogo aparte del módulo `household`, no se fusiona).
- Cargador (`core/lib/catalog.py`): `merge_fragments` (rechaza claves duplicadas, faltantes o fragmentos mal
  rotulados), `load_catalog_data` (por defecto los fragmentos empaquetados; con ruta acepta un archivo único —como
  antes— o un `index.json` en disco) y `load_catalog` (igual firma).
- Validación semántica repartida por fragmento en `FRAGMENT_CHECKS` (`core`, `household`, `cost`, `areas`), en el
  mismo orden y con los mismos mensajes que antes; `catalog_errors` conserva su firma.
- `residential_catalog.json` se conserva intacto como referencia hasta la tanda 4.
- Prueba nueva `tests/test_catalog_fragments.py` (18 pruebas): el diccionario fusionado es **idéntico** al original
  (igualdad, orden de claves y serialización), mismo SHA-256, cada clave con un solo dueño, carga desde índice y
  desde archivo único, errores de fusión y errores semánticos reportados por su fragmento.

### 4. Prueba de arquitectura v2 (`tests/test_architecture.py`, +67 casos parametrizados)
- `core` no importa nada fuera de `spaceplan.core`; `core/lib_aux` es hoja (no importa `core/lib`).
- `core` contiene los 16 archivos previstos.
- Cada puente solo importa su módulo de `core` y reexporta **los mismos objetos** (identidad `is`).

### 5. `pyproject.toml`
- `package-data`: `data/catalog/fragments/*.json`, `contracts/schemas/*.json`, `contracts/README.md`.

## Decisiones de diseño tomadas sin el usuario (para revisar)

1. **Ubicación de los esquemas**: `spaceplan/spaceplan/contracts/schemas/` (dentro del paquete instalable, como en
   la sección 3 del plan, pero en la subcarpeta `schemas/`). Motivo: la prueba `test_no_money_anywhere` excluye las
   rutas con `schemas` y, si no, confundiría `$schema`/`$ref` con el símbolo de moneda. Por la misma razón el
   registro usa `Resource.id()` en vez de leer `"$id"` en el código.
2. **Contratos por referencia al paquete**: los contratos no copian los bloques sino que apuntan al esquema del
   paquete; si el paquete cambia, el contrato cambia con él. `program_portfolio` y `area_matrix` (sin esquema en el
   paquete) solo fijan las claves de primer nivel; se detallan en la tanda 4.
3. **Carga y validación de contratos en `core/lib/schema_validation.py`**, no en un paquete `contracts` con código:
   así `core` sigue sin importar nada externo y `contracts/` queda como datos + documentación.
4. **Asignación de claves a fragmentos** (tabla de arriba). Casos discutibles: `profiles` (perfiles de tipología
   `balanced`, etc.) y `typologies` van a `household` porque los usa el constructor de programas; `accessibility`
   va a `profiles`; `display` (etiquetas y textos de láminas) va a `viz`; `space_types`/`zones`/`scales` quedan en
   `core` porque los usan casi todos los módulos.
5. **`key_order` en el índice** para que el diccionario fusionado sea idéntico también en el orden de claves (el
   SHA-256 ya era independiente del orden).
6. **Validadores semánticos todavía en `core/lib/catalog.py`**, agrupados por fragmento en `FRAGMENT_CHECKS`; en la
   tanda 2/3 pueden mudarse a cada módulo con un registro, sin cambiar mensajes.
7. **Puentes con `import *` sin nombres privados** (el análisis AST mostró que no hacen falta).
8. **Historial de git**: los archivos movidos se suben en un primer commit solo con `git mv` + reescritura de
   importaciones internas (para que `git log --follow` siga la historia) y un segundo commit con puentes, fragmentos,
   contratos y pruebas. El primer commit por sí solo no es ejecutable; la rama `refactor/tanda-1` apunta al segundo.

## Tiempos de la suite (este entorno, 2 núcleos)

| Tanda de archivos | Pruebas | Tiempo |
|---|---|---|
| architecture, catalog, catalog_fragments, contracts, schemas, geometry, scope, orientation, rule_variants, capacity_reference | 314 | 2 min 57 s (en paralelo con el golden check) |
| site_partition, backyard, circulation, realization, strategy_b | 58 | 1 min 8 s |
| zoning, program | 93 | 4 min 11 s |
| household, culture, cost, cli | 186 | 49 s |
| profiles, area_matrix | 74 | 1 min 2 s |
| **Total** | **725** | **≈ 10 min** |

Golden check: ≈ 2 min 45 s. Las pruebas nuevas suman ≈ 3 s.

## Errores encontrados sin corregir

- Ninguno de comportamiento. Solo se observó: `package.schema.json` declara `$id` `.../package/0.6` aunque el
  paquete va por 0.9, y `brief.schema.json` `.../brief/0.2` con brief 0.5 (identificadores, no versiones; se
  dejan como están porque los contratos los referencian).
- Avisos de ruff heredados en archivos movidos (B023 en `geometry.py`, RUF007 en `section.py`) sin cambios.

## Pendientes para la tanda 2

- Crear `modules/<m>/{main,lib,lib_aux}` y `pipeline/` y mover según 3.1, con puentes en `spaceplan.lib.*` y
  `spaceplan.main.*` (los puentes de la tanda 1 en `lib/`/`lib_aux/` se mantienen).
- Al mover `household`, `cost`, `areas`, considerar llevar sus validadores de `FRAGMENT_CHECKS` al módulo.
- Mientras exista `residential_catalog.json`, cualquier cambio de catálogo debe hacerse en el fragmento **y** en el
  archivo de referencia (la prueba de igualdad lo exige) — o mejor, no cambiar el catálogo hasta la tanda 4.
- Prueba de arquitectura v3 (grafo de 3.2).

## Posibilidades de innovación

- Generar los contratos desde los tipos (`dataclasses` → JSON Schema) para que código y esquema no diverjan.
- Versionado semántico automático del catálogo por fragmento (hash por fragmento en el paquete), para saber qué
  módulo cambió un resultado.
- Contratos como frontera para ejecutar módulos en paralelo o en servicios separados (el `input_sha256` permite
  caché de resultados por módulo).
