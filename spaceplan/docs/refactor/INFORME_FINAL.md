# Informe final de la reestructuración modular de spaceplan (sección 5 del plan)

Fecha: 9-oct-2026 · Repositorio `Remolino777/rule_forge`, rama `spaceplan-modular` · Ejecutado en 4 tandas
programadas (8–9 oct 2026) con la autorización del usuario del 8-oct-2026.

## Estado de las ramas instantáneas

| Rama | Commit | Contenido | Pruebas | Golden check |
|---|---|---|---|---|
| `refactor/tanda-0` | `fee4ec0` | punto de partida (pasos 1–6.6) | 620 | instantánea escrita |
| `refactor/tanda-1` | `fbf1d3c` | contratos (esquemas), `core/`, catálogo en fragmentos | 725 | PASSED |
| `refactor/tanda-2` | `1aee2ae` | `modules/<m>/{main,lib,lib_aux}`, `pipeline/`, grafo de dependencias | 1,062 | PASSED |
| `refactor/tanda-3` | `ae2db90` | ciclo roto, interfaz del sitio, `run_capacity` delgado, `visualize` repartido | 1,107 | PASSED |
| `refactor/tanda-4` | commit de cierre (= `spaceplan-modular`) | contratos ejecutables, CLI por módulo, pruebas por módulo, sin puentes | 1,026 | PASSED |

La rama `main` no se tocó; `tests/golden/` no se editó en ninguna tanda.

## Número de pruebas

620 → 725 → 1,062 → 1,107 → **1,026**. La baja de la tanda 4 (−81) se debe a que se eliminaron con los puentes
las 119 pruebas que los verificaban y 55 casos de una prueba parametrizada por archivo; se agregaron 60 pruebas de
contratos por módulo y 32 casos de arquitectura (detalle en `log/tanda-4.md`). Todas las pruebas de comportamiento
de la tanda 0 siguen (movidas a `tests/<módulo>/`).

## Tiempo de la suite

| Momento | Tiempo |
|---|---|
| Tanda 0 (inicio) | ≈ 9 min (en tandas de archivos con timeout de 10 min) |
| Tanda 3 | ≈ 7 min de reloj, ≈ 11 min sumando tandas |
| Tanda 4 (cierre, carpetas en serie) | ≈ 11 min 17 s en serie |
| Un módulo con sus contratos fijos | `cost` ≈ 12 s, `areas` ≈ 15 s, `viz` ≈ 3 s, `zoning` ≈ 1 min |

Por módulo: core 1 min 32 s · lotcap 1 min 55 s · site 1 min 6 s · household 3 min 46 s · cost 14 s · profiles 43 s · zoning 1 min 9 s · areas 15 s · viz 3 s · pipeline 32 s.

## Módulos y contratos creados

- **Núcleo** `core/` (lib: enums, rules, catalog, contracts, schema_validation, relation_graph; lib_aux: 11
  utilidades sin dominio).
- **8 módulos** `modules/{lotcap, site, household, cost, profiles, zoning, areas, viz}/{main,lib,lib_aux}`.
- **Composición** `pipeline/{main,lib}`: `run_capacity` (encadena contratos), `run_portfolio`, `run_area_analysis`,
  `run_household_report`, `run_catalog`, `run_modules`, CLI; `package` arma el paquete solo desde contratos.
- **7 contratos ejecutables (0.2.0)**: `lot_capacity` (lotcap), `site_plan` (site), `program` (household),
  `cost_report` (cost), `program_portfolio` (profiles), `zoning_scheme` (zoning), `area_matrix` (areas); más
  `brief` (0.5) y `package` (0.9), que no cambiaron. Cada productor tiene `to_contract` / `from_contract`
  validados; `cost` y `viz` consumen contratos como JSON.
- **CLI por módulo**: `lotcap`, `site`, `zoning`, `cost`, `viz`, más `--contract` en `household`, `profiles`,
  `areas` y `--contracts` en `capacity`. Los comandos anteriores no cambiaron.
- **Documentación**: `docs/architecture/modules.md` (generado desde el código), `contracts/README.md`, README,
  HANDOFF sección 4i, informes `log/tanda-1.md` a `tanda-4.md`.

## Garantía de que nada cambió

- Golden check en las 4 tandas: los 15 paquetes de referencia y la tabla de 3,148 celdas del piloto son idénticos a
  la instantánea de la tanda 0.
- Tanda 3: 15 salidas fuera de la instantánea (hogar, portafolio, matriz con E2 y figuras, CLI) idénticas byte a
  byte. Tanda 4: 21 paquetes en bruto (sin redondeo ni orden de claves) idénticos byte a byte a los de la tanda 3.

## Errores encontrados sin corregir (las 4 tandas)

- Ningún error de comportamiento.
- Identificadores de esquema heredados: `package.schema.json` `$id .../package/0.6` (paquete 0.9) y
  `brief.schema.json` `.../brief/0.2` (brief 0.5).
- Avisos de ruff heredados (73 en el informe completo, 89 al inicio de la tanda 4; ninguno nuevo en archivos creados o movidos), entre ellos
  importaciones sin usar en dos pruebas y concatenaciones implícitas en `cli.py` y `run_capacity.py`.
- HANDOFF sección 6 punto 9 con un tiempo de pruebas antiguo (registro histórico).

## Siguiente paso sugerido

**Paso 6.7 — apilamiento grueso como módulo nuevo `stacking`**: geometría de los esquemas verticales V1–V5 de 6.6
(planta alta contenida, escalera en la junta, plano envolvente 131.0444) para los mejores esquemas de dos pisos del
piloto. Leería los contratos `lot_capacity`, `site_plan` y `area_matrix` y produciría un contrato nuevo (propuesta:
`stacked_scheme`), siguiendo "Cómo agregar un módulo" en `docs/architecture/modules.md`. Antes conviene decidir si se
rehidrata la geometría de `lotcap` desde `lot_capacity` (para que `stacking` corra solo con contratos).

**Fuera de estas 4 tandas vuelve a regir la regla del usuario: primero análisis lógico y plan, y preguntar antes de
empezar a programar.**

## Posibilidades de innovación

- Caché por `input_sha256` y ejecución de módulos en paralelo o como servicios detrás de sus contratos.
- Selección de pruebas por impacto con el grafo generado (correr solo `tests/<m>/` de los módulos alcanzados).
- RuleForge (F3) podría consumir `lot_capacity` como contrato, sin importar spaceplan.
- Esquemas generados desde los tipos y contratos fijos regenerados en CI contra la instantánea.
