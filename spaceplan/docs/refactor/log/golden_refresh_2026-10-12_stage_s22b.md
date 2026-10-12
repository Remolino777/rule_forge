# Fixture refresh — paso 6.7a S2.2b (2026-10-12)

Aprobado por el cliente el 11/12-oct-2026: perfil intermedio (duros: baños y una pieza por espacio; preferencias
fuertes: recámara 11 × 10, clósets a muro completo, comedor y cocina).

## Golden (`tools/golden_check.py check`)
Sin cambios: GOLDEN CHECK PASSED (16 archivos). Los paquetes de capacidad no leen el catálogo de apilamiento ni el
registro de diseño.

## Fixtures de contratos (`tools/make_fixtures.py write`)
- `tests/stacking/fixtures/stack_plan_interior_50x100_empty_nest_anglo.json`: `stacking_catalog_version`
  (0.11.0 → 0.12.0), su hash y el `input_sha256`; contenido de la etapa S0 sin cambios.
- `tests/areas/fixtures/area_matrix_…`: sin cambios (solo `seconds`, volátil; se dejó el anterior).

## Causas
1. Catálogo de apilamiento 0.12.0: pesos de planta y de unidad con mobiliario, circulación y luz.
2. Estándares de diseño 0.3.0 y registro 0.2.0 (política de distribución, clósets, plantillas de cocina, kinds del
   perfil intermedio).

## Verificación
1440 pruebas: 1436 aprobadas en la corrida completa y las 4 restantes (documento de módulos, dos del contrato por la
versión del catálogo, la del baño compartido que ahora tiene su clóset de baño) corregidas y aprobadas.
