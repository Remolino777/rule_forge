# Contratos entre módulos de `spaceplan`

Los contratos son las **fronteras** entre los módulos de la arquitectura modular (plan de reestructuración,
sección 3.3). Cada contrato es un objeto JSON validado contra un esquema JSON Schema **Draft 2020-12** guardado en
`schemas/<contrato>.schema.json`.

Estado (tanda 4, 9-oct-2026): **contratos ejecutables, versión 0.2.0.** Cada módulo productor tiene
`modules/<m>/main/contract.py` con `to_contract(...)` (arma el sobre y valida al producir) y
`from_contract(contrato)` (valida al leer y devuelve los bloques sin el sobre). El `pipeline` arma el paquete
**solo** desde los contratos (`pipeline/lib/package.py:package_from_contracts`); `cost` lee `lot_capacity`,
`site_plan` y `program` como JSON (sin importar código de esos módulos) y `viz` dibuja desde los contratos.
El código común está en `spaceplan/core/lib/contracts.py` (`make_contract`, `read_contract`, `validate_contract`,
`load_contract`, `write_contract`, `package_json`, `plain_json`).

Pruebas: `tests/core/test_contracts.py` (esquemas contra la instantánea dorada, tanda 1) y
`tests/<módulo>/test_<módulo>_contract.py` (salida del módulo = contrato fijo de `tests/<módulo>/fixtures/`,
validación y aceptación por el consumidor). Los contratos fijos los genera `python tools/make_fixtures.py write`,
que antes de escribir comprueba que el paquete armado con ellos es idéntico a la instantánea dorada.

Línea de comandos: `spaceplan lotcap|site|zoning BRIEF -o C.json`, `spaceplan household BRIEF --contract P.json`,
`spaceplan cost --lot-capacity .. --site-plan .. --program ..`, `spaceplan viz ...`, `--contract` en `profiles` y
`areas`, `spaceplan stacking [LOTES] [--area-matrix AM --lot-capacity LC ...] -o S.json` (paso 6.7),
`spaceplan capacity BRIEF --contracts DIR`.

## Sobre común

Todo contrato lleva:

| Campo | Contenido |
|---|---|
| `contract` | nombre del contrato (constante) |
| `version` | versión semántica del esquema del contrato (`0.1.0` en la tanda 1, `0.2.0` desde la tanda 4) |
| `produced_by` | módulo productor (constante) |
| `input_sha256` | SHA-256 (JSON canónico) de las entradas que leyó el productor (brief o contratos previos) |
| `brief_id` | opcional, informativo (brief al que pertenece; tanda 4) |
| `consumers` | opcional, informativo |

## Contratos

| Contrato | Produce | Consume | Bloques (reutilizan definiciones existentes) |
|---|---|---|---|
| `lot_capacity` | lotcap | site, zoning, areas, cost, viz | `lot.polygon` (GeoJSON, pies, marco local), `lot.lot_block` (bloque `lot` del brief planificado, para redibujar), `scope`, `lot_metrics`, `boundaries`, `rule_variants`, `lot_conformity`, `capacity`, `realizable_capacity`, `sensitivity`, `warnings` (del paquete); `terrain`, `realization_strategy` |
| `site_plan` | site | zoning, areas, cost, viz | `site_partition` (del paquete: opciones por pisos, accesos, pavimento, jardín, fachadas, patio), `warnings` del sitio |
| `program` | household | profiles, zoning, cost | `program` (del brief), `household` (del paquete, puede ser null), `program_review` (del paquete) |
| `cost_report` | cost | profiles, areas, pipeline | `cost` (del paquete: índice relativo, presupuesto, tornado; sin dinero) |
| `program_portfolio` | profiles | areas, viz | salida de `run_profiles`: `ceilings`, `curve`, `profiles` (cinco perfiles) |
| `zoning_scheme` | zoning | viz, pipeline | `zoning`, `unit`, `corrections` (del paquete), `dwelling_type`, `realization_strategy` |
| `area_matrix` | areas | viz, stacking | salida de `run_area_matrix`: `meta`, `lots` (presupuesto, resumen, E2), `cells` |
| `stack_plan` | stacking | viz, pipeline | paso 6.7 (`run_stacking`): `meta` (etapa S0/S1/S2, selección, reglas y catálogo con hash), `lots` (plano envolvente, pisos que permite la altura, sondeo bajo terreno), `cells` (niveles respecto del terreno, altura por tipo de techo, estado, etapa siguiente) |

`brief` (0.5) y `package` (0.9) ya existen en `data/schemas/` y no cambian.

## Cómo se resuelven las referencias

Los bloques se referencian con `$ref` al `$id` del esquema del paquete o del brief
(p. ej. `https://municipal-permit-intelligence/spaceplan/package/0.6#/properties/capacity`), de modo que un
contrato y el paquete nunca divergen. `spaceplan.core.lib.schema_validation.contract_registry()` arma el registro
que resuelve esas referencias y `contract_errors(instancia, nombre)` valida una instancia.

## Decisiones provisionales (revisar)

- Los esquemas están en `contracts/schemas/` (no en `contracts/` directamente) para que la prueba "sin dinero"
  (`tests/test_cost.py`), que excluye las rutas con `schemas`, no confunda `$schema`/`$ref` con un símbolo de moneda.
- `program_portfolio` y `area_matrix` no tienen esquema en el paquete. En la tanda 4 se detallaron: cada perfil
  exige `program` (esquema del brief), área, índice, calidad, factibilidad y `within_ceilings`; el perfil por etapas
  `today`/`final`; cada celda de la matriz exige lote, hogar, perfil, esquema, pisos, estado, IC, IO, índice,
  puntaje, rango, `best` y `pareto`.
- Serialización: los bloques que el paquete redondea (lote, sitio, zonificación, revisión del programa) pasan por
  `package_json` (4 decimales, como el paquete); los que el paquete lleva tal cual (hogar, costo, programa,
  portafolio, matriz) por `plain_json`. Por eso un módulo que lee un contrato redondeado (p. ej. el patio leyendo la
  zonificación) puede diferir en el último decimal de lo que calcula en memoria; las pruebas lo toleran (< 0.01).
- `site` y `zoning` necesitan objetos geométricos de `lotcap` en memoria (polígonos de shapely, marco local,
  perfil de la envolvente) que el contrato no serializa todavía: sus comandos corren antes los módulos previos.
  Rehidratar esos objetos desde `lot_capacity` queda como paso siguiente.
