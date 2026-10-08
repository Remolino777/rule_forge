# Contratos entre módulos de `spaceplan`

Los contratos son las **fronteras** entre los módulos de la arquitectura modular (plan de reestructuración,
sección 3.3). Cada contrato es un objeto JSON validado contra un esquema JSON Schema **Draft 2020-12** guardado en
`schemas/<contrato>.schema.json`.

Estado (tanda 1, 8-oct-2026): **esquemas escritos, todavía no ejecutables.** Ningún módulo produce ni consume aún
estos objetos; las funciones `to_contract` / `from_contract` llegan en la tanda 4. Las pruebas de la tanda 1
(`tests/test_contracts.py`) verifican que los esquemas son válidos y que instancias armadas desde la salida
actual (paquetes de la instantánea dorada, `run_profiles`, `run_area_matrix`) validan.

## Sobre común

Todo contrato lleva:

| Campo | Contenido |
|---|---|
| `contract` | nombre del contrato (constante) |
| `version` | versión semántica del esquema del contrato (`0.1.0` en la tanda 1) |
| `produced_by` | módulo productor (constante) |
| `input_sha256` | SHA-256 (JSON canónico) de las entradas que leyó el productor (brief o contratos previos) |
| `consumers` | opcional, informativo |

## Contratos

| Contrato | Produce | Consume | Bloques (reutilizan definiciones existentes) |
|---|---|---|---|
| `lot_capacity` | lotcap | site, zoning, areas, viz | `lot.polygon` (GeoJSON, pies, marco local), `scope`, `lot_metrics`, `boundaries`, `rule_variants`, `lot_conformity`, `capacity`, `realizable_capacity`, `sensitivity` (del paquete) |
| `site_plan` | site | zoning, areas, viz | `site_partition` (del paquete: opciones por pisos, accesos, pavimento, jardín, fachadas, patio) |
| `program` | household | profiles, zoning, cost | `program` (del brief), `household` (del paquete, puede ser null), `program_review` (del paquete) |
| `cost_report` | cost | profiles, areas, pipeline | `cost` (del paquete: índice relativo, presupuesto, tornado; sin dinero) |
| `program_portfolio` | profiles | areas, viz | salida de `run_profiles`: `ceilings`, `curve`, `profiles` (cinco perfiles) |
| `zoning_scheme` | zoning | viz, pipeline | `zoning`, `unit`, `corrections` (del paquete) |
| `area_matrix` | areas | viz | salida de `run_area_matrix`: `meta`, `lots` (presupuesto, resumen, E2), `cells` |

`brief` (0.5) y `package` (0.9) ya existen en `data/schemas/` y no cambian.

## Cómo se resuelven las referencias

Los bloques se referencian con `$ref` al `$id` del esquema del paquete o del brief
(p. ej. `https://municipal-permit-intelligence/spaceplan/package/0.6#/properties/capacity`), de modo que un
contrato y el paquete nunca divergen. `spaceplan.core.lib.schema_validation.contract_registry()` arma el registro
que resuelve esas referencias y `contract_errors(instancia, nombre)` valida una instancia.

## Decisiones provisionales (revisar)

- Los esquemas están en `contracts/schemas/` (no en `contracts/` directamente) para que la prueba "sin dinero"
  (`tests/test_cost.py`), que excluye las rutas con `schemas`, no confunda `$schema`/`$ref` con un símbolo de moneda.
- `program_portfolio` y `area_matrix` no tienen todavía un esquema detallado en el paquete: en la tanda 1 fijan solo
  las claves de primer nivel; se detallan en la tanda 4 junto con `to_contract`.
