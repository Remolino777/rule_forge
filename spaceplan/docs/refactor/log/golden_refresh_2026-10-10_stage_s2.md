# Fixture refresh — paso 6.7a etapa S2 (2026-10-10)

Aprobado por el cliente el 10-oct-2026 (decisiones D1–D5 del plan `spaceplan_6_7a_S2_plan.md`).

## Golden (`tools/golden_check.py check`)
Sin cambios: GOLDEN CHECK PASSED (16 archivos). Los paquetes de capacidad y la tabla compacta del análisis de áreas no
leen el bloque nuevo `space_split` ni el catálogo de apilamiento.

## Fixtures de contratos (`tools/make_fixtures.py write`)
- `tests/areas/fixtures/area_matrix_interior_50x100_empty_nest_anglo.json`: bloque aditivo `space_split` en cada
  celda de dos pisos (decisión D1: cada espacio con su piso, zona y área objetivo, tal como lo evaluó el reparto
  balanceado o el máximo recortado); `null` en las de un piso. Cambian también los `seconds` (volátiles).
- `tests/stacking/fixtures/stack_plan_interior_50x100_empty_nest_anglo.json`: solo `stacking_catalog_version`
  (0.4.0 → 0.5.0), su hash y el `input_sha256`. El fixture es de la etapa S0 y no cambia en contenido.

## Causas
1. Catálogo de apilamiento 0.5.0: bloque `s2` (rejilla, topologías, orden de llegada, puertas por zona, fusión de
   servicio, pesos, retroceso a S1).
2. Reglas de cliente de escalera 0.2.0: precedencia de K05 sobre la matriz base (decisión D4).
3. Contrato `area_matrix`: bloque aditivo `space_split` (dentro de 0.2.0).
