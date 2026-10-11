# Fixture refresh — paso 6.7a etapa S2.1 (2026-10-11)

Aprobado por el cliente el 11-oct-2026 (decisiones E1–E6 del plan `spaceplan_6_7a_S2_1_plan.md`).

## Golden (`tools/golden_check.py check`)
Sin cambios: GOLDEN CHECK PASSED (16 archivos). Los paquetes de capacidad no leen el catálogo de apilamiento ni el
ruleset nuevo de aberturas; el ruleset de habitabilidad no cambia (las reglas nuevas viven en
`data/rules/crc_2025_openings.json`).

## Fixtures de contratos (`tools/make_fixtures.py write`)
- `tests/stacking/fixtures/stack_plan_interior_50x100_empty_nest_anglo.json`: solo `stacking_catalog_version`
  (0.9.0 → 0.10.0), su hash y el `input_sha256`. El fixture es de la etapa S0 y no cambia en contenido.
- `tests/areas/fixtures/area_matrix_…`: sin cambios (solo variaba `seconds`, volátil; se dejó el anterior).

## Causas
1. Catálogo de apilamiento 0.10.0: bloque `s21` (subdivisión de unidades, sobrantes, puertas, fachada, búsqueda,
   profundidad vertical, pesos, retroceso).
2. Ruleset nuevo `crc-2025-openings` 0.1.0 (O01 escape R310, O02 aberturas del garaje R302.5.1, O03 habitables en
   fachada R303.1 vía C03), todo `verified: false`.
3. Contrato `stack_plan`: bloque aditivo `s21` por celda y etapa `S2.1` en `meta.stage` (dentro de 0.2.0).
