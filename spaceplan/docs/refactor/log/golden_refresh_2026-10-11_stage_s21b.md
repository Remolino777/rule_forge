# Fixture refresh — paso 6.7a etapa S2.1b (2026-10-11)

Aprobado por el cliente el 11-oct-2026 (decisiones del plan `spaceplan_6_7a_S2_1b_plan.md`: corredizas, baños por
dormitorio K10, salida al patio, voladizo de 6 ft, puerta principal típica de San Diego, antejardín con Z10/Z11).

## Golden (`tools/golden_check.py check`)
Sin cambios: GOLDEN CHECK PASSED (16 archivos). El ajuste de programa (K10 y reserva de pasillo) corre sobre una copia
de la celda dentro de `stacking`, solo en la etapa S2.1; la matriz de áreas y los paquetes de capacidad no cambian.

## Fixtures de contratos (`tools/make_fixtures.py write`)
- `tests/stacking/fixtures/stack_plan_interior_50x100_empty_nest_anglo.json`: `stacking_catalog_version`
  (0.10.0 → 0.11.0), su hash y el `input_sha256`. Fixture de la etapa S0; el contenido no cambia.
- `tests/areas/fixtures/area_matrix_…`: sin cambios (solo `seconds`, volátil; se dejó el anterior).

## Causas
1. Catálogo de apilamiento 0.11.0: tipos de puerta (`main_entry`, `patio_slider`, `service_exterior`,
   `closet_slider`), espacios con corrediza, `exits.patio`, `program` (reserva de pasillo, K10),
   `upper_floor.cantilever` (6 ft, solo S2.1), modo `best` para S2.1.
2. Ruleset `crc-2025-openings` 0.2.0: O04 puerta de egreso (R311.2), O05 rellano exterior (R311.3); `verified: false`.
3. Reglas de cliente 0.5.0: K10-BATHS-PER-BEDROOM.
4. Contrato `stack_plan`: bloques aditivos `s21.site`, `s21.k10`, `floor.patio_exit`, `cells.program_adjustment` y
   tipos de puerta nuevos (dentro de 0.2.0).

## Verificación
1362 pruebas aprobadas (suite completa, 10 min 27 s); lint sin errores nuevos frente a la base.
